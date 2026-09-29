import unittest

from odyn_ai.config import SPECIALIST_PROFILES, SYSTEM_PROMPTS
from odyn_ai.core.agents import AgentManager


class SpecialistProfileTests(unittest.TestCase):
    def test_central_registry_contains_required_specialists(self):
        self.assertEqual(
            set(SPECIALIST_PROFILES),
            {"prawo", "osint", "web_builder", "game_builder"},
        )
        for profile_id, profile in SPECIALIST_PROFILES.items():
            self.assertTrue(profile["name"])
            self.assertTrue(profile["prompt"])
            self.assertIn(profile["prompt_key"], SYSTEM_PROMPTS)
            self.assertIsInstance(profile["can_search"], bool)
            self.assertIn(profile["mode"], {"no_code", "code"})

    def test_specialist_profiles_are_available_from_agent_manager(self):
        manager = AgentManager()
        agents = {item["id"]: item for item in manager.list_agents()}
        for profile_id, profile in SPECIALIST_PROFILES.items():
            self.assertIn(profile_id, agents)
            self.assertEqual(agents[profile_id]["name"], profile["name"])
            self.assertEqual(agents[profile_id]["can_search"], profile["can_search"])
            self.assertEqual(agents[profile_id]["mode"], profile["mode"])

    def test_specialist_prompts_are_domain_specific(self):
        self.assertIn("prawo", SYSTEM_PROMPTS["law"].lower())
        self.assertIn("osint", SYSTEM_PROMPTS["osint"].lower())
        self.assertIn("web", SYSTEM_PROMPTS["web_builder"].lower())
        self.assertIn("game", SYSTEM_PROMPTS["game_builder"].lower())


if __name__ == "__main__":
    unittest.main()
