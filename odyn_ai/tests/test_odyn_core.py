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

    def test_viking_nord_theme_uses_cold_north_palette(self):
        css = (BASE_DIR / "ui" / "nord.css").read_text(encoding="utf-8")
        self.assertIn("--obsydian:", css)
        self.assertIn("--stal:", css)
        self.assertIn("--stare-zloto:", css)
        self.assertIn("--runiczny-blekit:", css)
        self.assertIn("background: radial-gradient", css)
        self.assertIn("text-transform: uppercase", css)

    def test_frontend_status_and_errors_are_polish(self):
        html = (BASE_DIR / "ui" / "index.html").read_text(encoding="utf-8")
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
        self.assertIn("Tryb bez kodu", js)
        self.assertIn("Tryb kodowy", js)
        self.assertIn("Kod agenta", js)
        self.assertIn("SILNIK", html)
        self.assertIn("WEB", html)
        self.assertIn("ANDROID NATIVE", html)
        self.assertIn("ODYN IDE", html)
        self.assertIn("Eksplorator", html)
        self.assertIn("Edytor kodu", html)
        self.assertIn("Terminal", html)
        self.assertIn("Podgląd", html)
        self.assertIn("Tryb No Code", js)
        self.assertIn("Tryb Code", js)
        self.assertIn("/api/apps/", js)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def test_no_code_agent_has_builder_mode(self):
        manager = AgentManager()
        agent = manager.create("analityk", "Analityk", "Analizuj dane.", can_search=True)
        self.assertEqual(agent.mode, "no_code")
        self.assertEqual(agent.code, "")

    def test_code_agent_stores_source_without_executing_it(self):
        manager = AgentManager()
        source = "def agent(ctx):\n    return ctx"
        agent = manager.create_code("koder_test", "Koder testowy", source)
        self.assertEqual(agent.mode, "code")
        self.assertEqual(agent.code, source)
        self.assertEqual(agent.prompt, "Koder testowy")

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

    def test_app_builder_supports_web_and_native_android_modes(self):
        builder = AppBuilder()
        web = builder.create("Web", "Opis", "odyn_glowny", platform="web", mode="no_code")
        android = builder.create("Android", "Opis", "odyn_glowny", platform="android", mode="code")
        self.assertEqual(web["platform"], "web")
        self.assertEqual(web["mode"], "no_code")
        self.assertEqual(android["platform"], "android")
        self.assertEqual(android["mode"], "code")
        with self.assertRaises(ValueError):
            builder.create("Desktop", "Opis", "odyn_glowny", platform="desktop")

    def test_workspace_has_ide_project_files(self):
        builder = AppBuilder()
        app = builder.create("Projekt", "Opis", "odyn_glowny", platform="android", mode="code")
        workspace = builder.workspace(app["app_id"])
        self.assertEqual(workspace["platform"], "android")
        self.assertIn("settings.gradle.kts", workspace["files"])
        self.assertIn("app/src/main/AndroidManifest.xml", workspace["files"])

    def test_workspace_can_write_and_read_file(self):
        builder = AppBuilder()
        app = builder.create("Projekt", "Opis", "odyn_glowny", platform="web", mode="code")
        builder.write_file(app["app_id"], "src/App.tsx", "export default function App() { return null }")
        self.assertIn("src/App.tsx", builder.read_file(app["app_id"])["files"])
        self.assertIn("export default", builder.read_file(app["app_id"])["files"])

class EngineTests(unittest.TestCase):
    def test_auto_without_models_uses_python_fallback(self):
        with patch("odyn_ai.core.engine.MAIN_MODEL_PATH", Path("/missing/main.gguf")), patch(
            "odyn_ai.core.engine.DRAFT_MODEL_PATH", Path("/missing/draft.gguf")
        ), patch("odyn_ai.core.engine.shutil.which", return_value=None):
            engine = DualGGUFEngine(LLMConfig(backend="auto"))
        self.assertEqual(engine.backend, "python")
        self.assertFalse(engine.true_dual_gguf)
