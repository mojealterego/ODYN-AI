from __future__ import annotations

import asyncio
import json
import unittest

from nexus_core.engine.cognitive_inference import CognitiveInferencePipeline, CriticResult
from nexus_core.engine.llm_dual_engine import DualModelEngine


class FakeModel:
    def __init__(self, model_path: str, **kwargs):
        self.model_path = model_path
        self.calls = []

    def create_completion(self, prompt: str, **kwargs):
        self.calls.append(prompt)
        if self.model_path == "primary.gguf":
            if "CORRECT" in prompt:
                return {"choices": [{"text": "corrected answer"}]}
            return {"choices": [{"text": "draft answer"}]}
        return {"choices": [{"text": json.dumps({
            "decision": "accept",
            "confidence": 0.95,
            "safety": 0.99,
            "logic": 0.94,
            "reason": "ok"
        })}]}


class RejectThenCorrectModel(FakeModel):
    critic_calls = 0

    def create_completion(self, prompt: str, **kwargs):
        self.calls.append(prompt)
        if self.model_path == "primary.gguf":
            return {"choices": [{"text": "corrected answer" if "CORRECT" in prompt else "unsafe draft"}]}
        self.critic_calls += 1
        decision = "reject" if self.critic_calls == 1 else "accept"
        return {"choices": [{"text": json.dumps({
            "decision": decision,
            "confidence": 0.92,
            "safety": 0.10 if decision == "reject" else 0.98,
            "logic": 0.80 if decision == "reject" else 0.95,
            "reason": "unsafe" if decision == "reject" else "corrected"
        })}]}


class CognitiveInferenceTests(unittest.TestCase):
    def test_structured_critic_result_is_parsed(self) -> None:
        result = CriticResult.from_text(
            '{"decision":"reject","confidence":0.8,"safety":0.2,"logic":0.7,"reason":"unsafe"}'
        )
        self.assertTrue(result.rejected)
        self.assertEqual(result.reason, "unsafe")
        self.assertAlmostEqual(result.confidence, 0.8)

    def test_dual_engine_feeds_structured_critic_into_cognitive_gate(self) -> None:
        engine = DualModelEngine("primary.gguf", "critic.gguf", llama_factory=FakeModel)
        pipeline = CognitiveInferencePipeline(engine)

        result = asyncio.run(
            pipeline.run(
                "Zrób zadanie",
                strategies=("direct", "research"),
                fitness_fn=lambda _node, action: 1.0 if action == "research" else 0.5,
                state_embedding=(1.0, 0.0),
                target_embedding=(1.0, 0.0),
            )
        )

        self.assertEqual(result.output, "draft answer")
        self.assertFalse(result.gate.rejected)
        self.assertEqual(result.decision.selected_strategy, "research")
        self.assertIn("[TEMPORAL EVIDENCE]", result.context)

    def test_rejected_draft_is_corrected_and_re_evaluated(self) -> None:
        engine = DualModelEngine(
            "primary.gguf", "critic.gguf", llama_factory=RejectThenCorrectModel
        )
        pipeline = CognitiveInferencePipeline(engine)

        result = asyncio.run(
            pipeline.run(
                "Zrób zadanie",
                strategies=("direct",),
                fitness_fn=lambda _node, _action: 1.0,
                max_reflections=1,
            )
        )

        self.assertEqual(result.output, "corrected answer")
        self.assertFalse(result.gate.rejected)
        self.assertEqual(result.reflections, 1)


if __name__ == "__main__":
    unittest.main()
