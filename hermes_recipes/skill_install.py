"""Detect missing skills and build install hints.

Port of clawrecipes/src/lib/skill-install.ts. The original generates
``npx clawhub install <skill>`` commands for missing skills. On Hermes the
equivalent is ``hermes skills install <skill>`` (Hermes Skills Hub).
"""

from pathlib import Path
from typing import Iterable


def detect_missing_skills(install_dir: Path | str, skills: Iterable[str]) -> list[str]:
    base = Path(install_dir)
    missing: list[str] = []
    for slug in skills:
        if not (base / slug).exists():
            missing.append(slug)
    return missing


def skill_install_commands(skills: Iterable[str], *, workspace_env: str = "HERMES_RECIPES_WORKSPACE") -> list[str]:
    """Render install hints for the user.

    Hermes does not have a one-shot ``cd workspace && install`` flow like
    clawhub; instead, ``hermes skills install`` resolves the install root
    itself. We still emit a ``cd`` line for parity / scripting clarity.
    """
    return [
        f'cd "${workspace_env}"  # path under $HOME/.hermes/recipes/workspace by default',
        *[f"hermes skills install {slug}" for slug in skills],
    ]
