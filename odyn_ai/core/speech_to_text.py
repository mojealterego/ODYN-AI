from __future__ import annotations

from pathlib import Path
import os
import tempfile
from threading import Lock

ALLOWED_MIME_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
}
MIME_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/x-m4a": ".m4a",
}


class SpeechToTextError(RuntimeError):
    pass


class SpeechToText:
    """Local Whisper transcription with lazy model loading."""

    def __init__(
        self,
        model_name: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        max_audio_bytes: int = 25 * 1024 * 1024,
        language: str = "pl",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.max_audio_bytes = max_audio_bytes
        self.language = language
        self._model = None
        self._model_lock = Lock()

    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise SpeechToTextError(
                        "Backend lokalnego STT nie jest zainstalowany. "
                        "Zainstaluj profil ODYN STT z faster-whisper."
                    ) from exc
                try:
                    device = self.device
                    compute_type = self.compute_type
                    if device == "auto":
                        device = "cuda"
                        try:
                            import ctranslate2
                            if ctranslate2.get_cuda_device_count() < 1:
                                device = "cpu"
                        except Exception:
                            device = "cpu"
                    if compute_type == "auto":
                        compute_type = "float16" if device == "cuda" else "int8"
                    self._model = WhisperModel(
                        self.model_name,
                        device=device,
                        compute_type=compute_type,
                    )
                except Exception as exc:
                    raise SpeechToTextError(
                        f"Nie udało się uruchomić lokalnego modelu STT: {exc}"
                    ) from exc
        return self._model

    def transcribe_bytes(self, audio: bytes, content_type: str) -> str:
        if not audio:
            raise SpeechToTextError("Plik audio jest pusty.")
        if len(audio) > self.max_audio_bytes:
            raise SpeechToTextError(
                f"Plik audio przekracza limit {self.max_audio_bytes // (1024 * 1024)} MB."
            )
        content_type = content_type.split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_MIME_TYPES:
            raise SpeechToTextError(
                "Nieobsługiwany format audio. Dozwolone: WebM, OGG, WAV, MP3, MP4/M4A."
            )

        suffix = MIME_EXTENSIONS[content_type]
        path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="odyn-stt-",
                suffix=suffix,
                delete=False,
            ) as handle:
                handle.write(audio)
                path = Path(handle.name)

            model = self._load_model()
            segments, _ = model.transcribe(
                str(path),
                language=self.language,
                task="transcribe",
                vad_filter=True,
                beam_size=5,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if not text:
                raise SpeechToTextError("Nie rozpoznano mowy w nagraniu.")
            return text
        except SpeechToTextError:
            raise
        except Exception as exc:
            raise SpeechToTextError(f"Transkrypcja STT nie powiodła się: {exc}") from exc
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
