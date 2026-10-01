from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from odyn_ai.core.coding_agent import CodingAgent
from odyn_ai.core.execution import ExecutionEngine, ExecutionRequest
from odyn_ai.core.github_integration import GitHubIntegration
from nexus_core.reasoning.cognitive_engine import CognitiveEngine
from odyn_ai.core.experience_memory import AgentExperienceMemory
from nexus_core.plugins.deep_research import DeepResearchEngine
from odyn_ai.core.evolution import RoadmapDirective


@dataclass
class PipelineResult:
    app_id: str
    ok: bool
    changes: list[dict[str, str]]
    test: dict[str, Any]
    build: dict[str, Any] | None
    github: dict[str, Any] | None
    stage: str
    diagnostics: list[str]
    memory_events: list[int] = field(default_factory=list)
    cognitive_graph: dict[str, Any] = field(default_factory=dict)


class AutonomousBuildOrchestrator:
    """ODYN edit -> test -> correction -> build -> verify -> GitHub pipeline."""

    def __init__(
        self,
        apps,
        engine,
        coding_agent: CodingAgent,
        github: GitHubIntegration,
        memory: AgentExperienceMemory | None = None,
        *,
        max_corrections: int = 1,
        cognitive_engine: CognitiveEngine | None = None,
        swarm=None,
        evolution_branch: str = "odyn-evolution",
        deep_research: DeepResearchEngine | None = None,
    ) -> None:
        self.apps = apps
        self.execution = engine
        self.coding_agent = coding_agent
        self.github = github
        self.memory = memory
        self.max_corrections = max(0, max_corrections)
        self.cognitive = cognitive_engine or CognitiveEngine()
        self.swarm = swarm
        self.evolution_branch = evolution_branch
        self.deep_research = deep_research

    @staticmethod
    def _result_dict(result: Any) -> dict[str, Any]:
        if hasattr(result, "__dataclass_fields__"):
            return asdict(result)
        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "__dict__"):
            return dict(vars(result))
        raise TypeError("Execution result must be a dataclass, mapping, or object with attributes")

    def _remember(self, method: str, *args, **kwargs) -> None:
        if not self.memory:
            return
        try:
            getattr(self.memory, method)(*args, **kwargs)
        except Exception:
            # Persistence/RAG is advisory. It must never break a build.
            return

    def _remember_episode(self, method: str, *args, **kwargs) -> int | None:
        if not self.memory:
            return None
        try:
            episode = getattr(self.memory, method)(*args, **kwargs)
            return getattr(episode, "id", None)
        except TypeError:
            if not kwargs:
                return None
            try:
                episode = getattr(self.memory, method)(*args)
                return getattr(episode, "id", None)
            except Exception:
                return None
        except Exception:
            return None

    def _link_memory(self, source_id: int | None, target_id: int | None, relation: str) -> None:
        if not self.memory or source_id is None or target_id is None:
            return
        try:
            self.memory.link(source_id, target_id, relation)
        except Exception:
            return

    def _remember_change_episodes(
        self,
        app_id: str,
        changes: list[dict[str, str]],
        *,
        decision_id: int | None = None,
    ) -> list[int]:
        if not self.memory:
            return []
        try:
            episodes = self.memory.record_changes(
                app_id, changes, decision_id=decision_id
            )
        except TypeError:
            try:
                episodes = self.memory.record_changes(app_id, changes)
            except Exception:
                return []
        except Exception:
            return []
        return [episode.id for episode in episodes if getattr(episode, "id", None) is not None]

    def _cognitive_strategy_scores(
        self, instruction: str, files: dict[str, str], memory_context: str
    ) -> dict[str, float]:
        text = f"{instruction} {memory_context}".lower()
        scores = {"minimal_patch": 0.75, "test_first": 0.85, "architecture": 0.55}
        if any(word in text for word in ("refactor", "architecture", "architekt", "redesign")):
            scores["architecture"] += 0.35
        if any(word in text for word in ("failure", "fail", "błąd", "error", "napraw", "korekta")):
            scores["test_first"] += 0.10
        if len(files) >= 10:
            scores["test_first"] += 0.05
            scores["architecture"] += 0.05
        if any(word in text for word in ("simple", "prosty", "small", "mała")):
            scores["minimal_patch"] += 0.10
        return scores

    def _cognitive_snapshot(self, selected_strategy: str) -> dict[str, Any]:
        snapshot = self.cognitive.snapshot()
        snapshot["selected_strategy"] = selected_strategy
        return snapshot
    async def _apply(
        self,
        platform: str,
        instruction: str,
        files: dict[str, str],
        *,
        memory_context: str = "",
        inference_params: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.coding_agent.apply(
                platform,
                instruction,
                files,
                memory_context=memory_context,
                inference_params=inference_params,
            )
        except TypeError:
            if memory_context:
                try:
                    return await self.coding_agent.apply(
                        platform, instruction, files, memory_context=memory_context
                    )
                except TypeError:
                    pass
            return await self.coding_agent.apply(platform, instruction, files)

    def _persist_changes(
        self,
        app_id: str,
        previous: dict[str, str],
        edited: dict[str, Any],
    ) -> list[dict[str, str]]:
        changes = [
            change for change in edited.get("changes", [])
            if previous.get(change["path"]) != change["content"]
        ]
        for path, content in edited["files"].items():
            if previous.get(path) != content:
                self.apps.write_file(app_id, path, content)
        return changes

    async def _correct(
        self,
        app_id: str,
        platform: str,
        files: dict[str, str],
        stage: str,
        result: dict[str, Any],
        *,
        failed_execution_id: int | None = None,
        decision_cycle_id: str | None = None,
        decision_memory_id: int | None = None,
    ) -> tuple[dict[str, str], list[dict[str, str]], bool]:
        diagnostics = list(result.get("diagnostics", []))
        failure = (
            f"KOREKTA AUTONOMICZNA. Etap: {stage}. "
            f"Napraw błąd na podstawie diagnostyki, zachowując istniejącą funkcjonalność. "
            f"Diagnostyka: {' | '.join(diagnostics)}. "
            f"STDERR: {result.get('stderr', '')[-6000:]}"
        )
        context = self.memory.recall(failure, top_k=4) if self.memory else ""
        stress = self.memory.environmental_stress() if self.memory else 0.0
        edited = await self._apply(
            platform,
            failure,
            files,
            memory_context=context,
            inference_params=self.cognitive.cognitive_modulation(stress),
        )
        changes = self._persist_changes(app_id, files, edited)
        if not changes:
            return files, [], False

        correction_id = self._remember_episode(
            "record_correction",
            app_id,
            stage,
            diagnostics,
            changes,
            failed_execution_id=failed_execution_id,
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )
        correction_decision_id = self._remember_episode(
            "record_decision",
            app_id,
            failure,
            edited.get("summary", ""),
            changes,
            cognitive_strategy=None,
            decision_cycle_id=decision_cycle_id,
        )
        self._link_memory(decision_memory_id, correction_id, "corrects")
        if decision_memory_id is not None and correction_decision_id is not None:
            self._link_memory(decision_memory_id, correction_decision_id, "corrects")
        change_ids = self._remember_change_episodes(
            app_id, changes, decision_id=correction_decision_id
        )
        for change_id in change_ids:
            self._link_memory(change_id, failed_execution_id, "changed_before")
        return dict(edited["files"]), changes, True

    async def _execute_stage(
        self,
        app_id: str,
        platform: str,
        files: dict[str, str],
        stage: str,
        timeout: float,
        *,
        allow_correction: bool,
        cognitive_task: str | None = None,
        cognitive_parent_id: str | None = None,
        decision_cycle_id: str | None = None,
        decision_memory_id: int | None = None,
    ):
        result = await self.execution.execute(
            ExecutionRequest(platform, stage, files, timeout)
        )
        result_dict = self._result_dict(result)
        failed_execution_id = self._remember_episode(
            "record_execution", app_id, stage, result_dict,
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )

        if result.ok or not allow_correction:
            return files, [], result, failed_execution_id

        failure_text = (
            f"{stage} failed for {app_id}: "
            f"{' | '.join(result_dict.get('diagnostics', []))} "
            f"{result_dict.get('stderr', '')[-2000:]}"
        )
        failure_node = self.cognitive.add_thought(
            "failure",
            failure_text,
            parent_id=cognitive_parent_id,
            metadata={"stage": stage},
        )
        reflexion_node = self.cognitive.record_reflexion(
            cognitive_task or stage,
            failure_text,
            parent_id=failure_node,
        )
        self._remember_episode(
            "record_reflexion",
            app_id,
            stage,
            failure_text,
            failed_execution_id=failed_execution_id,
            cognitive_node_id=reflexion_node,
        )

        files, changes, corrected = await self._correct(
            app_id,
            platform,
            files,
            stage,
            result_dict,
            failed_execution_id=failed_execution_id,
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )
        if not corrected:
            return files, [], result, failed_execution_id

        self.cognitive.add_thought(
            "correction",
            f"{stage}: corrected {', '.join(item['path'] for item in changes)}",
            parent_id=reflexion_node,
            metadata={"changed_paths": [item["path"] for item in changes]},
        )

        retry = await self.execution.execute(
            ExecutionRequest(platform, stage, files, timeout)
        )
        retry_execution_id = self._remember_episode(
            "record_execution", app_id, f"{stage}_retry", self._result_dict(retry),
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )
        return files, changes, retry, retry_execution_id

    async def run(
        self,
        app_id: str,
        instruction: str,
        timeout: float = 300,
        github_repository: str | None = None,
        github_branch: str = "main",
        github_message: str = "feat(odyn): autonomous project update",
    ) -> PipelineResult:
        project = self.apps.workspace(app_id)
        platform = project["platform"]
        files = dict(project["files"])
        memory_events: list[int] = []
        changes: list[dict[str, str]] = []
        task_id: int | None = None

        if self.memory:
            try:
                task_id = self.memory.start_task(app_id, instruction, platform).id
                memory_events.append(task_id)
            except Exception:
                pass

        context = self.memory.recall(instruction, top_k=4) if self.memory else ""
        history_context = {}
        meta_context = (
            self.memory.infer_task_context(instruction, platform, files)
            if self.memory else {}
        )
        if self.memory and task_id is not None:
            try:
                task_episode = self.memory.store.get_episode(task_id)
                history_context = self.memory.history_context(
                    historical_transaction_at=task_episode.transaction_time_start,
                    valid_at=task_episode.valid_time_start,
                )
                meta_history = self.memory.meta_learning_context(meta_context)
                history_context["strategy_stats"] = meta_history["strategy_stats"]
                history_context["evidence_count"] = meta_history["evidence_count"]
                history_context["weighted_evidence"] = meta_history["weighted_evidence"]
                history_context["meta_learning"] = meta_history
            except Exception:
                history_context = {}
        environmental_stress = (
            self.memory.environmental_stress() if self.memory else 0.0
        )
        inference_policy = self.cognitive.cognitive_modulation(environmental_stress)
        evolution_context = ""
        roadmap: RoadmapDirective | None = None
        if self.swarm is not None:
            prepared = await self.swarm.prepare_cycle()
            roadmap = prepared.get("roadmap")
            if roadmap is not None:
                evolution_context = (
                    "\n\n[ODYN EVOLUTION ROADMAP]\n"
                    f"Version: {roadmap.version}\n"
                    "Architecture directives:\n"
                    + "\n".join(f"- {item}" for item in roadmap.architecture_changes[:20])
                    + "\nEvidence:\n"
                    + "\n".join(f"- {item}" for item in roadmap.evidence[:10])
                )

        task_node_id = self.cognitive.add_thought(
            "task",
            instruction + evolution_context,
            metadata={
                "environmental_stress": environmental_stress,
                "inference_policy": inference_policy,
            },
        )

        research_trace = None
        research_context = ""
        decision_parent_id = task_node_id
        if self.deep_research is not None:
            try:
                report = await self.deep_research.execute_rag_pipeline(
                    [instruction],
                    max_hops=2,
                    max_results=5,
                    max_followup_queries=4,
                )
                research_node_id = self.cognitive.add_thought(
                    "research_decision",
                    report.query,
                    parent_id=task_node_id,
                    metadata={
                        "hops": report.hops,
                        "source_count": len(report.sources),
                    },
                )
                decision_parent_id = research_node_id
                research_context = report.context
                if self.memory and task_id is not None:
                    task_episode = self.memory.store.get_episode(task_id)
                    research_trace = self.memory.record_research_pipeline(
                        task=task_episode,
                        report=report,
                        decision_cycle_id=None,
                    )
                    research_id = research_trace["research_decision"].id
                    memory_events.append(research_id)
                    for episode in research_trace["search_hops"].values():
                        memory_events.append(episode.id)
                    memory_events.extend(item.id for item in research_trace["sources"])
                    memory_events.append(research_trace["rag_context"].id)
            except Exception:
                # Research is an enrichment layer; failure must not disable the build pipeline.
                research_trace = None

        if research_context:
            context = f"{context}\n\n[DEEP RESEARCH RAG]\n{research_context}".strip()

        strategy_scores = self._cognitive_strategy_scores(instruction, files, context)
        strategies = ["minimal_patch", "test_first", "architecture"]
        decision = self.cognitive.decision_cycle(
            instruction,
            strategies,
            lambda _node, action: strategy_scores[action],
            context=meta_context,
            history_context=history_context,
            critic_result="PASS",
            parent_id=decision_parent_id,
        )
        decision_cycle_id = decision.decision_id
        if decision.gate.rejected or decision.selected_strategy is None:
            return PipelineResult(
                app_id, False, changes, {}, None, None,
                "cognitive_gate",
                [f"Decision Cycle {decision_cycle_id} został odrzucony przez Adversarial Gate."],
                memory_events,
                self._cognitive_snapshot(None),
            )
        if self.memory and task_id is not None:
            try:
                task_episode = self.memory.store.get_episode(task_id)
                cognitive_memory = self.memory.record_cognitive_decision(
                    task=task_episode,
                    decision_cycle=decision,
                    research_trace=research_trace,
                )
                memory_events.append(cognitive_memory.id)
            except Exception:
                pass

        plan = {
            "root_id": decision.root_node_id,
            "branch_ids": list(decision.branch_ids),
            "selected_id": decision.selected_node_id,
            "selected_strategy": decision.selected_strategy,
            "history_aware": bool(history_context),
            "historical_bias": decision.got_evaluation,
        }
        selected_strategy = decision.selected_strategy
        history_instruction = ""
        if history_context:
            history_instruction = (
                "\n[ODYN HISTORY-AWARE CONTEXT]\n"
                f"Historical strategy statistics: {history_context.get('strategy_stats', {})}\n"
                f"Successful procedures: {len(history_context.get('successful_procedures', []))}\n"
                f"Failed procedures: {len(history_context.get('failed_procedures', []))}\n"
                f"Corrections: {len(history_context.get('corrections', []))}"
            )

        plan_memory_id = self._remember_episode(
            "record_cognitive_plan",
            app_id,
            instruction,
            strategies,
            selected_strategy,
            cognitive_node_id=plan["root_id"],
            environmental_stress=environmental_stress,
            context=meta_context,
            decision_cycle_id=decision_cycle_id,
        )
        if plan_memory_id is not None:
            memory_events.append(plan_memory_id)
            self._link_memory(task_id, plan_memory_id, "planned_by")
        for strategy, node_id in zip(strategies, plan["branch_ids"]):
            strategy_memory_id = self._remember_episode(
                "record_cognitive_strategy",
                app_id,
                strategy,
                selected=strategy == selected_strategy,
                cognitive_node_id=node_id,
            )
            if strategy_memory_id is not None:
                memory_events.append(strategy_memory_id)
                self._link_memory(plan_memory_id, strategy_memory_id, "branches_to")

        selected_instruction = (
            f"[ODYN COGNITIVE STRATEGY: {selected_strategy}] "
            f"Apply the selected build strategy deliberately. "
            f"Original task: {instruction}"
            f"{evolution_context}"
            f"{history_instruction}"
        )
        edited = await self._apply(
            platform, selected_instruction, files, memory_context=context, inference_params=inference_policy
        )
        initial_changes = self._persist_changes(app_id, files, edited)
        files = dict(edited["files"])
        changes.extend(initial_changes)

        decision_node_id = self.cognitive.add_thought(
            "coding_decision",
            edited.get("summary", ""),
            parent_id=plan["selected_id"],
            metadata={"strategy": selected_strategy},
        )
        decision_memory_id = self._remember_episode(
            "record_decision",
            app_id,
            selected_instruction,
            edited.get("summary", ""),
            initial_changes,
            cognitive_strategy=selected_strategy,
            cognitive_node_id=decision_node_id,
            decision_cycle_id=decision_cycle_id,
        )
        if decision_memory_id is not None:
            memory_events.append(decision_memory_id)
        initial_change_ids = self._remember_change_episodes(
            app_id, initial_changes, decision_id=decision_memory_id
        )
        memory_events.extend(initial_change_ids)
        self._link_memory(task_id, decision_memory_id, "decided_by")

        files, test_changes, test, test_memory_id = await self._execute_stage(
            app_id, platform, files, "test", timeout,
            allow_correction=self.max_corrections > 0,
            cognitive_task=instruction,
            cognitive_parent_id=decision_node_id,
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )
        changes.extend(test_changes)
        if test_memory_id is not None:
            memory_events.append(test_memory_id)

        if not test.ok:
            self.cognitive.record_decision_outcome(
                decision,
                outcome="test_failure",
                execution_id=test_memory_id,
                correction=bool(test_changes),
            )
            return PipelineResult(
                app_id, False, changes, self._result_dict(test), None, None,
                "test",
                test.diagnostics + ["Build został zatrzymany, ponieważ testy nie przeszły."],
                memory_events,
                self._cognitive_snapshot(selected_strategy),
            )

        files, build_changes, build, build_memory_id = await self._execute_stage(
            app_id, platform, files, "build", timeout,
            allow_correction=self.max_corrections > 0,
            cognitive_task=instruction,
            cognitive_parent_id=decision_node_id,
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )
        changes.extend(build_changes)
        if build_memory_id is not None:
            memory_events.append(build_memory_id)

        if not build.ok:
            self.cognitive.record_decision_outcome(
                decision,
                outcome="build_failure",
                execution_id=build_memory_id,
                correction=bool(build_changes),
            )
            return PipelineResult(
                app_id, False, changes, self._result_dict(test), self._result_dict(build), None,
                "build",
                build.diagnostics + ["Weryfikacja artefaktu nie powiodła się."],
                memory_events,
                self._cognitive_snapshot(selected_strategy),
            )

        success_memory_id = self._remember_episode(
            "record_success",
            app_id,
            platform,
            "verified",
            build.artifact,
            source_execution_id=build_memory_id,
            decision_cycle_id=decision_cycle_id,
            decision_memory_id=decision_memory_id,
        )

        dgm_result = None
        if self.swarm is not None and roadmap is not None:
            dgm_result = await self.swarm.apply_roadmap(
                roadmap,
                self.evolution_branch,
                changes,
            )
            if not dgm_result:
                self.cognitive.record_decision_outcome(
                    decision,
                    outcome="dgm_failure",
                    execution_id=build_memory_id,
                    correction=False,
                )
                return PipelineResult(
                    app_id, False, changes, self._result_dict(test), self._result_dict(build), None,
                    "dgm",
                    ["Testy PASS", "Build PASS", "DGM/GitLab commit nie powiódł się."],
                    memory_events,
                    self._cognitive_snapshot(selected_strategy),
                )

        github_result = None
        if github_repository:
            github_result = asdict(await self.github.commit_files(
                github_repository, files, github_message, github_branch, False
            ))

        if success_memory_id is not None:
            memory_events.append(success_memory_id)
        self.cognitive.record_decision_outcome(
            decision,
            outcome="verified",
            execution_id=build_memory_id,
            correction=bool(test_changes or build_changes),
        )

        return PipelineResult(
            app_id, True, changes, self._result_dict(test), self._result_dict(build),
            github_result, "verified",
            ["Testy PASS", "Build PASS", "Artefakt zweryfikowany."],
            memory_events,
            self._cognitive_snapshot(selected_strategy),
        )

