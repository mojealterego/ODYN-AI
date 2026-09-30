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
        return [SearchResult("source", "https://example.com", "evidence")]


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

    def test_app_forge_creates_66_apps(self):
        matrix = AppForgeGenerator().generate_application_matrix()
        self.assertEqual(len(matrix["niche_apps"]), 33)
        self.assertEqual(len(matrix["dev_apps"]), 33)
        self.assertIn("game_builder_sdk", matrix)


if __name__ == "__main__":
    unittest.main()
