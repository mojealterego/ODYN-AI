"""Media orchestration for long-form video composition.

The module keeps generation backends behind interfaces and uses MoviePy only
for composition. Generated media is never executed as code by this component.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any


class MediaCompositionError(RuntimeError):
    """Raised when a media composition cannot be started safely."""


class MediaOrchestrator:
    def __init__(self, workspace_dir: str = "/tmp/nexus_media") -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def generate_music_and_audio(self, prompt: str) -> str:
        """Return the integration target for an external audio generator."""
        if not prompt or not prompt.strip():
            raise ValueError("prompt jest wymagany.")
        return str(self.workspace_dir / "generated_ambient_track.mp3")

    def initialize_generation_models(
        self,
        reference_image_path: str | None = None,
    ) -> dict[str, Any]:
        """Describe the generation-model initialization contract."""
        reference: str | None = None
        if reference_image_path is not None:
            path = Path(reference_image_path).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Obraz referencyjny nie istnieje: {path}")
            reference = str(path)

        return {
            "status": "ready",
            "reference_image": reference,
            "provider": "external_generation_adapter",
        }

    def render_configuration(self) -> dict[str, Any]:
        """Return the controlled rendering policy used by composition."""
        return {
            "concatenate_method": "compose",
            "fps": 24,
            "codec": "libx264",
            "threads": max(1, multiprocessing.cpu_count()),
            "preset": "ultrafast",
        }

    def _validate_output_filename(self, output_filename: str) -> Path:
        if not output_filename or not output_filename.strip():
            raise ValueError("output_filename jest wymagany.")

        candidate = Path(output_filename)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("output_filename musi wskazywać plik w workspace_dir.")

        output_path = (self.workspace_dir / candidate).resolve()
        if self.workspace_dir not in output_path.parents:
            raise ValueError("output_filename wychodzi poza workspace_dir.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    @staticmethod
    def _load_moviepy() -> tuple[Any, Any]:
        try:
            from moviepy import VideoFileClip, concatenate_videoclips
        except ImportError as exc:
            raise MediaCompositionError(
                "MoviePy nie jest zainstalowane. Zainstaluj zależność media."
            ) from exc
        return VideoFileClip, concatenate_videoclips

    def compose_long_feature_video(
        self,
        clip_paths: list[str],
        output_filename: str,
    ) -> str:
        """Compose many short clips into one long-form video."""
        output_path = self._validate_output_filename(output_filename)

        valid_paths = [
            Path(path).expanduser().resolve()
            for path in clip_paths
            if Path(path).expanduser().is_file()
        ]
        if not valid_paths:
            raise MediaCompositionError("brak poprawnych wejść MP4.")

        VideoFileClip, concatenate_videoclips = self._load_moviepy()
        clips: list[Any] = []
        final_video: Any | None = None

        try:
            clips = [VideoFileClip(str(path)) for path in valid_paths]
            final_video = concatenate_videoclips(clips, method="compose")

            config = self.render_configuration()
            final_video.write_videofile(
                str(output_path),
                fps=config["fps"],
                codec=config["codec"],
                threads=config["threads"],
                preset=config["preset"],
                logger=None,
            )
            return f"Wideo wyrenderowane i skompilowane: {output_path}"
        except Exception as exc:
            raise MediaCompositionError(
                f"Awaria renderowania wideo: {exc}"
            ) from exc
        finally:
            if final_video is not None:
                try:
                    final_video.close()
                except Exception:
                    pass
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass
