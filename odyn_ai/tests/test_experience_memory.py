import tempfile
import unittest
from pathlib import Path

from nexus_core.memory import BitemporalMemoryNode
from odyn_ai.core.experience_memory import AgentExperienceMemory


class ExperienceMemoryTests(unittest.TestCase):
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
