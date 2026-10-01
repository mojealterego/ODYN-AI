import tempfile
import unittest
from pathlib import Path

from nexus_core.memory import BitemporalMemoryNode
from odyn_ai.core.experience_memory import AgentExperienceMemory


class ExperienceMemoryTests(unittest.TestCase):
    def test_environmental_stress_reflects_recent_failures_and_successes(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )
            for ok in (False, False, False, True):
                memory.record_execution(
                    "app-1",
                    "test",
                    {"ok": ok, "exit_code": 0 if ok else 1, "diagnostics": []},
                )

            stressed = memory.environmental_stress()
            self.assertGreater(stressed, 0.5)

            memory.record_execution(
                "app-1", "test",
                {"ok": True, "exit_code": 0, "diagnostics": []},
            )
            recovered = memory.environmental_stress()
            self.assertLess(recovered, stressed)

    def test_environmental_stress_is_bounded_without_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )
            self.assertEqual(memory.environmental_stress(), 0.0)

    def test_history_context_contains_snapshot_outcomes_and_strategy_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )
            task = memory.start_task("app-1", "zbuduj kalkulator", "web")
            memory.record_cognitive_plan(
                "app-1", "zbuduj kalkulator",
                ["minimal_patch", "test_first"], "test_first",
            )
            memory.record_execution(
                "app-1", "test",
                {"ok": False, "exit_code": 1, "diagnostics": ["failed"]},
            )
            memory.record_correction(
                "app-1", "test", ["failed"],
                [{"path": "app.py", "content": "fixed"}],
            )
            memory.record_success("app-1", "web", "verified", "dist")

            context = memory.history_context(
                historical_transaction_at=task.transaction_time_start,
                valid_at=task.valid_time_start,
            )

            self.assertIn("current_memory", context)
            self.assertIn("historical_snapshot", context)
            self.assertIn("successful_procedures", context)
            self.assertIn("failed_procedures", context)
            self.assertIn("corrections", context)
            self.assertEqual(context["strategy_stats"]["test_first"]["successes"], 1)
            self.assertEqual(context["strategy_stats"]["test_first"]["failures"], 0)
            self.assertEqual(context["historical_snapshot"]["episodic_count"], 1)

    def test_meta_learning_is_context_specific(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )
            first = memory.start_task("web-1", "refactor frontend UI", "web")
            memory.record_cognitive_plan(
                "web-1", "refactor frontend UI",
                ["minimal_patch", "test_first"], "minimal_patch",
                context={"task_type": "refactor", "platform": "web", "architecture": "react"},
            )
            memory.record_execution(
                "web-1", "test",
                {"ok": True, "exit_code": 0, "diagnostics": []},
            )

            second = memory.start_task("android-1", "refactor Android UI", "android")
            memory.record_cognitive_plan(
                "android-1", "refactor Android UI",
                ["minimal_patch", "test_first"], "minimal_patch",
                context={"task_type": "refactor", "platform": "android", "architecture": "compose"},
            )
            memory.record_execution(
                "android-1", "test",
                {"ok": False, "exit_code": 1, "diagnostics": ["compile failed"]},
            )

            web = memory.meta_learning_context(
                {"task_type": "refactor", "platform": "web", "architecture": "react"}
            )
            android = memory.meta_learning_context(
                {"task_type": "refactor", "platform": "android", "architecture": "compose"}
            )

            self.assertGreater(web["strategy_stats"]["minimal_patch"]["successes"], 0)
            self.assertEqual(web["strategy_stats"]["minimal_patch"]["failures"], 0)
            self.assertEqual(android["strategy_stats"]["minimal_patch"]["successes"], 0)
            self.assertGreater(android["strategy_stats"]["minimal_patch"]["failures"], 0)

    def test_records_complete_autonomous_build_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )

            memory.start_task("app-1", "zbuduj kalkulator", "web")
            memory.record_decision("app-1", "zbuduj kalkulator", "użyj React", [])
            memory.record_changes("app-1", [
                {"path": "src/App.tsx", "content": "x"}
            ])
            memory.record_execution(
                "app-1", "test",
                {"ok": False, "exit_code": 1, "diagnostics": ["test failed"]}
            )
            memory.record_correction(
                "app-1", "test", ["test failed"],
                [{"path": "src/App.tsx", "content": "fixed"}]
            )
            memory.record_execution(
                "app-1", "build",
                {"ok": True, "artifact": "dist", "diagnostics": []}
            )
            memory.record_success("app-1", "web", "verified", "dist")

            events = memory.store.query(agent_id="odyn_orchestrator")
            event_types = [event.event_type for event in events]

            self.assertEqual(
                event_types,
                [
                    "task_started",
                    "coding_decision",
                    "code_change",
                    "test_result",
                    "correction",
                    "build_result",
                    "successful_procedure",
                ],
            )
            self.assertEqual(
                memory.store.query(event_type="successful_procedure")[0].payload["artifact"],
                "dist",
            )


    def test_meta_learning_uses_similarity_weighted_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )
            memory.start_task("web-react", "refactor frontend", "web")
            memory.record_cognitive_plan(
                "web-react", "refactor frontend",
                ["minimal_patch", "test_first"], "minimal_patch",
                context={"task_type": "refactor", "platform": "web", "architecture": "react"},
            )
            memory.record_execution("web-react", "test", {"ok": True, "exit_code": 0, "diagnostics": []})
            memory.start_task("android-react", "refactor mobile frontend", "android")
            memory.record_cognitive_plan(
                "android-react", "refactor mobile frontend",
                ["minimal_patch", "test_first"], "minimal_patch",
                context={"task_type": "refactor", "platform": "android", "architecture": "react"},
            )
            memory.record_execution("android-react", "test", {"ok": False, "exit_code": 1, "diagnostics": ["compile failed"]})

            result = memory.meta_learning_context(
                {"task_type": "refactor", "platform": "web", "architecture": "react"}
            )

            self.assertAlmostEqual(result["strategy_stats"]["minimal_patch"]["successes"], 1.0)
            self.assertAlmostEqual(result["strategy_stats"]["minimal_patch"]["failures"], 0.7)
            self.assertEqual(result["evidence_count"], 2)
            self.assertEqual(result["weighted_evidence"], 1.7)
            self.assertEqual([round(item["similarity"], 2) for item in result["evidence"]], [1.0, 0.7])

    def test_meta_learning_ignores_distant_context_and_cross_task_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = AgentExperienceMemory(
                store=BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            )
            memory.start_task("web-1", "refactor frontend", "web")
            memory.record_cognitive_plan(
                "web-1", "refactor frontend",
                ["minimal_patch", "test_first"], "minimal_patch",
                context={"task_type": "refactor", "platform": "web", "architecture": "react"},
            )
            memory.record_execution("web-1", "test", {"ok": True, "exit_code": 0, "diagnostics": []})
            memory.start_task("android-1", "fix backend", "android")
            memory.record_cognitive_plan(
                "android-1", "fix backend",
                ["minimal_patch", "test_first"], "minimal_patch",
                context={"task_type": "bugfix", "platform": "android", "architecture": "python"},
            )
            memory.record_execution("android-1", "test", {"ok": False, "exit_code": 1, "diagnostics": ["failed"]})

            result = memory.meta_learning_context(
                {"task_type": "refactor", "platform": "web", "architecture": "react"}
            )

            self.assertEqual(result["strategy_stats"]["minimal_patch"]["successes"], 1.0)
            self.assertEqual(result["strategy_stats"]["minimal_patch"]["failures"], 0.0)
            self.assertEqual(result["evidence_count"], 1)
            self.assertEqual(result["ignored_evidence_count"], 1)
            self.assertEqual(result["evidence"][0]["outcome"], "success")



if __name__ == "__main__":
    unittest.main()
