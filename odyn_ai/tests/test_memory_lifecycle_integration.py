import tempfile
import unittest
from pathlib import Path

from nexus_core.memory import BitemporalMemoryNode
from odyn_ai.core.experience_memory import AgentExperienceMemory
from odyn_ai.core.orchestrator import AutonomousBuildOrchestrator


class MemoryLifecycleIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_persists_failure_correction_and_success_graph(self):
        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"package.json": "{}"}}

            def write_file(self, app_id, path, content):
                pass

        class Coding:
            calls = 0

            async def apply(self, platform, instruction, files, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return {"summary": "pierwsza implementacja", "changes": [], "files": files}
                updated = dict(files)
                updated["package.json"] = '{"fixed":true}'
                return {
                    "summary": "korekta błędu testów",
                    "changes": [{"path": "package.json", "content": updated["package.json"]}],
                    "files": updated,
                }

        class Result:
            def __init__(self, ok, action):
                self.ok = ok
                self.diagnostics = [] if ok else ["npm test: failure"]
                self.exit_code = 0 if ok else 1
                self.artifact = "dist" if action == "build" and ok else None
                self.stdout = "PASS" if ok else ""
                self.stderr = "" if ok else "assertion failed"
                self.duration_ms = 5

        class Execution:
            calls = 0

            async def execute(self, request):
                self.calls += 1
                return Result(self.calls > 1, request.action)

        class GitHub:
            async def commit_files(self, *args, **kwargs):
                raise AssertionError("GitHub nie powinien być częścią tego testu.")

        with tempfile.TemporaryDirectory() as tmp:
            store = BitemporalMemoryNode(str(Path(tmp) / "memory.db"))
            memory = AgentExperienceMemory(store=store)
            result = await AutonomousBuildOrchestrator(
                Apps(), Execution(), Coding(), GitHub(), memory, max_corrections=1
            ).run("app-1", "zbuduj kalkulator")

            self.assertTrue(result.ok)

            events = store.query(agent_id="odyn_orchestrator")
            event_types = [event.event_type for event in events]
            self.assertEqual(
                event_types,
                [
                    "task_started",
                    "coding_decision",
                    "test_result",
                    "correction",
                    "test_result",
                    "build_result",
                    "successful_procedure",
                ],
            )

            failure = events[2]
            correction = events[3]
            retry = events[4]
            build = events[5]
            success = events[6]

            self.assertEqual(failure.payload["ok"], False)
            self.assertEqual(correction.payload["failed_execution_id"], failure.id)
            self.assertEqual(success.payload["source_execution_id"], build.id)
            self.assertEqual(
                [item.payload for item in store.related(correction.id, "corrects")],
                [failure.payload],
            )
            self.assertEqual(
                [item.payload for item in store.related(success.id, "verified_by")],
                [build.payload],
            )
            self.assertEqual(
                [item.id for item in store.related(task_id := events[0].id, "decided_by")],
                [events[1].id],
            )
            self.assertEqual(
                [item.id for item in store.related(events[3].id, "corrects")],
                [events[2].id],
            )
            self.assertEqual(
                [item.id for item in store.related(events[3].id, "corrects")],
                [failure.id],
            )


if __name__ == "__main__":
    unittest.main()
