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
            if attempts:
                historical_bias[strategy] = max(-0.25, min(0.25, (successes - failures) / attempts * 0.25))
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
