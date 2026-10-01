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


if __name__ == "__main__":
    unittest.main()
