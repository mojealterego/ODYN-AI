import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "ui" / "index.html"
APP = ROOT / "ui" / "app.js"


class VoiceUiContractTests(unittest.TestCase):
    def test_chat_contains_accessible_voice_button(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('id="voice-btn"', html)
        self.assertIn('type="button"', html)
        self.assertIn('aria-label="Włącz dyktowanie"', html)
        self.assertIn('id="voice-status"', html)
        self.assertIn('placeholder="Napisz polecenie lub użyj głosu', html)

    def test_voice_button_is_integrated_with_chat_form(self):
        html = INDEX.read_text(encoding="utf-8")
        chat_form_start = html.index('<form id="chat-form">')
        chat_form_end = html.index("</form>", chat_form_start)
        chat_form = html[chat_form_start:chat_form_end]
        self.assertIn('id="voice-btn"', chat_form)
        self.assertIn('id="user-input"', chat_form)
        self.assertIn('id="send-btn"', chat_form)

    def test_app_initializes_polish_speech_recognition(self):
        js = APP.read_text(encoding="utf-8")
        for token in (
            "SpeechRecognition",
            "webkitSpeechRecognition",
            "recognition.lang = \"pl-PL\"",
            "recognition.interimResults = true",
            "recognition.onresult",
            "recognition.onerror",
            "recognition.onend",
            'voice-btn',
        ):
            self.assertIn(token, js)

    def test_voice_input_does_not_auto_submit_chat(self):
        js = APP.read_text(encoding="utf-8")
        voice_section = js[js.index("function initVoiceInput"):js.index("function exportReport")]
        self.assertNotIn("send();", voice_section)
        self.assertIn("userInput.value", voice_section)


if __name__ == "__main__":
    unittest.main()
