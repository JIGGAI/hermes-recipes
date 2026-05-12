"""Covers hermes_recipes/workflows/media_drivers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hermes_recipes.workflows.media_drivers.openai_image_gen import OpenAIImageGen
from hermes_recipes.workflows.media_drivers.registry import (
    get_all_drivers,
    get_driver,
    is_driver_available,
    register_driver,
    reset_registry,
)
from hermes_recipes.workflows.media_drivers.types import (
    DurationConstraints,
    MediaDriverInvokeOpts,
    MediaDriverResult,
    parse_duration,
)
from hermes_recipes.workflows.media_drivers.utils import (
    find_skill_dir,
    find_venv_python,
    parse_media_output,
)


def test_parse_duration_handles_various_inputs():
    assert parse_duration(None) == "15"
    assert parse_duration({}) == "15"
    assert parse_duration({"duration": "5s"}) == "5"
    assert parse_duration({"duration": "20"}) == "20"
    assert parse_duration({"duration": 30}) == "30"
    assert parse_duration({"duration": "bad"}) == "15"
    assert parse_duration({"duration": -5}) == "15"


def test_parse_media_output_extracts_path():
    assert parse_media_output("MEDIA:/tmp/out.png\nDONE") == "/tmp/out.png"
    assert parse_media_output("no media here") == ""
    assert parse_media_output("") == ""


def test_find_skill_dir_searches_hermes_roots(tmp_path):
    hermes_home = tmp_path / ".hermes"
    skill = hermes_home / "skills" / "openai-image-gen"
    skill.mkdir(parents=True)
    found = find_skill_dir(
        "openai-image-gen", roots=[hermes_home / "skills"]
    )
    assert found == skill


def test_find_skill_dir_returns_none_when_missing(tmp_path):
    assert find_skill_dir("missing-slug", roots=[tmp_path]) is None


def test_find_venv_python_falls_back_to_system_python(tmp_path):
    assert find_venv_python(tmp_path) == "python3"


def test_find_venv_python_uses_venv_if_present(tmp_path):
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    venv_py = venv_bin / "python"
    venv_py.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    assert find_venv_python(tmp_path) == str(venv_py)


def test_registry_get_driver_and_availability():
    reset_registry()
    driver = get_driver("openai-image-gen")
    assert driver is not None
    assert driver.slug == "openai-image-gen"
    assert is_driver_available("openai-image-gen", {"OPENAI_API_KEY": "sk-123"})
    assert not is_driver_available("openai-image-gen", {})
    assert not is_driver_available("openai-image-gen", {"OPENAI_API_KEY": "   "})


def test_registry_register_extra_driver():
    reset_registry()
    initial = len(get_all_drivers())

    class FakeDriver:
        slug = "fake"
        media_type = "image"
        display_name = "Fake"
        required_env_vars: tuple = ()
        duration_constraints = None

        def invoke(self, opts):
            return MediaDriverResult(file_path=Path("/tmp/fake.png"))

    register_driver(FakeDriver())
    assert len(get_all_drivers()) == initial + 1
    assert get_driver("fake") is not None
    reset_registry()


def test_duration_constraints_dataclass_fields():
    dc = DurationConstraints(min_seconds=5, max_seconds=15, default_seconds=10, step_seconds=5)
    assert dc.min_seconds == 5
    assert dc.step_seconds == 5


def test_openai_image_gen_invoke_calls_run_script(tmp_path):
    skill_dir = tmp_path / "openai-image-gen"
    skill_dir.mkdir()
    (skill_dir / "generate_image.py").write_text("print('ok')\n", encoding="utf-8")

    captured: dict = {}

    def fake_run_script(**kwargs):
        captured.update(kwargs)
        return "MEDIA:/tmp/result.png\nDONE"

    with patch(
        "hermes_recipes.workflows.media_drivers.openai_image_gen.find_skill_dir",
        return_value=skill_dir,
    ), patch(
        "hermes_recipes.workflows.media_drivers.openai_image_gen.run_script",
        side_effect=fake_run_script,
    ):
        driver = OpenAIImageGen()
        opts = MediaDriverInvokeOpts(
            prompt="a cat",
            output_dir=tmp_path,
            timeout=30.0,
            config={"size": "512x512"},
            env={"OPENAI_API_KEY": "sk-test"},
        )
        result = driver.invoke(opts)

    assert result.file_path == Path("/tmp/result.png")
    assert result.metadata["skill"] == "openai-image-gen"
    assert captured["stdin"] == "a cat"
    assert captured["env"]["DALL_E_SIZE"] == "512x512"
    assert captured["env"]["OPENAI_API_KEY"] == "sk-test"


def test_openai_image_gen_invoke_raises_when_skill_missing():
    with patch(
        "hermes_recipes.workflows.media_drivers.openai_image_gen.find_skill_dir",
        return_value=None,
    ):
        driver = OpenAIImageGen()
        with pytest.raises(FileNotFoundError, match="Skill directory not found"):
            driver.invoke(
                MediaDriverInvokeOpts(prompt="x", output_dir=Path("/tmp"), timeout=1.0)
            )
