"""``hermes recipes`` CLI surface.

Phases 6a + 6b wire the full file-first command tree. ``worker-tick`` and the
inline ``workflows run`` (which runs nodes synchronously) are deferred to
Phase 4c — they require the workflow node executor.

Handlers are plain functions that take an ``argparse.Namespace`` and return
an ``int`` exit code, matching the Hermes plugin convention used by
``plugins/teams_pipeline/cli.py``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Callable, Optional

from hermes_recipes.cron_reconcile import (
    CronApi,
    reconcile_recipe_cron_jobs,
)
from hermes_recipes.cron_utils import (
    CronScope,
    load_cron_mapping_state,
    save_cron_mapping_state,
)
from hermes_recipes.integrations.hermes_cron import InMemoryCronApi
from hermes_recipes.integrations.hermes_profiles import (
    HermesProfileProvisioner,
    ProfileProvisioner,
)
from hermes_recipes.recipe_frontmatter import normalize_cron_jobs, parse_frontmatter
from hermes_recipes.recipe_loader import load_recipe_md
from hermes_recipes.scaffold import (
    scaffold_agent_from_recipe,
    scaffold_team_from_recipe,
)
from hermes_recipes.tickets import (
    assign_ticket,
    dispatch_request,
    list_tickets,
    move_ticket,
)
from hermes_recipes.ticket_workflow import handoff_ticket, take_ticket
from hermes_recipes.workflows.approvals import (
    approve_workflow_run,
    poll_workflow_approvals,
    resume_workflow_run,
)
from hermes_recipes.workflows.queue import cleanup_queues, enqueue_task
from hermes_recipes.workflows.runner import (
    enqueue_workflow_run,
    run_workflow_runner_once,
)
from hermes_recipes.workflows.tick import run_workflow_runner_tick
from hermes_recipes.workspace import resolve_team_context, resolve_workspace_root


# ──────────────────────────────────────────────────────────────────────────────
# Injectable defaults — tests swap these via CLI_HOOKS
# ──────────────────────────────────────────────────────────────────────────────


def _profile_provisioner_factory() -> ProfileProvisioner:
    return HermesProfileProvisioner()


def _cron_api_factory() -> CronApi:
    """Default cron API resolver — uses Hermes in production, in-memory otherwise."""
    if os.environ.get("HERMES_RECIPES_FAKE_CRON") == "1":
        return InMemoryCronApi()
    from hermes_recipes.integrations.hermes_cron import HermesCronApi

    return HermesCronApi()


CLI_HOOKS: dict[str, Callable[..., object]] = {
    "profile_provisioner": _profile_provisioner_factory,
    "cron_api": _cron_api_factory,
}


# ──────────────────────────────────────────────────────────────────────────────
# argparse wiring
# ──────────────────────────────────────────────────────────────────────────────


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes recipes <action>`` argparse tree."""
    subparser.add_argument(
        "--workspace-root",
        default=None,
        help="Override the recipes workspace root (default: ~/.hermes/recipes/workspace).",
    )
    subparser.add_argument(
        "--recipes-dir",
        action="append",
        default=None,
        help=(
            "Add a directory to the recipe lookup path. Repeat to add multiple. "
            "Defaults to <workspace_root>/../recipes."
        ),
    )
    subs = subparser.add_subparsers(dest="recipes_action")

    tickets_p = subs.add_parser("tickets", help="List tickets across all lanes for a team")
    tickets_p.add_argument("--team-id", required=True)
    tickets_p.add_argument("--json", action="store_true")

    dispatch_p = subs.add_parser("dispatch", help="Create an inbox + backlog ticket from a request")
    dispatch_p.add_argument("--team-id", required=True)
    dispatch_p.add_argument("--request", required=True)
    dispatch_p.add_argument("--owner", default="dev", choices=("dev", "devops", "lead", "test"))
    dispatch_p.add_argument("--dry-run", action="store_true")

    take_p = subs.add_parser("take", help="Take a ticket (move to in-progress, set Owner)")
    take_p.add_argument("--team-id", required=True)
    take_p.add_argument("--ticket", required=True)
    take_p.add_argument("--owner", default="dev", choices=("dev", "devops", "lead", "test"))

    handoff_p = subs.add_parser("handoff", help="Hand a ticket off to QA")
    handoff_p.add_argument("--team-id", required=True)
    handoff_p.add_argument("--ticket", required=True)
    handoff_p.add_argument("--tester", default="test", choices=("dev", "devops", "lead", "test"))

    assign_p = subs.add_parser("assign", help="Update the Owner: header on a ticket")
    assign_p.add_argument("--team-id", required=True)
    assign_p.add_argument("--ticket", required=True)
    assign_p.add_argument("--owner", required=True, choices=("dev", "devops", "lead", "test"))
    assign_p.add_argument("--dry-run", action="store_true")

    move_p = subs.add_parser("move-ticket", help="Move a ticket between lanes")
    move_p.add_argument("--team-id", required=True)
    move_p.add_argument("--ticket", required=True)
    move_p.add_argument("--to", required=True, choices=("backlog", "in-progress", "testing", "done"))
    move_p.add_argument("--completed", action="store_true")
    move_p.add_argument("--dry-run", action="store_true")

    complete_p = subs.add_parser("complete", help="Mark a ticket done")
    complete_p.add_argument("--team-id", required=True)
    complete_p.add_argument("--ticket", required=True)
    complete_p.add_argument("--dry-run", action="store_true")

    # ── scaffold + scaffold-team ───────────────────────────────────────────
    scaffold_p = subs.add_parser("scaffold", help="Scaffold a single-agent recipe")
    scaffold_p.add_argument("--recipe-id", required=True)
    scaffold_p.add_argument("--agent-id", required=True)
    scaffold_p.add_argument("--name", default=None)
    scaffold_p.add_argument("--overwrite", action="store_true")
    scaffold_p.add_argument(
        "--provision-profile",
        action="store_true",
        help="Call `hermes profile create <agentId>` after scaffolding",
    )
    scaffold_p.add_argument("--clone-from", default=None)
    scaffold_p.add_argument(
        "--install-cron",
        choices=("off", "prompt", "on"),
        default="off",
    )

    team_p = subs.add_parser("scaffold-team", help="Scaffold a team recipe (one role per agent)")
    team_p.add_argument("--recipe-id", required=True)
    team_p.add_argument("--team-id", required=True)
    team_p.add_argument("--overwrite", action="store_true")
    team_p.add_argument("--provision-profiles", action="store_true")
    team_p.add_argument("--clone-from", default=None)
    team_p.add_argument(
        "--install-cron", choices=("off", "prompt", "on"), default="off"
    )

    # ── workflow commands ──────────────────────────────────────────────────
    wf_p = subs.add_parser("workflows", help="Workflow runner / approval surfaces")
    wf_sub = wf_p.add_subparsers(dest="workflow_action")

    run_p = wf_sub.add_parser("run", help="Enqueue a workflow run (file-first)")
    run_p.add_argument("--team-id", required=True)
    run_p.add_argument("--workflow-file", required=True)
    run_p.add_argument("--trigger-kind", default="manual")

    once_p = wf_sub.add_parser("runner-once", help="Claim + advance one queued workflow run")
    once_p.add_argument("--team-id", required=True)
    once_p.add_argument("--run-id", default=None)
    once_p.add_argument("--lease-seconds", type=float, default=60.0)

    tick_p = wf_sub.add_parser("runner-tick", help="Claim + advance up to N queued workflow runs")
    tick_p.add_argument("--team-id", required=True)
    tick_p.add_argument("--concurrency", type=int, default=1)
    tick_p.add_argument("--lease-seconds", type=float, default=300.0)

    approve_p = wf_sub.add_parser("approve", help="Approve or reject a paused workflow run")
    approve_p.add_argument("--team-id", required=True)
    approve_p.add_argument("--run-id", required=True)
    approve_p.add_argument(
        "--approved", type=lambda v: str(v).lower() in ("1", "true", "yes"), required=True
    )
    approve_p.add_argument("--note", default=None)

    resume_p = wf_sub.add_parser("resume", help="Re-enter a workflow run after its approval was decided")
    resume_p.add_argument("--team-id", required=True)
    resume_p.add_argument("--run-id", required=True)

    poll_p = wf_sub.add_parser("poll-approvals", help="Resume any decided approvals across all runs")
    poll_p.add_argument("--team-id", required=True)
    poll_p.add_argument("--limit", type=int, default=None)

    cleanup_p = wf_sub.add_parser("cleanup-queues", help="Drop queue tasks for terminal/missing runs")
    cleanup_p.add_argument("--team-id", required=True)

    subparser.set_defaults(func=recipes_command)


# ──────────────────────────────────────────────────────────────────────────────
# top-level handler
# ──────────────────────────────────────────────────────────────────────────────


_ACTIONS_HELP = (
    "{tickets|dispatch|take|handoff|assign|move-ticket|complete|"
    "scaffold|scaffold-team|workflows}"
)


def recipes_command(args: argparse.Namespace) -> int:
    action = getattr(args, "recipes_action", None)
    if not action:
        print(f"Usage: hermes recipes {_ACTIONS_HELP}")
        return 2
    try:
        return _DISPATCH[action](args)
    except KeyError:
        print(f"Unknown action: {action}")
        return 2
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return 1
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# Path resolution helpers
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_workspace_root(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "workspace_root", None)
    if explicit:
        return Path(explicit).expanduser()
    return resolve_workspace_root()


def _resolve_team_dir(args: argparse.Namespace) -> Path:
    workspace_root = _resolve_workspace_root(args)
    ctx = resolve_team_context(args.team_id, workspace_root=workspace_root)
    return ctx["team_dir"]


def _resolve_recipe_dirs(args: argparse.Namespace) -> list[Path]:
    """Order:
      1. explicit ``--recipes-dir`` entries (CLI override)
      2. ``<workspace_root>/../recipes`` (user-managed workspace recipes)
      3. ``hermes_recipes/bundled_recipes/`` (ships with the package)
    """
    dirs: list[Path] = []
    for raw in getattr(args, "recipes_dir", None) or []:
        dirs.append(Path(raw).expanduser())
    workspace_root = _resolve_workspace_root(args)
    dirs.append(workspace_root.parent / "recipes")
    # Bundled recipes ship with the package.
    bundled = Path(__file__).parent / "bundled_recipes"
    if bundled.is_dir():
        dirs.append(bundled)
    return dirs


# ──────────────────────────────────────────────────────────────────────────────
# Ticket commands (Phase 6a)
# ──────────────────────────────────────────────────────────────────────────────


def _cmd_tickets(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = list_tickets(team_dir)
    if getattr(args, "json", False):
        payload = {
            lane: [
                {"number": r.number, "id": r.id, "file": str(r.file), "stage": r.stage}
                for r in result[lane]
            ]
            for lane in ("backlog", "in_progress", "testing", "done")
        }
        print(json.dumps(payload, indent=2))
        return 0
    for lane in ("backlog", "in_progress", "testing", "done"):
        rows = result[lane]
        header = lane.replace("_", "-")
        print(f"\n{header} ({len(rows)}):")
        if not rows:
            print("  (none)")
            continue
        for row in rows:
            print(f"  {row.id}  →  {row.file}")
    return 0


def _cmd_dispatch(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = dispatch_request(
        team_dir=team_dir,
        team_id=args.team_id,
        request_text=args.request,
        owner=args.owner,
        dry_run=args.dry_run,
    )
    print(json.dumps({**result, "team_dir": str(team_dir)}, default=str, indent=2))
    return 0


def _cmd_take(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = take_ticket(team_dir=team_dir, ticket=args.ticket, owner=args.owner)
    print(
        json.dumps(
            {
                "ok": True,
                "src_path": str(result["src_path"]),
                "dest_path": str(result["dest_path"]),
                "moved": result["moved"],
            },
            indent=2,
        )
    )
    return 0


def _cmd_handoff(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = handoff_ticket(team_dir=team_dir, ticket=args.ticket, tester=args.tester)
    print(
        json.dumps(
            {
                "ok": True,
                "src_path": str(result["src_path"]),
                "dest_path": str(result["dest_path"]),
                "moved": result["moved"],
            },
            indent=2,
        )
    )
    return 0


def _cmd_assign(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = assign_ticket(
        team_dir=team_dir,
        ticket=args.ticket,
        owner=args.owner,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


def _cmd_move_ticket(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = move_ticket(
        team_dir=team_dir,
        ticket=args.ticket,
        to=args.to,
        completed=args.completed,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


def _cmd_complete(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = move_ticket(
        team_dir=team_dir,
        ticket=args.ticket,
        to="done",
        completed=True,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Scaffold commands (Phase 6b)
# ──────────────────────────────────────────────────────────────────────────────


def _maybe_reconcile_cron(
    args: argparse.Namespace,
    *,
    scope: CronScope,
    frontmatter: dict,
    install_mode: str,
) -> Optional[dict]:
    if install_mode == "off":
        return None
    cron_jobs = normalize_cron_jobs(frontmatter)
    if not cron_jobs:
        return {"results": [], "message": "Recipe declares no cron jobs."}
    cron_api = CLI_HOOKS["cron_api"]()
    state_path = scope.state_dir / "notes" / "cron-jobs.json"
    state = load_cron_mapping_state(state_path)
    outcome = reconcile_recipe_cron_jobs(
        api=cron_api,
        scope=scope,
        recipe_cron_jobs=cron_jobs,
        state=state,
        install_mode=install_mode,  # type: ignore[arg-type]
    )
    save_cron_mapping_state(state_path, outcome.mapping)
    return {
        "results": [
            {
                "action": r.action,
                "key": r.key,
                "installed_cron_id": r.installed_cron_id,
            }
            for r in outcome.results
        ],
        "state_path": str(state_path),
    }


def _cmd_scaffold(args: argparse.Namespace) -> int:
    recipe_dirs = _resolve_recipe_dirs(args)
    loaded = load_recipe_md(args.recipe_id, recipe_dirs=recipe_dirs)
    frontmatter, _ = parse_frontmatter(loaded.md)
    workspace_root = _resolve_workspace_root(args)
    files_root = workspace_root.parent / f"workspace-{args.agent_id}"
    result = scaffold_agent_from_recipe(
        frontmatter,
        agent_id=args.agent_id,
        files_root_dir=files_root,
        workspace_root_dir=files_root,
        agent_name=args.name,
        update=args.overwrite,
        vars={
            "agentId": args.agent_id,
            "agentName": args.name or str(frontmatter.get("name") or args.agent_id),
        },
    )
    provision = None
    if args.provision_profile:
        provisioner = CLI_HOOKS["profile_provisioner"]()
        provision = provisioner.create_profile(args.agent_id, clone_from=args.clone_from)
    cron_result = _maybe_reconcile_cron(
        args,
        scope=CronScope(
            kind="agent",
            agent_id=args.agent_id,
            recipe_id=str(frontmatter.get("id") or args.recipe_id),
            state_dir=files_root,
        ),
        frontmatter=frontmatter,
        install_mode=args.install_cron,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "agent_id": args.agent_id,
                "files_root_dir": str(result.files_root_dir),
                "files_written": [
                    {"path": str(f.path), "wrote": f.wrote, "reason": f.reason}
                    for f in result.file_results
                ],
                "snippet": {
                    "id": result.snippet.id,
                    "workspace": result.snippet.workspace,
                    "identity": result.snippet.identity,
                }
                if result.snippet
                else None,
                "profile": {
                    "name": provision.name,
                    "created": provision.created,
                    "already_existed": provision.already_existed,
                }
                if provision
                else None,
                "cron": cron_result,
            },
            indent=2,
        )
    )
    return 0


def _cmd_scaffold_team(args: argparse.Namespace) -> int:
    recipe_dirs = _resolve_recipe_dirs(args)
    loaded = load_recipe_md(args.recipe_id, recipe_dirs=recipe_dirs)
    frontmatter, _ = parse_frontmatter(loaded.md)
    workspace_root = _resolve_workspace_root(args)
    team_dir = workspace_root.parent / f"workspace-{args.team_id}"

    result = scaffold_team_from_recipe(
        frontmatter,
        team_id=args.team_id,
        team_dir=team_dir,
        overwrite=args.overwrite,
    )

    provisions: list[dict] = []
    if args.provision_profiles:
        provisioner = CLI_HOOKS["profile_provisioner"]()
        for role, role_result in result.role_results.items():
            if role_result.snippet is None:
                continue
            outcome = provisioner.create_profile(
                role_result.snippet.id, clone_from=args.clone_from
            )
            provisions.append(
                {
                    "name": outcome.name,
                    "role": role,
                    "created": outcome.created,
                    "already_existed": outcome.already_existed,
                }
            )

    cron_result = _maybe_reconcile_cron(
        args,
        scope=CronScope(
            kind="team",
            team_id=args.team_id,
            recipe_id=str(frontmatter.get("id") or args.recipe_id),
            state_dir=team_dir,
        ),
        frontmatter=frontmatter,
        install_mode=args.install_cron,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "team_id": args.team_id,
                "team_dir": str(result.team_dir),
                "roles": list(result.role_results.keys()),
                "agents": [s.id for s in result.snippets],
                "profiles_provisioned": provisions,
                "cron_jobs_declared": result.cron_jobs_declared,
                "cron": cron_result,
            },
            indent=2,
        )
    )
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Workflow commands (Phase 6b)
# ──────────────────────────────────────────────────────────────────────────────


def _cmd_workflows(args: argparse.Namespace) -> int:
    action = getattr(args, "workflow_action", None)
    if not action:
        print(
            "Usage: hermes recipes workflows "
            "{run|runner-once|runner-tick|approve|resume|poll-approvals|cleanup-queues}"
        )
        return 2
    return _WORKFLOW_DISPATCH[action](args)


def _cmd_workflows_run(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = enqueue_workflow_run(
        team_dir=team_dir,
        team_id=args.team_id,
        workflow_file=args.workflow_file,
        trigger={"kind": args.trigger_kind},
    )
    print(json.dumps({**result, "team_dir": str(team_dir)}, default=str, indent=2))
    return 0


def _cmd_workflows_runner_once(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = run_workflow_runner_once(
        team_dir=team_dir,
        team_id=args.team_id,
        lease_seconds=args.lease_seconds,
        run_id=args.run_id,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


def _cmd_workflows_runner_tick(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = run_workflow_runner_tick(
        team_dir=team_dir,
        team_id=args.team_id,
        concurrency=args.concurrency,
        lease_seconds=args.lease_seconds,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


def _cmd_workflows_approve(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = approve_workflow_run(
        team_dir=team_dir,
        run_id=args.run_id,
        approved=args.approved,
        note=args.note,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "run_id": result.run_id,
                "status": result.status,
                "approval_file": str(result.approval_file),
            },
            indent=2,
        )
    )
    return 0


def _cmd_workflows_resume(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = resume_workflow_run(
        team_dir=team_dir,
        team_id=args.team_id,
        run_id=args.run_id,
        enqueue_task=enqueue_task,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


def _cmd_workflows_poll_approvals(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = poll_workflow_approvals(
        team_dir=team_dir,
        team_id=args.team_id,
        enqueue_task=enqueue_task,
        limit=args.limit,
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


def _cmd_workflows_cleanup_queues(args: argparse.Namespace) -> int:
    team_dir = _resolve_team_dir(args)
    result = cleanup_queues(team_dir)
    print(json.dumps(result, default=str, indent=2))
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch tables
# ──────────────────────────────────────────────────────────────────────────────


_DISPATCH = {
    "tickets": _cmd_tickets,
    "dispatch": _cmd_dispatch,
    "take": _cmd_take,
    "handoff": _cmd_handoff,
    "assign": _cmd_assign,
    "move-ticket": _cmd_move_ticket,
    "complete": _cmd_complete,
    "scaffold": _cmd_scaffold,
    "scaffold-team": _cmd_scaffold_team,
    "workflows": _cmd_workflows,
}


_WORKFLOW_DISPATCH = {
    "run": _cmd_workflows_run,
    "runner-once": _cmd_workflows_runner_once,
    "runner-tick": _cmd_workflows_runner_tick,
    "approve": _cmd_workflows_approve,
    "resume": _cmd_workflows_resume,
    "poll-approvals": _cmd_workflows_poll_approvals,
    "cleanup-queues": _cmd_workflows_cleanup_queues,
}
