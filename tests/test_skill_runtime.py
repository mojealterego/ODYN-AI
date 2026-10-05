from pathlib import Path
import tempfile
import unittest

from hermes_cli.skill_runtime import (
    SkillError,
    SkillRegistry,
    SkillSecurityError,
    compose_instructions,
    discover_skills,
    load_skill,
    manifest,
)


def write_skill(root: Path, name: str, *, description: str = "Android agent skill", triggers: str = "android, agent") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        "version: 1.2.3\n"
        f"description: {description}\n"
        f"triggers: {triggers}\n"
        "---\n\n# Instructions\nUse the narrow tool boundary.\n",
        encoding="utf-8",
    )
    return path


class SkillRuntimeTests(unittest.TestCase):
    def test_discovery_is_deterministic_and_manifest_hides_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            write_skill(root, "zeta", triggers="vision")
            write_skill(root, "alpha", triggers="android")
            skills = discover_skills(root)
            self.assertEqual([skill.name for skill in skills], ["alpha", "zeta"])
            self.assertEqual(manifest(skills)[0]["name"], "alpha")
            self.assertNotIn("instructions", manifest(skills)[0])

    def test_selection_prefers_trigger_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            write_skill(root, "android-agent", triggers="android, device")
            write_skill(root, "vision", triggers="image, vision")
            registry = SkillRegistry.from_directory(root)
            matches = registry.select("configure android device permissions")
            self.assertTrue(matches)
            self.assertEqual(matches[0].skill.name, "android-agent")

    def test_composition_contains_provenance_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            write_skill(root, "alpha")
            skill = load_skill(root / "alpha" / "SKILL.md", skill_root=root)
            selected = SkillRegistry((skill,)).select("android agent")
            text = compose_instructions(selected)
            self.assertIn("## Skill: alpha", text)
            self.assertIn(f"skill-sha256: {skill.digest}", text)

    def test_rejects_unsafe_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            bad = root / "Bad Name"
            bad.mkdir(parents=True)
            path = bad / "SKILL.md"
            path.write_text("---\nname: Bad Name\ndescription: invalid\n---\n", encoding="utf-8")
            with self.assertRaises(SkillError):
                load_skill(path, skill_root=root)

    def test_rejects_skill_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "skills"
            root.mkdir()
            outside = base / "SKILL.md"
            outside.write_text("---\nname: escape\ndescription: bad\n---\n", encoding="utf-8")
            with self.assertRaises(SkillSecurityError):
                load_skill(outside, skill_root=root)


if __name__ == "__main__":
    unittest.main()
