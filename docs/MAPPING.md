# ClawRecipes → Hermes Concept Mapping

This document maps every primitive in ClawRecipes (the OpenClaw plugin, TypeScript) to its equivalent in Hermes Agent (Python). Citations point at real files in both source trees so the port stays grounded. The OpenClaw plugin remains first-class on OpenClaw; this map drives the parallel Hermes expansion.

- Source: `/Users/rjjohnston/Sites/clawrecipes` (TypeScript, ~5,200 LOC)
- Target: `/Users/rjjohnston/Sites/hermes-agent` (Python ≥3.11)

## 1. Plugin shell

| ClawRecipes | Hermes |
|---|---|
| `openclaw.plugin.json` — id, version, configSchema, uiHints (clawrecipes/openclaw.plugin.json) | `plugin.yaml` — name, version, description, kind, platforms (e.g. hermes-agent/plugins/teams_pipeline/plugin.yaml) |
| `index.ts` exports + `api.registerCli()` (clawrecipes/index.ts:268) | `plugins/<name>/__init__.py` exports `register(ctx)`, calls `ctx.register_cli_command(...)` (hermes-agent/plugins/teams_pipeline/__init__.py) |
| OpenClaw `message_received` event subscription (clawrecipes/index.ts:245) | Hermes gateway transport adapters under `agent/transports/` and `tools/send_message_tool.py` (binding-aware) |
| OpenClaw `api.config` read/replace (clawrecipes/src/lib/recipes-config.ts:28-48) | Hermes `hermes_cli/config.py` `load_config()` / `save_config()` |

**Port shape for hermes-recipes:** a Hermes plugin directory `hermes_recipes/` with `plugin.yaml`, `__init__.py:register(ctx)`, and CLI registration of a `recipes` command tree.

## 2. Recipe DSL (Phase 1, pure logic)

| ClawRecipes | Hermes / hermes-recipes |
|---|---|
| `src/lib/recipe-frontmatter.ts` — YAML frontmatter parse, `normalizeCronJobs` | `hermes_recipes/recipe_frontmatter.py` (port; uses PyYAML) |
| `src/lib/template.ts` — `{{key}}` substitution | `hermes_recipes/template.py` (port; uses `re`) |
| `src/lib/recipe-id.ts` — id collision + auto-increment | `hermes_recipes/recipe_id.py` (port) |
| `src/lib/recipe-lint.ts` — team-recipe sanity checks | `hermes_recipes/recipe_lint.py` (port) |
| `src/lib/constants.ts` — `VALID_ROLES`, `VALID_STAGES`, `MAX_RECIPE_ID_AUTO_INCREMENT` | `hermes_recipes/constants.py` (port) |

Pure functions; no Hermes-API dependencies. Already implemented and tested in Phase 1.

## 3. Workspace + agent config (Phase 2)

| ClawRecipes | Hermes |
|---|---|
| Workspace root: `~/.openclaw/workspace` (clawrecipes/src/lib/workspace.ts:14-83) | Hermes home: `~/.hermes/` (hermes-agent/hermes_constants.py `get_hermes_home()`) |
| Per-agent workspace dir: `workspace-<agentId>/` | `~/.hermes/recipes/workspace-<agentId>/` (sibling to the canonical workspace root, matching the OpenClaw layout) |
| Per-team workspace dir: `workspace-<teamId>/roles/<role>/` | `~/.hermes/recipes/workspace-<teamId>/roles/<role>/` |
| OpenClaw `agents.list[]` entries with id/workspace/identity/tools (clawrecipes/src/lib/agent-config.ts) | **Hermes profiles** — each ClawRecipes agent maps 1:1 to a Hermes profile (`hermes profile create <agentId> --clone main`). Profiles have isolated config, sessions, skills, memory, and credentials. The `agent_config.upsert_agent_in_config` helper still writes a portable index (`recipe-agents.json`) for record-keeping and dashboard use; the actual provisioning happens via `hermes profile create` in Phase 6. |
| OpenClaw bindings (`bindings[]` with channel/peer/guild/team match) | Per-profile gateway configuration. The port stores intent in `recipe-bindings.json` (via `bindings.upsert_binding_in_config`) and Phase 6 translates each binding into `hermes gateway` config for the target profile. |
| `api.runtime.config.replaceConfigFile()` (clawrecipes/src/lib/recipes-config.ts:42) | `hermes_cli.config.save_config()` per profile (Phase 6 wires this). |

### Why profile-per-role and not subagents

ClawRecipes models agents as durable, named identities (`team-lead`, `team-dev`, …) with their own workspace, SOUL, and tool profile. Hermes has three multi-agent primitives — **profiles** (durable, named, isolated `hermes` instances), **`delegate_task` subagents** (synchronous spawn, ephemeral, summary returned to parent), and **`hermes -w` worktree spawning** (separate `hermes` processes controlled via tmux). Of these, only profiles preserve the ClawRecipes "named role with its own state" semantics, so the port targets profiles.

Subagents and worktree spawning remain available as implementation details for the workflow runner: a `tool` or `llm` node can `delegate_task(...)` to a short-lived worker without disturbing the profile model.

## 3a. Teams on Hermes

Hermes does not have a built-in "team" object. The port assembles a team from existing primitives:

1. **A profile per role** — `hermes profile create <teamId>-<role> --clone main`, one per entry in `agents:` from the recipe.
2. **A shared on-disk workspace** — `~/.hermes/recipes/workspace-<teamId>/`, with the same `roles/<role>/`, `work/<lane>/`, `inbox/`, `outbox/`, `shared-context/`, `notes/` layout the OpenClaw plugin uses. Each role profile sets its `workdir` to its role directory.
3. **A shared kanban board** — Hermes's kanban already advertises itself as a "multi-profile collaboration board" (`tools/kanban_tools.py`). The port creates a per-team board on scaffold and (Phase 6) mirrors ticket-file state into it so users see the same tickets in `hermes kanban` and `/kanban`.
4. **Per-role cron jobs** — recipe `cronJobs:` entries get `profile: <agentId>` when installed via Hermes's cron API (Phase 5).

## 4. Ticket workflow (Phase 3 — done)

**Decision: file-first stays the source of truth.** Hermes kanban statuses (`triage|todo|ready|running|blocked|done|archived`, see `hermes_cli/kanban_db.py:93`) don't map 1:1 to ClawRecipes lanes (`backlog|in-progress|testing|done`), and the OpenClaw plugin keeps recipes/workflows that depend on the on-disk lane layout — the most compatible port keeps that layout intact on Hermes. Phase 6 then layers a thin **kanban-sync adapter** that mirrors ticket files into Hermes's kanban DB so users see the same tickets in `hermes kanban` and `/kanban`.

| ClawRecipes | hermes-recipes (Phase 3) |
|---|---|
| Lanes (backlog / in-progress / testing / done) (clawrecipes/src/lib/lanes.ts:22-32) | `hermes_recipes/lanes.py` (Phase 2) — same directory layout |
| Ticket file `NNNN-slug.md` with `Owner:` / `Status:` frontmatter | `hermes_recipes/ticket_finder.py` + `hermes_recipes/ticket_workflow.py` — identical on-disk shape |
| `dispatch` (clawrecipes/index.ts:524-578) | `hermes_recipes/tickets.dispatch_request` — same inbox + backlog ticket writes |
| `take`, `handoff` (clawrecipes/src/lib/ticket-workflow.ts) | `hermes_recipes/ticket_workflow.take_ticket`, `handoff_ticket` |
| `move-ticket`, `assign`, list tickets (clawrecipes/src/handlers/tickets.ts) | `hermes_recipes/tickets.move_ticket`, `assign_ticket`, `list_tickets` |
| OpenClaw `api.runtime.system.enqueueSystemEvent` after dispatch | Injected as an optional `on_nudge=` callback so the file-first writes stay testable; Phase 6 wires a real Hermes-side callback |
| `cleanup-closed-assignments` (legacy) | Skipped — assignment stubs are deprecated upstream too |

### Kanban-sync (Phase 6)

Plan:
- On `scaffold-team`, create a Hermes kanban board named `recipes:<teamId>` via the same SQLite store at `~/.hermes/kanban.db`.
- On every ticket transition (`dispatch`, `take`, `handoff`, `move_ticket`, `complete`), upsert a matching kanban task. Ticket → kanban status mapping: backlog → `todo`, in-progress → `running`, testing → `running` + metadata `lane=testing`, done → `done`.
- Ticket `Owner:` → kanban `assignee` (profile name).
- Comments under `## Comments` get mirrored into kanban `task_comments`.

This keeps the OpenClaw plugin's file-first guarantees while giving Hermes users the native kanban experience.

## 5. Workflow runner (Phase 4 — largest)

This is the most complex subsystem and has **no direct Hermes equivalent**. The port keeps the file-first design (workflow JSON + run files) so workflow authors don't have to rewrite their workflows.

| ClawRecipes | hermes-recipes plan |
|---|---|
| `src/lib/workflows/workflow-types.ts` — Workflow / Run / NodeState / ApprovalRecord shapes | `hermes_recipes/workflows/types.py` — Python `TypedDict` / `dataclass` |
| `workflow-runner.ts` — enqueue + lifecycle | `workflows/runner.py` |
| `workflow-queue.ts` — per-agent JSON queues + claim/lease locks | `workflows/queue.py` (same file layout: `shared-context/workflow-queues/<agentId>.json`) |
| `workflow-worker.ts` — main worker loop | `workflows/worker.py` |
| `workflow-node-executor.ts` — node execution | `workflows/node_executor.py` — node kinds map: |
| &nbsp;&nbsp;`llm` node → calls Claude via OpenClaw plugin\_llm | → Hermes `agent/plugin_llm.py` (provider-agnostic) |
| &nbsp;&nbsp;`tool` node → calls OpenClaw `api.toolsInvoke` | → Hermes `tools.registry.registry.invoke(tool_name, args)` |
| &nbsp;&nbsp;`human_approval` node → reads `shared-context/.../approvals/approval.json`, listens for Telegram reply | → Hermes `tools/approval.py` + binding-aware reply via gateway transports |
| &nbsp;&nbsp;`writeback` node → patches ticket markdown | → kanban metadata update |
| &nbsp;&nbsp;`handoff` node → moves ticket to new lane / owner | → kanban move task |
| `workflow-tick.ts` — runner tick (claim N runs in parallel) | `workflows/tick.py` |
| `workflow-approvals.ts` — approval lifecycle | `workflows/approvals.py` |
| `outbound-client.ts` — HTTP POST to `<baseUrl>/v1/<platform>/publish` | `workflows/outbound.py` — same HTTP shape (it's already a clean HTTP boundary) |
| `outbound-sanitize.ts` — strip draft markers | `workflows/outbound_sanitize.py` (direct port) |
| `media-drivers/` — DALL-E, Kling, Runway, Luma, NanoBanana | `workflows/media_drivers/` — Hermes already has `agent/image_gen_provider.py` + `agent/image_gen_registry.py`; prefer wiring through those where types match, port the rest. |

## 6. Cron (Phase 5)

| ClawRecipes | Hermes |
|---|---|
| `cronJobs:` in recipe frontmatter (id, schedule, message, agentId, timezone, timeoutSeconds, enabledByDefault, delivery) | Hermes cron job schema in `cron/jobs.py` (id, schedule, prompt, skills, timezone, ...) |
| `reconcileRecipeCronJobs()` shells out to `openclaw cron add/edit` (clawrecipes/src/handlers/cron.ts:175-288) | Calls `cron.jobs.create_job()` / `cron.jobs.update_job()` directly (in-process; no subprocess) |
| `cronInstallation: off \| prompt \| on` config | Same enum; same UX (CLI prompt) |
| Spec-hash mapping at `notes/cron-jobs.json` for change detection | Same file inside `~/.hermes/recipes/teams/<teamId>/notes/cron-jobs.json` |
| Orphan disable on recipe re-scaffold | Same logic — uses Hermes `cron.jobs.delete_job(id)` |

This is the cleanest port surface — Hermes's cron API is already in-process and idempotent.

## 7. Marketplace + skill install + kitchen manifest (Phase 6)

| ClawRecipes | hermes-recipes plan |
|---|---|
| ClawHub marketplace fetch from `clawkitchen.ai` (clawrecipes/src/handlers/install.ts) | Hermes Skills Hub at `agentskills.io` (already integrated in `tools/skills_hub.py`); recipes can be published there as `kind: recipe-pack` skills |
| Skill install (manual `npx clawhub install`) | Hermes `tools/skills_sync.py` does this natively |
| Kitchen manifest (clawrecipes/src/lib/kitchen-manifest.ts) — pre-computed nav JSON | Optional. Hermes has its own dashboard (`hermes dashboard`). Defer until requested. |

## 8. CLI surface (Phase 6)

ClawRecipes registers `openclaw recipes <subcommand>`. The port registers `hermes recipes <subcommand>` via `ctx.register_cli_command()` with the same subcommand names where they make sense:

```
hermes recipes list | show | status
hermes recipes scaffold | scaffold-team | add-role | migrate-team | remove-team
hermes recipes dispatch | tickets | take | handoff | assign | move-ticket | complete
hermes recipes workflows run | runner-once | runner-tick | worker-tick | approve | resume | poll-approvals | cleanup-queues
hermes recipes bind | unbind | bindings
hermes recipes install | install-recipe | install-skill
```

Subcommands are wired in Phase 6 once Phases 1–5 are stable.

## What's pure logic vs adapter-required

Direct from the architectural review:

**Pure (port directly):** recipe-frontmatter, template, recipe-id, recipe-lint, lanes (logic only), ticket-finder, ticket-workflow (markdown patching), agent-config (object construction), cron-utils (spec hashing), workflow-types, workflow-queue, workflow-worker (state machine), workflow-node-executor (control flow), workflow-approvals (file-based state), workflow-utils, outbound-client, outbound-sanitize, kitchen-manifest, skill-install (detection only).

**Adapter (wrap Hermes equivalents):** workspace resolution (Hermes home), recipes listing (filesystem), recipes-config (Hermes config I/O), cron reconciliation (Hermes cron API), tool invocation in workflow nodes (Hermes tool registry), message-bus listener for approval replies (Hermes gateway transports), approval-binding lookup (Hermes bindings), manifest scheduling (Hermes task scheduler), media drivers (prefer Hermes image-gen registry where overlapping).

This split is the basis for the phased plan in [README.md](../README.md).
