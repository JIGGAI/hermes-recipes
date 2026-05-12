"""Mirrors clawrecipes/src/lib/skill-install.ts behavior."""

from hermes_recipes.skill_install import detect_missing_skills, skill_install_commands


def test_detect_missing_skills_returns_only_absent(tmp_path):
    (tmp_path / "skill-a").mkdir()
    (tmp_path / "skill-b").mkdir()
    missing = detect_missing_skills(tmp_path, ["skill-a", "skill-b", "skill-c"])
    assert missing == ["skill-c"]


def test_detect_missing_skills_empty_list_returns_empty(tmp_path):
    assert detect_missing_skills(tmp_path, []) == []


def test_skill_install_commands_uses_hermes_cli():
    out = skill_install_commands(["foo", "bar"])
    assert any("hermes skills install foo" in line for line in out)
    assert any("hermes skills install bar" in line for line in out)
    assert out[0].startswith("cd ")
