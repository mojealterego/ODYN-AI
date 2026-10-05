"""Portable, deterministic Skills discovery and loading runtime.

The runtime intentionally handles *procedural guidance* only. Tool execution,
MCP transports, model calls, and Android capabilities remain separate concerns.
No third-party dependency is required.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from typing import Iterable, Mapping


_MAX_SKILL_BYTES = 256 * 1024
_MAX_DESCRIPTION_BYTES = 32 * 1024
_MAX_SKILLS = 512
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class SkillError(ValueError):
    """Base class for invalid or unsafe skill metadata/content."""


class SkillSecurityError(SkillError):
    """Raised when a skill violates a filesystem or content safety boundary."""


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    version: str
    description: str
    instructions: str
    root: Path
    digest: str
    triggers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillMatch:
    skill: Skill
    score: float
    matched_terms: tuple[str, ...]


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise SkillError("SKILL.md must begin with YAML-style frontmatter")
    marker = text.find("\n---\n", 4)
    if marker < 0:
        raise SkillError("SKILL.md frontmatter is not closed")
    values: dict[str, str] = {}
    for raw in text[4:marker].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise SkillError(f"Invalid frontmatter line: {raw!r}")
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in {"name", "version", "description", "triggers"}:
            continue
        values[key] = value
    return values, text[marker + len("\n---\n"):]


def _validate_root(base: Path, candidate: Path) -> Path:
    base = base.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise SkillSecurityError("Skill path escapes the configured skill root") from exc
    return candidate


def load_skill(path: Path, *, skill_root: Path | None = None) -> Skill:
    path = path.resolve()
    if skill_root is not None:
        path = _validate_root(skill_root, path)
    if path.name != "SKILL.md":
        raise SkillError("A skill entry point must be named SKILL.md")
    if not path.is_file():
        raise SkillError(f"Skill file does not exist: {path}")
    if path.stat().st_size > _MAX_SKILL_BYTES:
        raise SkillSecurityError("SKILL.md exceeds the maximum supported size")

    text = path.read_text(encoding="utf-8")
    meta, instructions = _frontmatter(text)
    name = meta.get("name", "").strip()
    version = meta.get("version", "").strip() or "0.0.0"
    description = meta.get("description", "").strip()
    if not _SAFE_NAME.fullmatch(name):
        raise SkillError("Skill name must match the safe lowercase identifier format")
    if not description or len(description) > 4096:
        raise SkillError("Skill description is required and must be <= 4096 characters")

    triggers = tuple(t.strip().lower() for t in meta.get("triggers", "").split(",") if t.strip())
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Skill(name, version, description, instructions.strip(), path.parent, digest, triggers)


def discover_skills(skill_root: Path) -> tuple[Skill, ...]:
    """Discover skills deterministically, ignoring hidden directories/files."""
    root = skill_root.resolve()
    if not root.is_dir():
        return ()
    candidates = [p for p in root.glob("*/SKILL.md") if not any(part.startswith(".") for part in p.parts)]
    if len(candidates) > _MAX_SKILLS:
        raise SkillSecurityError("Skill directory exceeds the maximum supported skill count")
    skills = [load_skill(p, skill_root=root) for p in sorted(candidates, key=lambda x: x.parent.name)]
    return tuple(skills)


def select_skills(query: str, skills: Iterable[Skill], *, limit: int = 3) -> tuple[SkillMatch, ...]:
    """Select skills using deterministic lexical relevance; never executes tools."""
    if limit < 1:
        return ()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,63}", query.lower()))
    matches: list[SkillMatch] = []
    for skill in skills:
        haystack = " ".join((skill.name, skill.description, *skill.triggers)).lower()
        terms = tuple(sorted(token for token in tokens if token in haystack))
        trigger_hits = sum(1 for trigger in skill.triggers if trigger and trigger in query.lower())
        score = (len(terms) / max(len(tokens), 1)) + min(trigger_hits * 0.5, 1.0)
        if score > 0:
            matches.append(SkillMatch(skill, min(score, 1.0), terms))
    matches.sort(key=lambda m: (-m.score, m.skill.name))
    return tuple(matches[:limit])


def compose_instructions(matches: Iterable[SkillMatch]) -> str:
    """Compose a bounded instruction bundle with explicit skill provenance."""
    blocks: list[str] = []
    for match in matches:
        blocks.append(
            f"## Skill: {match.skill.name} (v{match.skill.version})\n"
            f"<!-- skill-sha256: {match.skill.digest} -->\n"
            f"{match.skill.instructions}"
        )
    return "\n\n".join(blocks)


class SkillRegistry:
    """Small immutable-by-default registry suitable for repeated Android requests."""

    def __init__(self, skills: Iterable[Skill] = ()) -> None:
        self._skills: dict[str, Skill] = {skill.name: skill for skill in skills}

    @classmethod
    def from_directory(cls, skill_root: Path) -> "SkillRegistry":
        return cls(discover_skills(skill_root))

    def all(self) -> tuple[Skill, ...]:
        return tuple(self._skills[name] for name in sorted(self._skills))

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def select(self, query: str, *, limit: int = 3) -> tuple[SkillMatch, ...]:
        return select_skills(query, self._skills.values(), limit=limit)


def manifest(skills: Iterable[Skill]) -> tuple[Mapping[str, str], ...]:
    """Return a stable, UI/API-safe manifest without exposing instructions."""
    return tuple(
        {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "digest": skill.digest,
        }
        for skill in sorted(skills, key=lambda item: item.name)
    )
