import tempfile
import unittest
from pathlib import Path

from nexus_core.memory import BitemporalMemoryNode
from nexus_core.reasoning.cognitive_engine import CognitiveEngine
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
            instructions = []
            inference_policies = []

            async def apply(self, platform, instruction, files, **kwargs):
                self.instructions.append(instruction)
                self.inference_policies.append(kwargs.get("inference_params"))
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
            coding = Coding()
            orchestrator = AutonomousBuildOrchestrator(
                Apps(), Execution(), coding, GitHub(), memory,
                max_corrections=1, cognitive_engine=CognitiveEngine()
            )
            result = await orchestrator.run("app-1", "zbuduj kalkulator")

            self.assertTrue(result.ok)

            events = store.query(agent_id="odyn_orchestrator")
            event_types = [event.event_type for event in events]
            self.assertEqual(
                event_types,
                [
                    "task_started",
                    "cognitive_plan",
                    "cognitive_strategy",
                    "cognitive_strategy",
                    "cognitive_strategy",
                    "coding_decision",
                    "test_result",
                    "reflexion",
                    "correction",
                    "coding_decision",
                    "code_change",
                    "test_retry_result",
                    "build_result",
                    "successful_procedure",
                ],
            )

            plan = events[1]
            strategies = events[2:5]
            decision = events[5]
            failure = events[6]
            reflexion = events[7]
            correction = events[8]
            correction_decision = events[9]
            correction_change = events[10]
            retry = events[11]
            build = events[12]
            success = events[13]

            self.assertEqual(plan.payload["selected_strategy"], "test_first")
            self.assertEqual({item.payload["strategy"] for item in strategies}, {"minimal_patch", "test_first", "architecture"})
            self.assertEqual(decision.payload["cognitive_strategy"], "test_first")
            self.assertEqual(correction_decision.event_type, "coding_decision")
            self.assertEqual(correction_change.event_type, "code_change")
            self.assertIn("test_first", coding.instructions[0])
            self.assertEqual(coding.inference_policies[0], {"temperature": 0.7, "top_p": 0.9})
            self.assertEqual(len(coding.inference_policies), 2)
            self.assertLessEqual(coding.inference_policies[1]["temperature"], 0.7)
            self.assertEqual(reflexion.payload["failed_execution_id"], failure.id)
            self.assertEqual(result.cognitive_graph["selected_strategy"], "test_first")
            self.assertTrue(any(node["kind"] == "selected_strategy" for node in result.cognitive_graph["nodes"]))

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
            task_id = events[0].id
            self.assertEqual(
                [item.id for item in store.related(task_id, "planned_by")],
                [events[1].id],
            )
            self.assertEqual(
                [item.id for item in store.related(task_id, "decided_by")],
                [events[5].id],
            )
            self.assertEqual(
                [item.id for item in store.related(reflexion.id, "reflects_on")],
                [failure.id],
            )


if __name__ == "__main__":
    unittest.main()
