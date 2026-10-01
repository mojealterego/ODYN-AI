from __future__ import annotations

import asyncio
import unittest

from nexus_core.engine.llm_dual_engine import DualModelEngine


class FakeLlama:
    instances = []

    def __init__(self, model_path: str, **kwargs):
        self.model_path = model_path
        self.kwargs = kwargs
        self.prompts = []
        FakeLlama.instances.append(self)

    def create_completion(self, prompt: str, **kwargs):
        self.prompts.append((prompt, kwargs))
        if self.model_path == "primary.gguf":
            return {"choices": [{"text": "bezpieczna odpowiedź"}]}
        return {"choices": [{"text": "PASS"}]}


class DualModelEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeLlama.instances.clear()

    def test_loads_primary_and_critic_with_independent_contexts(self) -> None:
        engine = DualModelEngine(
            "primary.gguf",
            "critic.gguf",
            llama_factory=FakeLlama,
            primary_context=8192,
            critic_context=2048,
        )

        asyncio.run(engine.start())

        self.assertEqual({item.model_path for item in FakeLlama.instances}, {"primary.gguf", "critic.gguf"})
        self.assertEqual(FakeLlama.instances[0].kwargs["n_ctx"], 8192)
        self.assertEqual(FakeLlama.instances[1].kwargs["n_ctx"], 2048)
        self.assertEqual(FakeLlama.instances[0].kwargs["n_gpu_layers"], -1)
        self.assertEqual(FakeLlama.instances[1].kwargs["n_gpu_layers"], -1)

    def test_primary_draft_is_accepted_after_critic_passes(self) -> None:
        engine = DualModelEngine("primary.gguf", "critic.gguf", llama_factory=FakeLlama)

        result = asyncio.run(engine.generate_with_adversarial_gating("Napisz odpowiedź."))

        self.assertEqual(result, "bezpieczna odpowiedź")
        self.assertEqual(engine.last_evaluation, "PASS")
        self.assertFalse(engine.last_rejected)
        self.assertEqual(FakeLlama.instances[1].prompts[0][0].splitlines()[0], "SYSTEM: Oceń odpowiedź.")

    def test_critic_rejection_never_returns_primary_draft(self) -> None:
        class RejectingCritic(FakeLlama):
            def create_completion(self, prompt: str, **kwargs):
                self.prompts.append((prompt, kwargs))
                if self.model_path == "primary.gguf":
                    return {"choices": [{"text": "draft"}]}
                return {"choices": [{"text": "ODRZUCONO: błąd krytyczny"}]}

        engine = DualModelEngine("primary.gguf", "critic.gguf", llama_factory=RejectingCritic)

        result = asyncio.run(engine.generate_with_adversarial_gating("task"))

        self.assertTrue(engine.last_rejected)
        self.assertEqual(engine.last_gate_reason, "critic_rejected")
        self.assertNotEqual(result, "draft")
        self.assertIn("Adversarial Gating", result)

    def test_generation_runs_off_event_loop(self) -> None:
        class SlowLlama(FakeLlama):
            def create_completion(self, prompt: str, **kwargs):
                import time
                time.sleep(0.05)
                return super().create_completion(prompt, **kwargs)

        async def scenario() -> None:
            engine = DualModelEngine("primary.gguf", "critic.gguf", llama_factory=SlowLlama)
            ticks = 0

            async def ticker() -> None:
                nonlocal ticks
                for _ in range(5):
                    await asyncio.sleep(0.01)
                    ticks += 1

            await asyncio.gather(
                engine.generate_with_adversarial_gating("task"),
                ticker(),
            )
            self.assertGreaterEqual(ticks, 3)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
