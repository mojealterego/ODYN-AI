import unittest

from odyn_ai.core.evolution import (
    AppForgeGenerator,
    DGMUpdateAgent,
    LLMModelMetadata,
    ModelScoutAgent,
    RoadmapDirective,
    TechReconAgent,
    TechReconData,
)


class FakeHF:
    def __init__(self):
        self.queries = []
        self.downloads = []

    def scan_for_obliterate_models(self, limit=5):
        self.queries.append(limit)
        return [LLMModelMetadata("example/obliterate-model", ["obliterate", "gguf"], 12)]

    def download_and_mount_model(self, model_id, filename):
        self.downloads.append((model_id, filename))
        return True


class FakeInternet:
    def __init__(self):
        self.queries = []

    async def search_web(self, query, max_results=5):
        self.queries.append((query, max_results))
        from odyn_ai.core.search import SearchResult
        return [SearchResult("source", "https://example.com", "MCP server evidence")]


class FakeGitLab:
    def __init__(self):
        self.calls = []

    def commit_dgm_mutation(self, branch, commit_message, actions):
        self.calls.append((branch, commit_message, actions))
        return True


class EvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_scout_uses_obliterate_only_and_mounts_discovered_gguf(self):
        hf = FakeHF()
        scout = ModelScoutAgent(hf, internet=FakeInternet())
        result = await scout.execute(limit=3, download=True)

        self.assertEqual(result[0].model_id, "example/obliterate-model")
        self.assertTrue(result[0].is_mounted)
        self.assertEqual(hf.queries, [3])
        self.assertEqual(hf.downloads, [("example/obliterate-model", "obliterate-model-Q4_K_M.gguf")])

    async def test_tech_recon_searches_multiple_web_surfaces(self):
        internet = FakeInternet()
        recon = TechReconAgent(internet)
        result = await recon.execute(["AI agent", "MCP"])

        self.assertEqual(len(result), 2)
        self.assertEqual(len(internet.queries), 2)
        self.assertIn("AI agent", internet.queries[0][0])
        self.assertIn("MCP", internet.queries[1][0])
        self.assertTrue(result[0].mcp_servers_found)

    async def test_dgm_update_sends_gitlab_actions_without_hiding_failure(self):
        gitlab = FakeGitLab()
        agent = DGMUpdateAgent(gitlab)
        roadmap = RoadmapDirective(
            version="1.1.0",
            architecture_changes=["new MCP layer"],
            code_mutations_required=[
                {"action": "update", "file_path": "src/core/mcp.py", "content": "pass"}
            ],
        )

        ok = await agent.execute(roadmap, branch="odyn-evolution")

        self.assertTrue(ok)
        self.assertEqual(gitlab.calls[0][0], "odyn-evolution")
        self.assertEqual(gitlab.calls[0][2][0]["file_path"], "src/core/mcp.py")



    async def test_swarm_roadmap_flows_through_cognitive_coding_test_build_then_gitlab(self):
        from odyn_ai.core.orchestrator import AutonomousBuildOrchestrator

        class Apps:
            def workspace(self, app_id):
                return {"platform": "web", "files": {"app.py": "print('old')"}}

            def write_file(self, app_id, path, content):
                pass

        class Coding:
            async def apply(self, platform, instruction, files, **kwargs):
                updated = dict(files)
                updated["app.py"] = "print('new')"
                return {
                    "summary": "implemented roadmap directive",
                    "changes": [{"path": "app.py", "content": updated["app.py"]}],
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
                raise AssertionError("GitHub commit should be disabled in this integration test")

        class Swarm:
            def __init__(self):
                self.events = []

            async def prepare_cycle(self):
                self.events.append("prepare")
                return {
                    "roadmap": RoadmapDirective(
                        version="1.2.0",
                        architecture_changes=["new MCP adapter"],
                        code_mutations_required=[],
                        evidence=["https://example.com/evidence"],
                    )
                }

            async def apply_roadmap(self, roadmap, branch, changes):
                self.events.append(("apply", branch, changes))
                return True

        swarm = Swarm()
        result = await AutonomousBuildOrchestrator(
            Apps(),
            Execution(),
            Coding(),
            GitHub(),
            swarm=swarm,
        ).run("app-1", "dodaj adapter MCP")

        self.assertTrue(result.ok)
        self.assertEqual(result.stage, "verified")
        self.assertEqual(swarm.events[0], "prepare")
        self.assertEqual(swarm.events[1][0], "apply")
        self.assertEqual(swarm.events[1][1], "odyn-evolution")
        self.assertEqual(swarm.events[1][2], [{"path": "app.py", "content": "print('new')"}])
        self.assertIn("new MCP adapter", result.cognitive_graph["nodes"][0]["content"])

    def test_app_forge_creates_66_apps(self):
        matrix = AppForgeGenerator().generate_application_matrix()
        self.assertEqual(len(matrix["niche_apps"]), 33)
        self.assertEqual(len(matrix["dev_apps"]), 33)
        self.assertIn("game_builder_sdk", matrix)


if __name__ == "__main__":
    unittest.main()
