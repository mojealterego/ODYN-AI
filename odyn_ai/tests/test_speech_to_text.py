import unittest


class SpeechToTextContractTests(unittest.TestCase):
    def test_transcriber_is_lazy_and_validates_audio(self):
        from odyn_ai.core.speech_to_text import SpeechToText, SpeechToTextError

        service = SpeechToText(model_name="tiny")
        self.assertEqual(service.model_name, "tiny")
        with self.assertRaises(SpeechToTextError):
            service.transcribe_bytes(b"", "audio/webm")
        with self.assertRaises(SpeechToTextError):
            service.transcribe_bytes(b"not-audio", "text/plain")

    def test_api_exposes_transcription_endpoint(self):
        from odyn_ai.api.server import app

        paths = {route.path for route in app.routes}
        self.assertIn("/api/stt/transcribe", paths)

    def test_stt_config_is_environment_driven(self):
        from odyn_ai.config import STTConfig

        cfg = STTConfig()
        self.assertIn(cfg.model, {"tiny", "base", "small", "medium", "large-v3", "turbo"})
        self.assertIn(cfg.device, {"auto", "cpu", "cuda"})
        self.assertIn(cfg.compute_type, {"auto", "int8", "int8_float16", "float16", "float32"})
        self.assertGreater(cfg.max_audio_bytes, 0)


if __name__ == "__main__":
    unittest.main()
