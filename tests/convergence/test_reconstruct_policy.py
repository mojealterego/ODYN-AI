from __future__ import annotations

import pytest

from scripts.convergence.reconstruct_policy import (
    ConflictResolution,
    MigrationClass,
    classify_path,
    resolve_conflict,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("odyn_ai/cognition/cognitive_engine.py", MigrationClass.KEEP),
        ("odyn_ai/cognition/dual_model_engine.py", MigrationClass.KEEP),
        ("agent/cognition/review_cycle.py", MigrationClass.PORT),
        ("agent/turn_candidate_review.py", MigrationClass.PORT),
        ("agent/turn_request_assembly.py", MigrationClass.PORT),
        ("agent/conversation_loop.py", MigrationClass.PORT),
        ("agent/cognitive_gate.py", MigrationClass.PORT),
        ("agent/tool_plan_validation.py", MigrationClass.PORT),
        ("agent/tool_dispatch_helpers.py", MigrationClass.PORT),
        ("run_agent.py", MigrationClass.PORT),
        ("android/app/src/main/java/com/mobilefork/hermesagent/MainActivity.kt", MigrationClass.PORT),
        ("hermes_android/runtime_identity.py", MigrationClass.PORT),
        ("tests/hermes_android/test_runtime_env.py", MigrationClass.PORT),
        ("scripts/prepare_android_native_libs.py", MigrationClass.PORT),
        ("constraints-android.txt", MigrationClass.PORT),
        ("tools/android_device_tool.py", MigrationClass.PORT),
        ("tests/agent/cognition/test_review_cycle.py", MigrationClass.PORT),
        ("tests/agent/test_untrusted_tool_results.py", MigrationClass.PORT),
        ("docs/legacy/old-ui.md", MigrationClass.ARCHIVE),
        ("apps/desktop/src/main.ts", MigrationClass.UPSTREAM_REPLACED),
    ],
)
def test_classification_preserves_odyn_owned_surfaces(path: str, expected: MigrationClass) -> None:
    assert classify_path(path) is expected


@pytest.mark.parametrize(
    "path",
    [
        "odyn_ai/cognition/hermes_execution.py",
        "agent/cognition/review_cycle.py",
        "agent/turn_candidate_review.py",
        "agent/conversation_loop.py",
        "agent/cognitive_gate.py",
        "agent/tool_plan_validation.py",
        "agent/tool_dispatch_helpers.py",
        "run_agent.py",
        "android/app/src/main/AndroidManifest.xml",
        "hermes_android/runtime_identity.py",
        "scripts/check_android_litertlm_version.py",
    ],
)
def test_critical_conflicts_never_silently_discard_odyn(path: str) -> None:
    assert resolve_conflict(path) is ConflictResolution.ODYN_REVIEW_REQUIRED


def test_upstream_owned_conflicts_default_to_upstream_and_are_recorded() -> None:
    assert resolve_conflict("gateway/platforms/api_server.py") is ConflictResolution.UPSTREAM_REVIEW_REQUIRED
