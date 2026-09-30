import unittest

from odyn_ai.core.orchestrator import AutonomousBuildOrchestrator
from odyn_ai.core.evolution import RoadmapDirective


class SwarmIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_swarm_roadmap_is_fed_into_coding_and_dgm_runs_after_verified_build(self):
        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"package.json": "{}"}}
            def write_file(self, app_id, path, content):
                pass

        class Coding:
            async def apply(self, platform, instruction, files, **kwargs):
                self.instruction = instruction
                updated = dict(files)
                updated["package.json"] = '{"evolved":true}'
                return {
                    "summary": "evolved",
                    "changes": [{"path": "package.json", "content": updated["package.json"]}],
                    "files": updated,
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
                return type("R", (), {"ok": True, "__dict__": {"ok": True}})()

        class Swarm:
            async def prepare_cycle(self, **kwargs):
                return {
                    "roadmap": RoadmapDirective(
                        "1.2.0",
                        ["Add verified MCP adapter"],
                        [],
                        ["https://example.test/evidence"],
                    )
                }

            async def apply_roadmap(self, roadmap, branch, changes):
                self.applied = (roadmap.version, branch, changes)
                return True

        swarm = Swarm()
        coding = Coding()
        result = await AutonomousBuildOrchestrator(
            Apps(), Execution(), coding, GitHub(), swarm=swarm
        ).run(
            "app",
            "dodaj integrację MCP",
            github_repository=None,
        )

        self.assertTrue(result.ok)
        self.assertIn("Add verified MCP adapter", coding.instruction)
        self.assertEqual(swarm.applied[0], "1.2.0")
        self.assertEqual(swarm.applied[1], "odyn-evolution")
        self.assertEqual(swarm.applied[2][0]["path"], "package.json")

    async def test_swarm_dgm_is_not_applied_when_test_fails(self):
        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"package.json": "{}"}}
            def write_file(self, app_id, path, content):
                pass

        class Coding:
            async def apply(self, platform, instruction, files, **kwargs):
                return {"summary": "x", "changes": [], "files": files}

        class Result:
            ok = False
            diagnostics = ["FAIL"]
            exit_code = 1
            artifact = None
            stdout = ""
            stderr = "failure"
            duration_ms = 1

        class Execution:
            async def execute(self, request):
                return Result()

        class GitHub:
            async def commit_files(self, *args, **kwargs):
                raise AssertionError("GitHub must not run after failed test")

        class Swarm:
            async def prepare_cycle(self, **kwargs):
                return {"roadmap": RoadmapDirective("1.2.0", ["change"], [], [])}
            async def apply_roadmap(self, roadmap, branch, changes):
                raise AssertionError("DGM must not run after failed test")

        result = await AutonomousBuildOrchestrator(
            Apps(), Execution(), Coding(), GitHub(), swarm=Swarm()
        ).run("app", "zmień")

        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "test")


if __name__ == "__main__":
    unittest.main()
