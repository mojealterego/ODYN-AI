import unittest

from odyn_ai.core.coding_agent import CodingAgent


class CodingAgentValidationTests(unittest.TestCase):
    def test_normalizes_valid_json_patch(self):
        class FakeEngine:
            async def stream_chat(self, messages):
                yield '{"summary":"ok","changes":[{"path":"src/App.tsx","content":"export default 1"}]}'

        import asyncio
        result = asyncio.run(
            CodingAgent(FakeEngine()).propose(
                "web", "zmień aplikację", {"src/App.tsx": "x"}
            )
        )
        self.assertEqual(result["changes"][0]["path"], "src/App.tsx")

    def test_forwards_cognitive_inference_policy(self):
        class FakeEngine:
            def __init__(self):
                self.policy = None

            async def stream_chat(self, messages, *, inference_params=None):
                self.policy = inference_params
                yield '{"summary":"policy aware","changes":[]}'

        import asyncio
        engine = FakeEngine()
        result = asyncio.run(
            CodingAgent(engine).propose(
                "web",
                "napraw build",
                {"package.json": "{}"},
                inference_params={"temperature": 0.2, "top_p": 0.65},
            )
        )
        self.assertEqual(result["summary"], "policy aware")
        self.assertEqual(engine.policy, {"temperature": 0.2, "top_p": 0.65})

    def test_rejects_traversal_from_model(self):
        class FakeEngine:
            async def stream_chat(self, messages):
                yield '{"summary":"bad","changes":[{"path":"../x","content":"pwn"}]}'

        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(CodingAgent(FakeEngine()).propose("web", "zmień", {}))

    def test_injects_relevant_memory_context(self):
        class FakeEngine:
            def __init__(self):
                self.messages = None

            async def stream_chat(self, messages):
                self.messages = messages
                yield '{"summary":"memory aware","changes":[]}'

        import asyncio
        engine = FakeEngine()
        result = asyncio.run(
            CodingAgent(engine).propose(
                "web",
                "napraw build",
                {"package.json": "{}"},
                memory_context="Wcześniej build wymagał poprawki package.json.",
            )
        )
        self.assertEqual(result["summary"], "memory aware")
        self.assertIn(
            "Wcześniej build wymagał poprawki package.json.",
            engine.messages[-1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
