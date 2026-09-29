import unittest
from pathlib import Path
from unittest.mock import patch
from odyn_ai.config import LLMConfig
from odyn_ai.core.agents import AgentManager
from odyn_ai.core.builders import AppBuilder
from odyn_ai.core.engine import DualGGUFEngine

class ConfigTests(unittest.TestCase):
    def test_supported_backend(self):
        self.assertEqual(LLMConfig(backend="python").backend, "python")
    def test_unknown_backend_rejected(self):
        with self.assertRaises(ValueError): LLMConfig(backend="invalid")

class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_context_is_injected(self):
        manager = AgentManager()
        fake = type("R", (), {"title":"T","url":"https://example.test","snippet":"S"})()
        with patch.object(manager.internet, "search_web", return_value=[fake]):
            result = await manager.preprocess([{"role":"system","content":"x"},{"role":"user","content":"wyszukaj aktualne dane"}], "odyn_czarny_kruk")
        self.assertEqual(result[-1]["role"], "user")
        self.assertIn("Źródło 1", result[-2]["content"])

class BuilderTests(unittest.TestCase):
    def test_declarative_app(self):
        app = AppBuilder().create("Test", "Opis", "odyn_glowny")
        self.assertTrue(app["app_id"].startswith("app_"))

class EngineTests(unittest.TestCase):
    def test_auto_without_models_uses_python_fallback(self):
        with patch("odyn_ai.core.engine.MAIN_MODEL_PATH", Path("/missing/main.gguf")), patch("odyn_ai.core.engine.DRAFT_MODEL_PATH", Path("/missing/draft.gguf")), patch("odyn_ai.core.engine.shutil.which", return_value=None):
            engine = DualGGUFEngine(LLMConfig(backend="auto"))
        self.assertEqual(engine.backend, "python")
        self.assertFalse(engine.true_dual_gguf)
