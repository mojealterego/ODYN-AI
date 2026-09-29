import unittest
from pathlib import Path
from unittest.mock import patch
from odyn_ai.config import LLMConfig
from odyn_ai.core.agents import AgentManager
from odyn_ai.core.builders import AppBuilder
from odyn_ai.core.engine import DualGGUFEngine

BASE_DIR = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_supported_backend(self):
        self.assertEqual(LLMConfig(backend="python").backend, "python")

    def test_unknown_backend_rejected(self):
        with self.assertRaises(ValueError):
            LLMConfig(backend="invalid")


class PolishLanguageTests(unittest.TestCase):
    def test_web_ui_is_polish_first(self):
        html = (BASE_DIR / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="pl">', html)
        self.assertIn("Inteligencja lokalna", html)
        self.assertIn("KREATOR AGENTÓW", html)
        self.assertIn("KREATOR APLIKACJI", html)
        self.assertIn("Status silnika", html)
        self.assertNotIn("AGENTS BUILDER", html)
        self.assertNotIn("APP BUILDER", html)
        self.assertNotIn("LOCAL-FIRST INTELLIGENCE", html)

    def test_frontend_status_and_errors_are_polish(self):
        js = (BASE_DIR / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("PODWÓJNY GGUF", js)
        self.assertIn("PYTHON", js)
        self.assertIn("Przetwarzanie…", js)
        self.assertIn("Błąd ODYN AI", js)
        self.assertNotIn("DUAL GGUF", js)
        self.assertNotIn("SPECULATIVE", js)
        self.assertNotIn("Fallback Python", js)
        self.assertNotIn("Builder API", js)
        self.assertIn("Kreator agentów", js)
        self.assertIn("Kreator aplikacji", js)
        self.assertIn("SILNIK", js)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_context_is_injected(self):
        manager = AgentManager()
        fake = type("R", (), {"title": "T", "url": "https://example.test", "snippet": "S"})()
        with patch.object(manager.internet, "search_web", return_value=[fake]):
            result = await manager.preprocess(
                [{"role": "system", "content": "x"}, {"role": "user", "content": "wyszukaj aktualne dane"}],
                "odyn_czarny_kruk",
            )
        self.assertEqual(result[-1]["role"], "user")
        self.assertIn("Źródło 1", result[-2]["content"])


class BuilderTests(unittest.TestCase):
    def test_declarative_app(self):
        app = AppBuilder().create("Test", "Opis", "odyn_glowny")
        self.assertTrue(app["app_id"].startswith("app_"))


class EngineTests(unittest.TestCase):
    def test_auto_without_models_uses_python_fallback(self):
        with patch("odyn_ai.core.engine.MAIN_MODEL_PATH", Path("/missing/main.gguf")), patch(
            "odyn_ai.core.engine.DRAFT_MODEL_PATH", Path("/missing/draft.gguf")
        ), patch("odyn_ai.core.engine.shutil.which", return_value=None):
            engine = DualGGUFEngine(LLMConfig(backend="auto"))
        self.assertEqual(engine.backend, "python")
        self.assertFalse(engine.true_dual_gguf)
