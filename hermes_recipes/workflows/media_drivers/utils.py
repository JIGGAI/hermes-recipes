"""Driver utilities — skill lookup, script execution, output parsing.

Port of clawrecipes/src/lib/workflows/media-drivers/utils.ts. The OpenClaw
version wraps subprocess calls in a bash + python3 -c indirection because
it can't import ``child_process`` directly — Python doesn't have that
restriction, so this version uses ``subprocess.run`` directly.

Skill search roots target the Hermes home (``~/.hermes/skills/`` and similar),
not the OpenClaw home.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Iterable, Optional


def default_hermes_home() -> Path:
    return Path.home() / ".hermes"


def hermes_skill_roots(hermes_home: Optional[Path] = None) -> tuple[Path, ...]:
    home = hermes_home or default_hermes_home()
    return (
        home / "skills",
        home / "recipes" / "workspace" / "skills",
        home / "recipes" / "workspace",
    )


def find_skill_dir(
    slug: str, *, roots: Optional[Iterable[Path]] = None
) -> Optional[Path]:
    candidates = roots if roots is not None else hermes_skill_roots()
    for root in candidates:
        candidate = Path(root) / slug
        if candidate.is_dir():
            return candidate
    return None


def find_venv_python(skill_dir: Path | str) -> str:
    venv_python = Path(skill_dir) / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else "python3"


_MEDIA_RE = re.compile(r"^MEDIA:(.+)$", re.MULTILINE)


def parse_media_output(stdout: str) -> str:
    m = _MEDIA_RE.search(stdout or "")
    return m.group(1).strip() if m else ""


def run_script(
    *,
    runner: str,
    script: Path | str,
    args: Optional[list[str]] = None,
    stdin: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    cwd: Path | str,
    timeout: float,
) -> str:
    """Run *script* with *runner* under *cwd*, returning stdout.

    Raises ``RuntimeError`` (with stdout + stderr context) on non-zero exit.
    """
    merged_env = dict(os.environ)
    if env:
        merged_env.update({k: str(v) for k, v in env.items()})
    merged_env.setdefault("MEDIA_OUTPUT_DIR", str(cwd))

    try:
        result = subprocess.run(
            [runner, str(script), *(args or [])],
            input=stdin or "",
            text=True,
            capture_output=True,
            cwd=str(cwd),
            env=merged_env,
            timeout=max(1.0, float(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        raise RuntimeError(
            f"Script execution timed out after {timeout}s"
            + (f"\n--- stdout ---\n{stdout.strip()}" if stdout else "")
            + (f"\n--- stderr ---\n{stderr.strip()}" if stderr else "")
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"Script execution failed with exit code {result.returncode}"
            + (f"\n--- stdout ---\n{result.stdout.strip()}" if result.stdout else "")
            + (f"\n--- stderr ---\n{result.stderr.strip()}" if result.stderr else "")
        )
    return (result.stdout or "").strip()
