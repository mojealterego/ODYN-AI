import unittest
from dataclasses import dataclass

from odyn_ai.core.orchestrator import AutonomousBuildOrchestrator


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_stops_before_build_when_tests_fail(self):
        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"package.json": "{}"}}
            def write_file(self, app_id, path, content):
                pass

        class Coding:
            async def apply(self, platform, instruction, files):
                return {"changes": [], "files": files}

        class Result:
            def __init__(self, ok):
                self.ok = ok
                self.diagnostics = ["failed"]
                self.__dict__.update({"exit_code": 1, "artifact": None})

        class Execution:
            calls = []
            async def execute(self, request):
                self.calls.append(request.action)
                return Result(False)

        class GitHub:
            async def commit_files(self, *args, **kwargs):
                raise AssertionError("GitHub nie może być wywołany po błędzie testów.")

        execution = Execution()
        result = await AutonomousBuildOrchestrator(Apps(), execution, Coding(), GitHub()).run("app", "zmień")
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "test")
        self.assertEqual(execution.calls, ["test"])


if __name__ == "__main__":
    unittest.main()
