import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ui" / "app.js"
REQUIREMENTS = ROOT / "requirements.txt"

class NativeSttContractTests(unittest.TestCase):
    def test_frontend_contains_media_recorder_upload_flow(self):
        js = APP.read_text(encoding="utf-8")
        for token in ("MediaRecorder", "/api/stt/transcribe", "FormData", "mediaRecorder.ondataavailable", "mediaRecorder.onstop", "audio/webm"):
            self.assertIn(token, js)

    def test_native_stt_does_not_auto_submit_chat(self):
        js = APP.read_text(encoding="utf-8")
        section = js[js.index("function initNativeVoiceInput"):js.index("function initVoiceInput")]
        self.assertNotIn("send();", section)
        self.assertIn("userInput.value", section)

    def test_backend_stt_dependency_is_declared(self):
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertRegex(requirements, r"(?m)^faster-whisper[<>=~!].*$")

if __name__ == "__main__":
    unittest.main()
