"""Render recipe templates into agent / team workspaces.

Port of the *pure* half of clawrecipes/src/handlers/scaffold.ts +
src/handlers/team.ts. The handlers themselves are OpenClaw-specific (they
call ``applyAgentSnippetsToOpenClawConfig`` and shell out to ``openclaw
cron``); this Python port keeps the rendering pure and lets the CLI layer
choose what to do with the returned ``AgentConfigSnippet`` + cron reconcile
result.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from hermes_recipes.agent_config import AgentConfigSnippet
from hermes_recipes.fs_utils import ensure_dir, write_file_safely
from hermes_recipes.recipe_frontmatter import RecipeFrontmatter, normalize_cron_jobs
from hermes_recipes.scaffold_templates import render_team_md, render_tickets_md
from hermes_recipes.template import render_template


_TEAM_LEVEL_FILE_PREFIXES = ("shared-context/", "notes/")


@dataclass(frozen=True)
class ScaffoldedFile:
    path: Path
    wrote: bool
    reason: str


@dataclass(frozen=True)
class AgentScaffoldResult:
    files_root_dir: Path
    workspace_root_dir: Path
    file_results: list[ScaffoldedFile] = field(default_factory=list)
    snippet: Optional[AgentConfigSnippet] = None


def _normalize_templates(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("recipe.templates must be an object")
    return {k: v for k, v in raw.items() if isinstance(v, str)}


def _normalize_files(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("recipe.files must be an array")
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"recipe.files[{idx}] must be an object")
        file_path = str(entry.get("path") or "").strip()
        template = str(entry.get("template") or "").strip()
        if not file_path:
            raise ValueError(f"recipe.files[{idx}].path is required")
        if not template:
            raise ValueError(f"recipe.files[{idx}].template is required")
        mode_raw = str(entry.get("mode") or "").strip()
        if mode_raw and mode_raw not in ("createOnly", "overwrite"):
            raise ValueError(f"recipe.files[{idx}].mode must be createOnly|overwrite")
        out.append({"path": file_path, "template": template, "mode": mode_raw or None})
    return out


def scaffold_agent_from_recipe(
    recipe: RecipeFrontmatter,
    *,
    agent_id: str,
    files_root_dir: Path | str,
    workspace_root_dir: Path | str,
    agent_name: Optional[str] = None,
    vars: Optional[dict[str, str]] = None,
    update: bool = False,
    file_path_filter: Optional[Iterable[str]] = None,
    file_path_exclude: Optional[Iterable[str]] = None,
) -> AgentScaffoldResult:
    """Render ``recipe.templates`` into files under *files_root_dir*.

    Path-filter knobs:
      - *file_path_filter*: if provided, only paths starting with one of
        these prefixes are written. Team scaffolding uses this to write
        team-level files (``shared-context/``, ``notes/``) at the team root.
      - *file_path_exclude*: if provided, paths starting with one of these
        prefixes are skipped. Team scaffolding uses this to keep team-level
        files OUT of per-role directories.

    The two filters compose — exclusion runs after inclusion.
    """
    files_root = Path(files_root_dir)
    ensure_dir(files_root)

    templates = _normalize_templates(recipe.get("templates"))
    files = _normalize_files(recipe.get("files"))
    rendered_vars = dict(vars or {})
    include_prefixes = tuple(file_path_filter) if file_path_filter else None
    exclude_prefixes = tuple(file_path_exclude) if file_path_exclude else None

    file_results: list[ScaffoldedFile] = []
    for spec in files:
        path = spec["path"]
        if include_prefixes is not None and not any(
            path.startswith(prefix) for prefix in include_prefixes
        ):
            continue
        if exclude_prefixes is not None and any(
            path.startswith(prefix) for prefix in exclude_prefixes
        ):
            continue
        template_body = templates.get(spec["template"])
        if not isinstance(template_body, str):
            raise ValueError(f"Missing template: {spec['template']}")
        rendered = render_template(template_body, rendered_vars)
        target = files_root / path
        mode = spec["mode"] or ("overwrite" if update else "createOnly")
        result = write_file_safely(target, rendered, mode)
        file_results.append(
            ScaffoldedFile(path=target, wrote=result["wrote"], reason=result["reason"])
        )

    tools = recipe.get("tools") if isinstance(recipe.get("tools"), dict) else None
    snippet = AgentConfigSnippet(
        id=agent_id,
        workspace=str(workspace_root_dir),
        identity={"name": agent_name or recipe.get("name") or agent_id},
        tools=tools,
    )

    return AgentScaffoldResult(
        files_root_dir=files_root,
        workspace_root_dir=Path(workspace_root_dir),
        file_results=file_results,
        snippet=snippet,
    )


# ── team-level scaffolding ──────────────────────────────────────────────────


@dataclass(frozen=True)
class TeamScaffoldResult:
    team_dir: Path
    role_results: dict[str, AgentScaffoldResult] = field(default_factory=dict)
    snippets: list[AgentConfigSnippet] = field(default_factory=list)
    cron_jobs_declared: int = 0


def ensure_team_directory_structure(team_dir: Path | str) -> None:
    base = Path(team_dir)
    for sub in (
        "shared",
        "shared-context",
        "shared-context/agent-outputs",
        "shared-context/feedback",
        "shared-context/kpis",
        "shared-context/calendar",
        "shared-context/memory",
        "inbox",
        "outbox",
        "notes",
        "work",
        "work/backlog",
        "work/in-progress",
        "work/testing",
        "work/done",
        "work/assignments",
    ):
        (base / sub).mkdir(parents=True, exist_ok=True)


def _write_team_bootstrap_files(
    *,
    team_id: str,
    team_dir: Path,
    overwrite: bool,
    qa_checklist: bool,
) -> None:
    """Drop the canonical TEAM.md / TICKETS.md / status / notes scaffolding."""
    mode = "overwrite" if overwrite else "createOnly"
    write_file_safely(team_dir / "TEAM.md", render_team_md(team_id), mode)
    write_file_safely(team_dir / "TICKETS.md", render_tickets_md(team_id), mode)
    write_file_safely(
        team_dir / "shared-context" / "priorities.md",
        f"# Priorities — {team_id}\n\n- (empty)\n",
        mode,
    )
    write_file_safely(team_dir / "notes" / "plan.md", f"# Plan — {team_id}\n\n- (empty)\n", mode)
    write_file_safely(team_dir / "notes" / "status.md", f"# Status — {team_id}\n\n- (empty)\n", mode)
    if qa_checklist:
        write_file_safely(
            team_dir / "notes" / "QA_CHECKLIST.md",
            (
                f"# QA Checklist — {team_id}\n\n"
                "Use this when verifying a ticket before moving it from "
                "work/testing/ → work/done/.\n\n"
                "## Checklist\n"
                "- [ ] Repro steps verified\n"
                "- [ ] Acceptance criteria met\n"
                "- [ ] No regressions in adjacent flows\n"
            ),
            mode,
        )


def scaffold_team_from_recipe(
    recipe: RecipeFrontmatter,
    *,
    team_id: str,
    team_dir: Path | str,
    overwrite: bool = False,
) -> TeamScaffoldResult:
    """Lay out a team workspace and render per-role files.

    ``recipe.agents[]`` drives the role list; ``recipe.files[]`` is rendered
    once at the team root (only ``shared-context/`` and ``notes/`` paths)
    and again under each role dir (everything else).
    """
    base = Path(team_dir)
    ensure_team_directory_structure(base)

    qa_checklist = bool(recipe.get("qaChecklist") or False)
    if not qa_checklist:
        # Auto-enable if a `test` role is declared.
        agents = recipe.get("agents") or []
        qa_checklist = any(
            isinstance(a, dict) and str(a.get("role") or "") == "test"
            for a in agents
        )
    _write_team_bootstrap_files(
        team_id=team_id, team_dir=base, overwrite=overwrite, qa_checklist=qa_checklist
    )

    role_results: dict[str, AgentScaffoldResult] = {}
    snippets: list[AgentConfigSnippet] = []

    agents = recipe.get("agents") or []
    if not isinstance(agents, list):
        raise ValueError("recipe.agents must be an array")

    for entry in agents:
        if not isinstance(entry, dict):
            raise ValueError("recipe.agents[] entries must be objects")
        role = str(entry.get("role") or "").strip()
        if not role:
            raise ValueError("recipe.agents[].role is required")
        role_name = str(entry.get("name") or role).strip()
        agent_id = f"{team_id}-{role}"
        role_dir = base / "roles" / role

        result = scaffold_agent_from_recipe(
            recipe,
            agent_id=agent_id,
            agent_name=role_name,
            files_root_dir=role_dir,
            workspace_root_dir=role_dir,
            update=overwrite,
            vars={
                "teamId": team_id,
                "teamDir": str(base),
                "role": role,
                "agentId": agent_id,
                "agentName": role_name,
            },
            # Per-role dirs skip team-level prefixes (those land at the team root).
            file_path_exclude=_TEAM_LEVEL_FILE_PREFIXES,
        )
        role_results[role] = result
        if result.snippet is not None:
            snippets.append(result.snippet)

    # Write the team-level slice of files[] at the team root.
    team_level = scaffold_agent_from_recipe(
        recipe,
        agent_id=team_id,
        files_root_dir=base,
        workspace_root_dir=base,
        update=overwrite,
        vars={"teamId": team_id, "teamDir": str(base)},
        file_path_filter=_TEAM_LEVEL_FILE_PREFIXES,
    )

    cron_jobs_declared = len(normalize_cron_jobs(recipe))

    return TeamScaffoldResult(
        team_dir=base,
        role_results=role_results,
        snippets=snippets,
        cron_jobs_declared=cron_jobs_declared,
    )
