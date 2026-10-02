from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

import numpy as np

try:
    import networkx as nx
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("CognitiveEngine requires the 'networkx' dependency.") from exc


class CriticModel(Protocol):
    def evaluate_and_critique(self, task: str, output: str) -> str: ...
    def correct(self, task: str, output: str, critique: str) -> str: ...


@dataclass(frozen=True)
class ThoughtNode:
    node_id: str
    kind: str
    content: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CognitiveEvaluation:
    similarity: float
    distance: float
    passed: bool


@dataclass(frozen=True)
class AdversarialGateResult:
    similarity: float
    passed: bool
    rejected: bool
    reason: str


@dataclass(frozen=True)
class DecisionCycle:
    decision_id: str
    root_node_id: str
    context: dict[str, Any]
    candidate_strategies: tuple[str, ...]
    historical_evidence: dict[str, Any]
    got_evaluation: dict[str, float]
    gate: AdversarialGateResult
    selected_strategy: str | None
    selected_node_id: str | None
    branch_ids: tuple[str, ...]
    phases: tuple[str, ...]
    status: str


    @property
    def rejected(self) -> bool:
        """Backward-compatible view of the adversarial gate decision."""
        return self.gate.rejected

    @property
    def accepted(self) -> bool:
        return self.gate.passed and not self.gate.rejected


class CognitiveEngine:
    """Graph-of-Thought reasoning, bounded Reflexion and adaptive inference policy."""

    def __init__(
        self,
        *,
        evaluation_threshold: float = 0.80,
        stress_threshold: float = 0.80,
        max_reflections: int = 2,
    ) -> None:
        if not 0 <= evaluation_threshold <= 1:
            raise ValueError("evaluation_threshold must be between 0 and 1")
        if not 0 <= stress_threshold <= 1:
            raise ValueError("stress_threshold must be between 0 and 1")
        if max_reflections < 0:
            raise ValueError("max_reflections cannot be negative")
        self.thought_graph = nx.DiGraph()
        self.evaluation_threshold = evaluation_threshold
        self.stress_threshold = stress_threshold
        self.max_reflections = max_reflections
        self.decision_cycle_count = 0

    @staticmethod
    def _normalise(vector: Sequence[float]) -> np.ndarray:
        result = np.asarray(vector, dtype=np.float64).reshape(-1)
        if result.size == 0 or not np.all(np.isfinite(result)):
            raise ValueError("embedding must be non-empty and finite")
        return result

    def jepa_evaluate_embedding(
        self, state_embedding: Sequence[float], target_embedding: Sequence[float]
    ) -> float:
        state = self._normalise(state_embedding)
        target = self._normalise(target_embedding)
        if state.shape != target.shape:
            raise ValueError("embedding dimensions must match")
        denominator = np.linalg.norm(state) * np.linalg.norm(target)
        return 0.0 if denominator == 0 else float(np.dot(state, target) / denominator)

    def evaluate_embedding(
        self,
        state_embedding: Sequence[float],
        target_embedding: Sequence[float],
        *,
        threshold: float | None = None,
    ) -> CognitiveEvaluation:
        similarity = self.jepa_evaluate_embedding(state_embedding, target_embedding)
        threshold = self.evaluation_threshold if threshold is None else threshold
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        return CognitiveEvaluation(similarity, 1.0 - similarity, similarity >= threshold)

    def adversarial_gate(
        self,
        task: str,
        output: str,
        *,
        critic_result: str,
        state_embedding: Sequence[float],
        target_embedding: Sequence[float],
        threshold: float | None = None,
    ) -> AdversarialGateResult:
        """Apply deterministic safety/quality gating before accepting a candidate."""
        evaluation = self.evaluate_embedding(
            state_embedding, target_embedding, threshold=threshold
        )
        critic_upper = critic_result.upper()
        if any(marker in critic_upper for marker in ("UNSAFE", "REJECT", "INVALID", "FAIL")):
            return AdversarialGateResult(
                evaluation.similarity, False, True, "critic_rejected"
            )
        if not evaluation.passed:
            return AdversarialGateResult(
                evaluation.similarity, False, True, "embedding_below_threshold"
            )
        return AdversarialGateResult(
            evaluation.similarity, True, False, "accepted"
        )

    def add_thought(
        self,
        kind: str,
        content: str,
        *,
        parent_id: str | None = None,
        score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not kind.strip():
            raise ValueError("kind cannot be empty")
        node_id = f"{kind}_{self.decision_cycle_count}_{self.thought_graph.number_of_nodes()}"
        self.thought_graph.add_node(
            node_id, kind=kind, content=content, score=score, metadata=dict(metadata or {})
        )
        if parent_id is not None:
            if parent_id not in self.thought_graph:
                raise KeyError(f"Unknown parent thought: {parent_id}")
            self.thought_graph.add_edge(parent_id, node_id, relation="derives")
        return node_id

    def get_thought(self, node_id: str) -> ThoughtNode:
        data = self.thought_graph.nodes[node_id]
        return ThoughtNode(
            node_id, data["kind"], data["content"], data.get("score"), dict(data.get("metadata", {}))
        )

    def connect_thought(self, source_id: str, target_id: str, *, relation: str = "derives") -> None:
        """Connect two thoughts while preserving the Graph-of-Thought DAG invariant."""
        if source_id not in self.thought_graph or target_id not in self.thought_graph:
            raise KeyError("Both thought nodes must exist")
        if source_id == target_id or nx.has_path(self.thought_graph, target_id, source_id):
            raise ValueError("GoT must remain acyclic")
        self.thought_graph.add_edge(source_id, target_id, relation=relation)

    def branch(self, parent_id: str, alternatives: Sequence[str]) -> list[str]:
        return [self.add_thought("branch", item, parent_id=parent_id) for item in alternatives]

    def ab_mcts_step(
        self,
        current_node: str,
        possible_actions: Sequence[str],
        fitness_fn: Callable[[str, str], float],
        *,
        depth: int = 1,
        opponent_actions_fn: Callable[[str], Sequence[str]] | None = None,
        rollout_fn: Callable[[str], float] | None = None,
    ) -> str:
        """Select an action with bounded alpha-beta search over a GoT branch.

        With depth=1 this is the deterministic fitness selector used by the
        original API. With deeper search, optional opponent branches and
        rollouts provide a bounded adversarial tree search; it is deliberately
        deterministic and does not pretend to be a stochastic full MCTS.
        """
        if current_node not in self.thought_graph:
            raise KeyError(f"Unknown current node: {current_node}")
        if not possible_actions:
            raise ValueError("possible_actions cannot be empty")
        if depth < 1:
            raise ValueError("depth must be >= 1")

        def evaluate(node: str, actions: Sequence[str], remaining: int, alpha: float, beta: float, maximizing: bool) -> float:
            if not actions:
                return float(rollout_fn(node) if rollout_fn else 0.0)
            if remaining <= 1:
                values = [float(fitness_fn(node, action)) for action in actions]
                return max(values) if maximizing else min(values)
            values: list[float] = []
            if maximizing:
                value = -float("inf")
                for action in actions:
                    immediate = float(fitness_fn(node, action))
                    next_node = self.add_thought(
                        "search", action, parent_id=node, score=immediate,
                        metadata={"depth": remaining, "maximizing": True},
                    )
                    replies = list(opponent_actions_fn(action)) if opponent_actions_fn else []
                    child = immediate if not replies else evaluate(
                        next_node, replies, remaining - 1, alpha, beta, False
                    )
                    value = max(value, child)
                    alpha = max(alpha, value)
                    if alpha >= beta:
                        break
                return value
            value = float("inf")
            for action in actions:
                immediate = float(fitness_fn(node, action))
                next_node = self.add_thought(
                    "search", action, parent_id=node, score=immediate,
                    metadata={"depth": remaining, "maximizing": False},
                )
                replies = list(opponent_actions_fn(action)) if opponent_actions_fn else []
                child = immediate if not replies else evaluate(
                    next_node, replies, remaining - 1, alpha, beta, True
                )
                value = min(value, child)
                beta = min(beta, value)
                if alpha >= beta:
                    break
            return value

        best_action = possible_actions[0]
        best_score = -float("inf")
        for action in possible_actions:
            immediate = float(fitness_fn(current_node, action))
            score = immediate
            if depth > 1 and opponent_actions_fn:
                node_id = self.add_thought(
                    "search", action, parent_id=current_node, score=immediate,
                    metadata={"depth": depth, "root": True},
                )
                replies = list(opponent_actions_fn(action))
                if replies:
                    score = evaluate(
                        node_id, replies, depth - 1,
                        -float("inf"), float("inf"), False
                    )
            if score > best_score:
                best_action, best_score = action, score

        self.add_thought(
            "action", best_action, parent_id=current_node, score=best_score,
            metadata={"fitness": best_score, "search_depth": depth},
        )
        return best_action

    def decision_cycle(
        self,
        task: str,
        strategies: Sequence[str],
        fitness_fn: Callable[[str, str], float],
        *,
        context: dict[str, Any],
        history_context: dict[str, Any] | None = None,
        critic_result: str = "PASS",
        state_embedding: Sequence[float] | None = None,
        target_embedding: Sequence[float] | None = None,
        parent_id: str | None = None,
        search_depth: int = 1,
    ) -> DecisionCycle:
        """Run the bounded Decision Cycle 2.0 as one causal reasoning unit."""
        if not strategies:
            raise ValueError("strategies cannot be empty")
        decision_id = f"decision_{self.decision_cycle_count}_{self.thought_graph.number_of_nodes()}"
        history = dict(history_context or {})
        state_embedding = state_embedding if state_embedding is not None else [1.0]
        target_embedding = target_embedding if target_embedding is not None else [1.0]

        phases = (
            "context",
            "candidate_strategies",
            "historical_evidence",
            "got_evaluation",
            "adversarial_gate",
            "strategy_selection",
        )
        root_id = self.add_thought(
            "decision_cycle",
            task,
            parent_id=parent_id,
            metadata={"decision_id": decision_id, "phase": "context", "context": dict(context)},
        )
        candidate_id = self.add_thought(
            "candidate_strategies",
            ", ".join(strategies),
            parent_id=root_id,
            metadata={"decision_id": decision_id, "phase": "candidate_strategies"},
        )
        evidence_id = self.add_thought(
            "historical_evidence",
            "contextual strategy evidence",
            parent_id=candidate_id,
            metadata={
                "decision_id": decision_id,
                "phase": "historical_evidence",
                "strategy_stats": history.get("strategy_stats", {}),
                "evidence_count": history.get("evidence_count", 0),
                "weighted_evidence": history.get("weighted_evidence", 0.0),
            },
        )

        base_scores = {
            strategy: float(fitness_fn(evidence_id, strategy))
            for strategy in strategies
        }
        plan = self.plan_build(
            task,
            strategies,
            lambda _node, action: base_scores[action],
            parent_id=evidence_id,
            history_context=history,
        )
        got_scores = {
            strategy: float(base_scores[strategy] + plan["historical_bias"].get(strategy, 0.0))
            for strategy in strategies
        }
        got_id = self.add_thought(
            "got_evaluation",
            "strategy fitness evaluated",
            parent_id=evidence_id,
            metadata={"decision_id": decision_id, "phase": "got_evaluation", "scores": got_scores},
        )
        gate = self.adversarial_gate(
            task,
            task,
            critic_result=critic_result,
            state_embedding=state_embedding,
            target_embedding=target_embedding,
        )
        gate_id = self.add_thought(
            "adversarial_gate",
            gate.reason,
            parent_id=got_id,
            metadata={
                "decision_id": decision_id,
                "phase": "adversarial_gate",
                "similarity": gate.similarity,
                "passed": gate.passed,
                "rejected": gate.rejected,
            },
        )
        if not gate.passed:
            self.decision_cycle_count += 1
            return DecisionCycle(
                decision_id, root_id, dict(context), tuple(strategies), history, got_scores,
                gate, None, None, (), phases, "rejected",
            )

        selected = self.ab_mcts_step(
            got_id,
            strategies,
            lambda _node, action: got_scores[action],
            depth=search_depth,
        )
        selection_id = self.add_thought(
            "strategy_selection",
            selected,
            parent_id=gate_id,
            score=got_scores[selected],
            metadata={"decision_id": decision_id, "phase": "strategy_selection"},
        )
        self.decision_cycle_count += 1
        return DecisionCycle(
            decision_id, root_id, dict(context), tuple(strategies), history, got_scores,
            gate, selected, selection_id, tuple(plan["branch_ids"]), phases, "selected",
        )

    def record_decision_outcome(
        self,
        cycle: DecisionCycle,
        *,
        outcome: str,
        execution_id: int | None = None,
        correction: bool = False,
    ) -> str:
        """Close a Decision Cycle with an explicit outcome node."""
        if cycle.status != "selected":
            raise ValueError("Only a selected Decision Cycle can be closed")
        if not outcome.strip():
            raise ValueError("outcome cannot be empty")
        outcome_id = self.add_thought(
            "decision_outcome",
            outcome,
            parent_id=cycle.selected_node_id,
            metadata={
                "decision_id": cycle.decision_id,
                "phase": "outcome",
                "execution_id": execution_id,
                "correction": correction,
                "status": "completed",
            },
        )
        return outcome_id

    def plan_build(
        self,
        task: str,
        strategies: Sequence[str],
        fitness_fn: Callable[[str, str], float],
        *,
        parent_id: str | None = None,
        history_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a bounded build strategy graph and select one strategy.

        The graph stores compact decision summaries, not hidden chain-of-thought.
        """
        if not strategies:
            raise ValueError("strategies cannot be empty")
        history = dict(history_context or {})
        strategy_history = history.get("strategy_stats", {})
        historical_bias: dict[str, float] = {}
        for strategy in strategies:
            stats = strategy_history.get(strategy, {})
            successes = float(stats.get("successes", 0))
            failures = float(stats.get("failures", 0))
            attempts = successes + failures
            evidence_count = int(history.get("evidence_count", attempts))
            if attempts and evidence_count >= 2:
                confidence = min(1.0, attempts / 5.0)
                historical_bias[strategy] = max(
                    -0.25,
                    min(0.25, ((successes - failures) / attempts) * 0.25 * confidence),
                )
            else:
                historical_bias[strategy] = 0.0

        root_id = self.add_thought(
            "cognitive_plan",
            task,
            parent_id=parent_id,
            metadata={
                "strategy_count": len(strategies),
                "history_aware": bool(history),
                "historical_bias": historical_bias,
                "historical_snapshot": history.get("historical_snapshot"),
            },
        )
        branch_ids = self.branch(root_id, strategies)
        branch_scores = {
            strategy: float(fitness_fn(root_id, strategy)) + historical_bias.get(strategy, 0.0)
            for strategy in strategies
        }
        selected = self.ab_mcts_step(
            root_id,
            strategies,
            lambda _node, action: branch_scores[action],
        )
        selected_index = list(strategies).index(selected)
        selected_id = self.add_thought(
            "selected_strategy",
            selected,
            parent_id=branch_ids[selected_index],
            score=branch_scores[selected],
            metadata={
                "alternatives": list(strategies),
                "base_scores": {key: float(fitness_fn(root_id, key)) for key in strategies},
                "historical_bias": historical_bias,
            },
        )
        self.decision_cycle_count += 1
        return {
            "root_id": root_id,
            "branch_ids": branch_ids,
            "selected_id": selected_id,
            "selected_strategy": selected,
            "history_aware": bool(history),
            "historical_bias": historical_bias,
        }

    def record_reflexion(
        self,
        task: str,
        failure: str,
        *,
        parent_id: str | None = None,
    ) -> str:
        """Record a compact failure -> reflection node in the decision graph."""
        if parent_id is None:
            parent_id = self.add_thought("failure", failure, metadata={"task": task})
        reflection_id = self.add_thought(
            "reflexion",
            failure,
            parent_id=parent_id,
            metadata={"task": task},
        )
        self.decision_cycle_count += 1
        return reflection_id

    def reflexion_loop(
        self,
        task: str,
        initial_output: str,
        critic_model: CriticModel,
        *,
        max_reflections: int | None = None,
    ) -> str:
        limit = self.max_reflections if max_reflections is None else max_reflections
        if limit < 0:
            raise ValueError("max_reflections cannot be negative")

        parent_id = self.add_thought("attempt", initial_output, metadata={"task": task})
        current = initial_output
        for reflection_index in range(limit + 1):
            critique = critic_model.evaluate_and_critique(task, current)
            critique_id = self.add_thought(
                "critique", critique, parent_id=parent_id,
                metadata={"reflection": reflection_index},
            )
            self.decision_cycle_count += 1
            rejected = any(
                marker in critique.upper()
                for marker in ("FAIL", "REJECT", "UNSAFE", "INVALID")
            )
            if not rejected or reflection_index == limit:
                return current
            current = critic_model.correct(task, current, critique)
            parent_id = self.add_thought(
                "correction", current, parent_id=critique_id,
                metadata={"reflection": reflection_index},
            )
        return current

    def cognitive_modulation(self, environmental_stress: float) -> dict[str, float]:
        stress = float(environmental_stress)
        if not 0 <= stress <= 1:
            raise ValueError("environmental_stress must be between 0 and 1")
        if stress >= self.stress_threshold:
            ratio = (stress - self.stress_threshold) / max(1e-9, 1 - self.stress_threshold)
            return {"temperature": round(0.20 - 0.10 * ratio, 4), "top_p": round(0.65 - 0.15 * ratio, 4)}
        ratio = stress / max(self.stress_threshold, 1e-9)
        return {"temperature": round(0.70 - 0.20 * ratio, 4), "top_p": round(0.90 - 0.10 * ratio, 4)}

    def snapshot(self) -> dict[str, Any]:
        return {
            "decision_cycle_count": self.decision_cycle_count,
            "nodes": [
                {
                    "id": node_id,
                    "kind": data["kind"],
                    "content": data["content"],
                    "score": data.get("score"),
                    "metadata": dict(data.get("metadata", {})),
                }
                for node_id, data in self.thought_graph.nodes(data=True)
            ],
            "edges": [
                {"source": source, "target": target, "relation": data.get("relation", "derives")}
                for source, target, data in self.thought_graph.edges(data=True)
            ],
        }
