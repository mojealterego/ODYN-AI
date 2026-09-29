import unittest

from odyn_ai.core.orchestrator import AutonomousBuildOrchestrator


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_attempts_one_autonomous_test_correction(self):
        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"package.json": "{}"}}

            def write_file(self, app_id, path, content):
                pass

        class Coding:
            calls = 0

            async def apply(self, platform, instruction, files):
                self.calls += 1
                if self.calls == 1:
                    return {"summary": "pierwsza próba", "changes": [], "files": files}
                corrected = dict(files)
                corrected["package.json"] = '{"fixed":true}'
                return {
                    "summary": "korekta testów",
                    "changes": [{"path": "package.json", "content": corrected["package.json"]}],
                    "files": corrected,
                }

        class Result:
            def __init__(self, ok):
                self.ok = ok
                self.diagnostics = ["failed"] if not ok else []
                self.exit_code = 1 if not ok else 0
                self.artifact = None
                self.stdout = ""
                self.stderr = ""
                self.duration_ms = 1

        class Execution:
            calls = []

            async def execute(self, request):
                self.calls.append(request.action)
                return Result(len(self.calls) > 1)

        class GitHub:
            async def commit_files(self, *args, **kwargs):
                raise AssertionError("GitHub nie może być wywołany po błędzie testów.")

        execution = Execution()
        result = await AutonomousBuildOrchestrator(
            Apps(), execution, Coding(), GitHub(), max_corrections=1
        ).run("app", "zmień")

        self.assertTrue(result.ok)
        self.assertEqual(result.stage, "verified")
        self.assertEqual(execution.calls, ["test", "test", "build"])

    async def test_successful_pipeline_records_memory(self):
        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"package.json": "{}"}}

            def write_file(self, app_id, path, content):
                pass

        class Coding:
            async def apply(self, platform, instruction, files):
                return {
                    "summary": "gotowe",
                    "changes": [],
                    "files": files,
                }

        class Result:
            def __init__(self, action):
                self.ok = True
                self.diagnostics = []
                self.exit_code = 0
                self.artifact = "dist" if action == "build" else None
                self.stdout = "PASS"
                self.stderr = ""
                self.duration_ms = 1

        class Execution:
            async def execute(self, request):
                return Result(request.action)

        class GitHub:
            async def commit_files(self, *args, **kwargs):
                raise AssertionError("GitHub nie jest częścią tego testu.")

        class Memory:
            def __init__(self):
                self.events = []

            class Episode:
                def __init__(self, event_id):
                    self.id = event_id

            def start_task(self, *args):
                self.events.append("task_started")
                return self.Episode(1)

            def recall(self, *args, **kwargs):
                return ""

            def record_decision(self, *args):
                self.events.append("coding_decision")
                return self.Episode(2)

            def record_changes(self, *args):
                self.events.append("code_change")
                return []

            def record_execution(self, app_id, stage, result):
                self.events.append(stage)
                return self.Episode(3)

            def record_success(self, *args, **kwargs):
                self.events.append("successful_procedure")
                return self.Episode(4)

        memory = Memory()
        result = await AutonomousBuildOrchestrator(
            Apps(), Execution(), Coding(), GitHub(), memory
        ).run("app", "zbuduj")

        self.assertTrue(result.ok)
        self.assertIn("task_started", memory.events)
        self.assertIn("coding_decision", memory.events)
        self.assertIn("test", memory.events)
        self.assertIn("build", memory.events)
        self.assertIn("successful_procedure", memory.events)


if __name__ == "__main__":
    unittest.main()
