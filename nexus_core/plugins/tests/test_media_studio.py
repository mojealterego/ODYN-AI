from __future__ import annotations

import pytest

from nexus_core.plugins.media_studio import MediaOrchestrator, MediaCompositionError


def test_rejects_empty_clip_list(tmp_path) -> None:
    studio = MediaOrchestrator(str(tmp_path))

    with pytest.raises(MediaCompositionError, match="brak poprawnych"):
        studio.compose_long_feature_video([], "feature.mp4")


def test_rejects_missing_clip_paths(tmp_path) -> None:
    studio = MediaOrchestrator(str(tmp_path))

    with pytest.raises(MediaCompositionError, match="brak poprawnych"):
        studio.compose_long_feature_video(
            [str(tmp_path / "missing.mp4")],
            "feature.mp4",
        )


def test_rejects_unsafe_output_name(tmp_path) -> None:
    studio = MediaOrchestrator(str(tmp_path))

    with pytest.raises(ValueError, match="output_filename"):
        studio.compose_long_feature_video([], "../feature.mp4")


def test_render_configuration_uses_compose_and_all_cpu_threads(tmp_path) -> None:
    studio = MediaOrchestrator(str(tmp_path))
    config = studio.render_configuration()

    assert config["concatenate_method"] == "compose"
    assert config["threads"] >= 1
    assert config["preset"] == "ultrafast"
    assert config["codec"] == "libx264"


def test_generation_models_report_reference_image_without_executing_model(
    tmp_path,
) -> None:
    studio = MediaOrchestrator(str(tmp_path))
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"image")

    result = studio.initialize_generation_models(str(reference))

    assert result["status"] == "ready"
    assert result["reference_image"] == str(reference)


def test_music_bridge_returns_deterministic_workspace_path(tmp_path) -> None:
    studio = MediaOrchestrator(str(tmp_path))

    result = studio.generate_music_and_audio("ambient cinematic")

    assert result.endswith("generated_ambient_track.mp3")
    assert str(tmp_path) in result
