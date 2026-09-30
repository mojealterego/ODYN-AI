import unittest

from odyn_ai.config import LLMConfig
from odyn_ai.core.engine import DualGGUFEngine


class EngineInferencePolicyTests(unittest.TestCase):
    def test_cognitive_overrides_are_used_without_mutating_base_config(self):
        config = LLMConfig(backend="python", temperature=0.65, top_p=0.9)
        engine = DualGGUFEngine.__new__(DualGGUFEngine)
        engine.config = config

        effective = engine.effective_inference_params(
            {"temperature": 0.2, "top_p": 0.65}
        )

        self.assertEqual(effective, {"temperature": 0.2, "top_p": 0.65})
        self.assertEqual(config.temperature, 0.65)
        self.assertEqual(config.top_p, 0.9)

    def test_inference_policy_rejects_invalid_ranges(self):
        engine = DualGGUFEngine.__new__(DualGGUFEngine)
        engine.config = LLMConfig(backend="python")

        with self.assertRaises(ValueError):
            engine.effective_inference_params({"temperature": 2.1})
        with self.assertRaises(ValueError):
            engine.effective_inference_params({"top_p": 0.0})


if __name__ == "__main__":
    unittest.main()
