#!/usr/bin/env python3
"""Validate repository Skills as deterministic, auditable bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from hermes_cli.skill_runtime import SkillError, SkillSecurityError, discover_skills

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|client[_-]?secret|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"),
)
_REQUIRED_HEADINGS = ("# ", "## Goal", "## Workflow", "## Security", "## Stop conditions")


def validate(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        skills = discover_skills(root)
    except (SkillError, SkillSecurityError) as exc:
        return [{"severity": "error", "path": str(root), "message": str(exc)}]

    names: set[str] = set()
    for skill in skills:
        path = skill.root / "SKILL.md"
        if skill.name in names:
            findings.append({"severity": "error", "path": str(path), "message": f"Duplicate skill name: {skill.name}"})
        names.add(skill.name)
        text = path.read_text(encoding="utf-8")
        for heading in _REQUIRED_HEADINGS:
            if heading not in text:
                findings.append({"severity": "error", "path": str(path), "message": f"Missing required section: {heading}"})
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"severity": "error", "path": str(path), "message": "Potential credential/secret detected"})
        for directory in ("references", "assets", "scripts"):
            candidate = skill.root / directory
            if candidate.is_symlink():
                findings.append({"severity": "error", "path": str(candidate), "message": "Skill resource directory must not be a symlink"})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="skills", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = validate(args.root)
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2, sort_keys=True))
    else:
        if not findings:
            print(f"Skills validation passed: {len(discover_skills(args.root))} skill(s)")
        for finding in findings:
            print(f"{finding['severity'].upper()}: {finding['path']}: {finding['message']}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
