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

    def test_build_plan_creates_task_strategy_and_selection_graph(self) -> None:
        engine = CognitiveEngine()
        task = engine.add_thought("task", "build app")
        plan = engine.plan_build(
            "build app",
            ["minimal_patch", "test_first", "architecture"],
            lambda _, action: {"minimal_patch": 0.4, "test_first": 0.9, "architecture": 0.2}[action],
            parent_id=task,
        )
        self.assertEqual(plan["selected_strategy"], "test_first")
        snapshot = engine.snapshot()
        kinds = [node["kind"] for node in snapshot["nodes"]]
        self.assertIn("cognitive_plan", kinds)
        self.assertIn("selected_strategy", kinds)
        self.assertTrue(
            any(
                edge["source"] == task and edge["relation"] == "derives"
                for edge in snapshot["edges"]
            )
        )

    def test_history_aware_plan_applies_historical_strategy_bias(self) -> None:
        engine = CognitiveEngine()
        plan = engine.plan_build(
            "build app",
            ["minimal_patch", "test_first"],
            lambda _, action: 0.80,
            history_context={
                "strategy_stats": {
                    "minimal_patch": {"successes": 0, "failures": 2},
                    "test_first": {"successes": 2, "failures": 0},
                },
                "historical_snapshot": {"transaction_at": "2026-04-01T00:00:00+00:00"},
            },
        )

        self.assertEqual(plan["selected_strategy"], "test_first")
        self.assertTrue(plan["history_aware"])
        self.assertGreater(plan["historical_bias"]["test_first"], plan["historical_bias"]["minimal_patch"])
        snapshot = engine.snapshot()
        cognitive_plan = next(node for node in snapshot["nodes"] if node["kind"] == "cognitive_plan")
        self.assertEqual(
            cognitive_plan["metadata"]["historical_snapshot"]["transaction_at"],
            "2026-04-01T00:00:00+00:00",
        )

    def test_meta_learning_bias_is_contextual_and_bounded(self) -> None:
        engine = CognitiveEngine()
        plan = engine.plan_build(
            "refactor web UI",
            ["minimal_patch", "test_first"],
            lambda _, action: 0.80,
            history_context={
                "strategy_stats": {
                    "minimal_patch": {"successes": 4, "failures": 0, "attempts": 4},
                    "test_first": {"successes": 0, "failures": 4, "attempts": 4},
                },
                "context": {"platform": "web", "task_type": "refactor", "architecture": "react"},
                "evidence_count": 4,
            },
        )
        self.assertEqual(plan["selected_strategy"], "minimal_patch")
        self.assertLessEqual(plan["historical_bias"]["minimal_patch"], 0.25)
        self.assertGreater(plan["historical_bias"]["minimal_patch"], 0.0)

    def test_meta_learning_ignores_single_outlier(self) -> None:
        engine = CognitiveEngine()
        plan = engine.plan_build(
            "task",
            ["minimal_patch", "test_first"],
            lambda _, action: 0.80 if action == "test_first" else 0.81,
            history_context={
                "strategy_stats": {
                    "minimal_patch": {"successes": 0, "failures": 1},
                    "test_first": {"successes": 0, "failures": 0},
                },
                "evidence_count": 1,
            },
        )
        self.assertEqual(plan["historical_bias"]["minimal_patch"], 0.0)


    def test_adversarial_gate_combines_critic_and_embedding(self) -> None:
        engine = CognitiveEngine(evaluation_threshold=0.8)
        result = engine.adversarial_gate(
            "task", "output", critic_result="PASS",
            state_embedding=[1, 0], target_embedding=[0.95, 0.1],
        )
        self.assertTrue(result.passed)
        self.assertFalse(result.rejected)
        self.assertAlmostEqual(result.similarity, engine.jepa_evaluate_embedding([1, 0], [0.95, 0.1]))

    def test_adversarial_gate_rejects_unsafe_critic_even_with_good_embedding(self) -> None:
        engine = CognitiveEngine(evaluation_threshold=0.8)
        result = engine.adversarial_gate(
            "task", "output", critic_result="UNSAFE: reject",
            state_embedding=[1, 0], target_embedding=[1, 0],
        )
        self.assertFalse(result.passed)
        self.assertTrue(result.rejected)
        self.assertEqual(result.reason, "critic_rejected")

    def test_graph_rejects_cycle_edges(self) -> None:
        engine = CognitiveEngine()
        root = engine.add_thought("root", "task")
        child = engine.add_thought("child", "step", parent_id=root)
        with self.assertRaises(ValueError):
            engine.connect_thought(child, root)


    def test_decision_cycle_has_stable_id_and_phase_trace(self) -> None:
        engine = CognitiveEngine()
        cycle = engine.decision_cycle(
            "refactor web UI",
            ["minimal_patch", "test_first"],
            lambda _, action: 0.9 if action == "test_first" else 0.8,
            context={"platform": "web", "task_type": "refactor", "architecture": "react"},
            history_context={
                "strategy_stats": {
                    "test_first": {"successes": 2, "failures": 0},
                    "minimal_patch": {"successes": 0, "failures": 2},
                },
                "evidence_count": 4,
            },
            critic_result="PASS",
            state_embedding=[1, 0],
            target_embedding=[1, 0],
        )
        self.assertTrue(cycle.decision_id)
        self.assertEqual(cycle.selected_strategy, "test_first")
        self.assertEqual(
            cycle.phases,
            ("context", "candidate_strategies", "historical_evidence",
             "got_evaluation", "adversarial_gate", "strategy_selection"),
        )
        self.assertEqual(cycle.status, "selected")
        snapshot = engine.snapshot()
        cycle_nodes = [
            node for node in snapshot["nodes"]
            if node["metadata"].get("decision_id") == cycle.decision_id
        ]
        self.assertGreaterEqual(len(cycle_nodes), 3)

    def test_decision_cycle_rejects_before_strategy_selection(self) -> None:
        engine = CognitiveEngine()
        cycle = engine.decision_cycle(
            "unsafe task",
            ["minimal_patch", "test_first"],
            lambda _, action: 1.0,
            context={"platform": "web", "task_type": "general", "architecture": "react"},
            history_context={"evidence_count": 2},
            critic_result="UNSAFE: reject",
            state_embedding=[1, 0],
            target_embedding=[1, 0],
        )
        self.assertTrue(cycle.rejected)
        self.assertIsNone(cycle.selected_strategy)
        self.assertEqual(cycle.status, "rejected")


    def test_decision_cycle_can_be_closed_with_outcome(self) -> None:
        engine = CognitiveEngine()
        cycle = engine.decision_cycle(
            "build app",
            ["minimal_patch", "test_first"],
            lambda _, action: 1.0,
            context={"platform": "web", "task_type": "feature", "architecture": "react"},
            critic_result="PASS",
        )
        outcome_id = engine.record_decision_outcome(
            cycle, outcome="verified", execution_id=123, correction=True
        )
        node = engine.get_thought(outcome_id)
        self.assertEqual(node.kind, "decision_outcome")
        self.assertEqual(node.metadata["decision_id"], cycle.decision_id)
        self.assertTrue(node.metadata["correction"])

    def test_reflexion(self) -> None:
        engine = CognitiveEngine(max_reflections=2)
        result = engine.reflexion_loop("task", "bad", FakeCritic())
        self.assertEqual(result, "bad [corrected]")
        snapshot = engine.snapshot()
        self.assertTrue(any(edge["relation"] == "derives" for edge in snapshot["edges"]))

    def test_bounded_adversarial_search(self) -> None:
        engine = CognitiveEngine()
        root = engine.add_thought("root", "choose")
        scores = {
            ("root", "safe"): 9.0,
            ("root", "fast"): 10.0,
            ("safe", "bad"): 2.0,
            ("safe", "good"): 8.0,
            ("fast", "bad"): 1.0,
            ("fast", "good"): 0.0,
        }

        def fitness(node: str, action: str) -> float:
            branch = "root" if node == root else engine.get_thought(node).content
            return scores[(branch, action)]

        self.assertEqual(
            engine.ab_mcts_step(
                root,
                ["safe", "fast"],
                fitness,
                depth=2,
                opponent_actions_fn=lambda _: ["bad", "good"],
            ),
            "safe",
        )

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
