"""Locate a recipe markdown file by id.

Port of the discovery half of clawrecipes/src/lib/recipes.ts. The OpenClaw
plugin walks the workspace recipes dir then the built-in bundled recipes; the
Hermes port is general — callers pass an ordered list of recipe roots.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class LoadedRecipe:
    recipe_id: str
    path: Path
    md: str


def load_recipe_md(
    recipe_id: str, *, recipe_dirs: Iterable[Path | str]
) -> LoadedRecipe:
    """Return ``LoadedRecipe`` for the first ``<dir>/<recipe_id>.md`` that exists.

    Raises ``FileNotFoundError`` (with the dirs that were searched) when not found.
    """
    tried: list[Path] = []
    for raw_dir in recipe_dirs:
        candidate = Path(raw_dir) / f"{recipe_id}.md"
        tried.append(candidate)
        if candidate.exists():
            return LoadedRecipe(
                recipe_id=recipe_id,
                path=candidate,
                md=candidate.read_text(encoding="utf-8"),
            )
    paths = "\n  - ".join(str(p) for p in tried) or "(none)"
    raise FileNotFoundError(
        f"Recipe not found: {recipe_id}. Searched:\n  - {paths}"
    )


def list_recipe_ids(recipe_dirs: Iterable[Path | str]) -> list[str]:
    """Return the union of recipe ids discoverable in the given dirs."""
    seen: set[str] = set()
    out: list[str] = []
    for raw_dir in recipe_dirs:
        d = Path(raw_dir)
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if entry.suffix != ".md":
                continue
            rid = entry.stem
            if rid in seen:
                continue
            seen.add(rid)
            out.append(rid)
    return out


def find_recipe_path(
    recipe_id: str, *, recipe_dirs: Iterable[Path | str]
) -> Optional[Path]:
    """Same lookup as :func:`load_recipe_md` but returns ``None`` instead of raising."""
    for raw_dir in recipe_dirs:
        candidate = Path(raw_dir) / f"{recipe_id}.md"
        if candidate.exists():
            return candidate
    return None
