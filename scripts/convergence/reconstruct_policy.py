from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath


class MigrationClass(str, Enum):
    KEEP = "KEEP"
    PORT = "PORT"
    REWRITE = "REWRITE"
    UPSTREAM_REPLACED = "UPSTREAM_REPLACED"
    PLUGIN = "PLUGIN"
    ARCHIVE = "ARCHIVE"
    DELETE = "DELETE"


class ConflictResolution(str, Enum):
    ODYN_REVIEW_REQUIRED = "ODYN_REVIEW_REQUIRED"
    UPSTREAM_REVIEW_REQUIRED = "UPSTREAM_REVIEW_REQUIRED"


_KEEP_PREFIXES = (
    "odyn_ai/cognition/",
)

_PORT_PREFIXES = (
    "android/",
    "odyn_ai/",
    "agent/cognition/",
    "tests/agent/cognition/",
)

_PORT_EXACT = {
    "agent/cognitive_gate.py",
    "agent/tool_plan_validation.py",
    "agent/tool_dispatch_helpers.py",
    "run_agent.py",
    "tests/agent/test_untrusted_tool_results.py",
    "agent/turn_candidate_review.py",
    "agent/turn_request_assembly.py",
    "agent/conversation_loop.py",
}

_ARCHIVE_PREFIXES = (
    "docs/legacy/",
    "legacy/",
)

_UPSTREAM_OWNED_PREFIXES = (
    "agent/",
    "apps/desktop/",
    "gateway/",
    "hermes_cli/",
    "plugins/",
    "plugin-catalog/",
    "skills/",
    "optional-skills/",
    "optional-mcps/",
    "web/",
    "ui-tui/",
    "tui_gateway/",
    "cron/",
    "pm/",
    "evals/",
    "locales/",
)


def _normalise(path: str) -> str:
    value = PurePosixPath(path).as_posix().lstrip("./")
    if value in {"", "."} or value.startswith("../"):
        raise ValueError(f"invalid repository path: {path!r}")
    return value


def classify_path(path: str) -> MigrationClass:
    value = _normalise(path)
    if value in _PORT_EXACT:
        return MigrationClass.PORT
    if value.startswith(_KEEP_PREFIXES):
        return MigrationClass.KEEP
    if value.startswith(_ARCHIVE_PREFIXES):
        return MigrationClass.ARCHIVE
    if value.startswith(_PORT_PREFIXES):
        return MigrationClass.PORT
    if value.startswith(_UPSTREAM_OWNED_PREFIXES):
        return MigrationClass.UPSTREAM_REPLACED
    return MigrationClass.REWRITE


def resolve_conflict(path: str) -> ConflictResolution:
    classification = classify_path(path)
    if classification in {MigrationClass.KEEP, MigrationClass.PORT}:
        return ConflictResolution.ODYN_REVIEW_REQUIRED
    return ConflictResolution.UPSTREAM_REVIEW_REQUIRED
