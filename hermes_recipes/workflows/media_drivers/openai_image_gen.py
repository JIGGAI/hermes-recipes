"""OpenAI image generation (DALL-E) driver.

Port of clawrecipes/src/lib/workflows/media-drivers/openai-image-gen.driver.ts.
"""

from pathlib import Path
from typing import Any, Optional

from hermes_recipes.workflows.media_drivers.types import (
    DurationConstraints,
    MediaDriverInvokeOpts,
    MediaDriverResult,
)
from hermes_recipes.workflows.media_drivers.utils import (
    find_skill_dir,
    find_venv_python,
    parse_media_output,
    run_script,
)


class OpenAIImageGen:
    slug = "openai-image-gen"
    media_type = "image"
    display_name = "OpenAI Image Generation (DALL-E)"
    required_env_vars: tuple[str, ...] = ("OPENAI_API_KEY",)
    duration_constraints: Optional[DurationConstraints] = None

    def invoke(self, opts: MediaDriverInvokeOpts) -> MediaDriverResult:
        skill_dir = find_skill_dir(self.slug)
        if skill_dir is None:
            raise FileNotFoundError(f"Skill directory not found for {self.slug}")
        script_path = skill_dir / "generate_image.py"
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")

        runner = find_venv_python(skill_dir)
        size = str((opts.config or {}).get("size") or "1024x1024")

        env = dict(opts.env or {})
        env.setdefault("DALL_E_SIZE", size)

        stdout = run_script(
            runner=runner,
            script=script_path,
            stdin=opts.prompt,
            env=env,
            cwd=opts.output_dir,
            timeout=opts.timeout,
        )

        file_path = parse_media_output(stdout)
        if not file_path:
            raise RuntimeError(
                f"No MEDIA: path found in script output. Output: {stdout}"
            )

        return MediaDriverResult(
            file_path=Path(file_path),
            metadata={
                "skill": self.slug,
                "prompt": opts.prompt,
                "script_output": stdout,
            },
        )
