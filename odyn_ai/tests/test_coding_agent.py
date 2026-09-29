import unittest

from odyn_ai.core.coding_agent import CodingAgent


class CodingAgentValidationTests(unittest.TestCase):
    def test_normalizes_valid_json_patch(self):
        class FakeEngine:
            async def stream_chat(self, messages):
                yield '{"summary":"ok","changes":[{"path":"src/App.tsx","content":"export default 1"}]}'

        import asyncio
        result = asyncio.run(CodingAgent(FakeEngine()).propose("web", "zmień aplikację", {"src/App.tsx": "x"}))
        self.assertEqual(result["changes"][0]["path"], "src/App.tsx")

    def test_rejects_traversal_from_model(self):
        class FakeEngine:
            async def stream_chat(self, messages):
                yield '{"summary":"bad","changes":[{"path":"../x","content":"pwn"}]}'

        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(CodingAgent(FakeEngine()).propose("web", "zmień", {}))


if __name__ == "__main__":
    unittest.main()
