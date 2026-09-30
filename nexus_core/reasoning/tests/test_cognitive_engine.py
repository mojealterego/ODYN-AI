from __future__ import annotations

import unittest

from nexus_core.reasoning.cognitive_engine import CognitiveEngine


class FakeCritic:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate_and_critique(self, task: str, output: str) -> str:
        self.calls += 1
        return "FAIL: improve" if self.calls == 1 else "PASS"

    def correct(self, task: str, output: str, critique: str) -> str:
        return output + " [corrected]"


class CognitiveEngineTests(unittest.TestCase):
    def test_cosine_similarity(self) -> None:
        engine = CognitiveEngine()
        self.assertAlmostEqual(engine.jepa_evaluate_embedding([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(engine.jepa_evaluate_embedding([1, 0], [0, 1]), 0.0)
        self.assertEqual(engine.jepa_evaluate_embedding([0, 0], [1, 0]), 0.0)

    def test_embedding_evaluation(self) -> None:
        result = CognitiveEngine(evaluation_threshold=0.9).evaluate_embedding([1, 0], [0.95, 0.1])
        self.assertTrue(result.passed)
        self.assertLess(result.distance, 0.1)

    def test_graph_and_fitness(self) -> None:
        engine = CognitiveEngine()
        root = engine.add_thought("root", "task")
        branches = engine.branch(root, ["A", "B", "C"])
        self.assertEqual(set(engine.thought_graph.successors(root)), set(branches))
        self.assertEqual(
            engine.ab_mcts_step(root, ["slow", "fast"], lambda _, a: 0.9 if a == "fast" else 0.2),
            "fast",
        )

    def test_reflexion(self) -> None:
        result = CognitiveEngine(max_reflections=2).reflexion_loop("task", "bad", FakeCritic())
        self.assertEqual(result, "bad [corrected]")

    def test_modulation(self) -> None:
        engine = CognitiveEngine()
        calm = engine.cognitive_modulation(0.1)
        stress = engine.cognitive_modulation(0.9)
        self.assertGreater(calm["temperature"], stress["temperature"])
        self.assertGreater(calm["top_p"], stress["top_p"])

    def test_validation(self) -> None:
        engine = CognitiveEngine()
        with self.assertRaises(ValueError):
            engine.jepa_evaluate_embedding([], [1])
        with self.assertRaises(ValueError):
            engine.jepa_evaluate_embedding([1], [1, 2])
        with self.assertRaises(ValueError):
            engine.cognitive_modulation(1.1)


if __name__ == "__main__":
    unittest.main()
