# hermes-recipes

**Markdown recipes that scaffold agents, teams, and file-first workflows on
[Hermes Agent](https://github.com/NousResearch/hermes-agent).**

A single markdown recipe like `development-team.md` becomes a real workspace
on disk:

- one **Hermes profile per role** (`team-lead`, `team-dev`, `team-test`, …)
- a shared on-disk **team workspace** with `inbox/`, `outbox/`,
  `shared-context/`, `notes/`, and **file-first ticket lanes**
  (`work/backlog/`, `work/in-progress/`, `work/testing/`, `work/done/`)
- recipe-declared **cron jobs** installed into Hermes's scheduler
- a **JSON workflow runner** with LLM / tool / approval / handoff nodes,
  per-agent queues, and approval bindings

Once installed, every action is accessible from the regular `hermes` CLI as a
new `recipes` subcommand tree.

```bash
# Spin up a team
hermes recipes scaffold-team --recipe-id development-team --team-id my-team \
    --provision-profiles --install-cron on

# Dispatch a request — creates an inbox entry + numbered backlog ticket
hermes recipes dispatch --team-id my-team --request "Add OAuth login" --owner lead

# Work the lifecycle: backlog → in-progress → testing → done
hermes recipes take     --team-id my-team --ticket 1 --owner dev
hermes recipes handoff  --team-id my-team --ticket 1
hermes recipes complete --team-id my-team --ticket 1
```

## Install

Hermes-recipes ships as a Python package. Pick one of two install paths.

### Method A — pip + `config.yaml` edit (smallest footprint)

```bash
~/.hermes/venv/bin/pip install hermes-recipes
```

Then add this to `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - hermes_recipes
```

### Method B — pip + directory-plugin shim (so `hermes plugins` sees it)

```bash
git clone https://github.com/JIGGAI/hermes-recipes.git
~/.hermes/venv/bin/pip install ./hermes-recipes
./hermes-recipes/scripts/install_dir_plugin.sh
hermes plugins enable hermes_recipes
```

### Verify

```bash
hermes recipes --help
```

You should see the full `tickets`, `dispatch`, `scaffold`, `workflows`,
… action tree. See [`docs/INSTALL.md`](docs/INSTALL.md) for the full
comparison, troubleshooting, and an end-to-end smoke test validated
against Hermes v0.13.0.

## What you get

Once installed, the plugin exposes these commands under `hermes recipes`:

| Command | What it does |
|---|---|
| `scaffold <recipe-id> --agent-id …` | Render a single-agent recipe into `~/.hermes/recipes/workspace-<agentId>/`, optionally provision a Hermes profile and install cron jobs |
| `scaffold-team <recipe-id> --team-id …` | Build a per-role team workspace + provision one Hermes profile per role |
| `dispatch --team-id … --request "…"` | Turn a free-form request into an inbox entry + numbered backlog ticket |
| `tickets --team-id …` | List tickets across the four lanes, JSON or table output |
| `take` / `handoff` / `assign` / `move-ticket` / `complete` | File-first ticket transitions with `Owner:` / `Status:` patching |
| `workflows run` | Enqueue a JSON workflow run from `shared-context/workflows/<file>.json` |
| `workflows runner-once` / `runner-tick` | Scheduler claims queued runs, enqueues their next runnable nodes onto per-agent queues |
| `workflows approve` / `resume` / `poll-approvals` | Approval lifecycle (human-in-the-loop steps) |
| `workflows cleanup-queues` | Drop queue tasks whose runs are terminal or missing |

Every ticket and workflow-run is a file on disk you can grep, version, and
diff — no opaque database.

## Recipe format

```yaml
---
id: development-team
kind: team
name: Development Team
agents:
  - role: lead
    name: Lead
  - role: dev
    name: Developer
  - role: test
    name: QA
templates:
  soul: |
    # SOUL — {{agentName}} ({{role}})
    I am part of team: {{teamId}}
  agents: "# AGENTS — {{agentName}}\n"
  tools:  "# TOOLS — {{agentName}}\n"
files:
  - path: SOUL.md
    template: soul
  - path: AGENTS.md
    template: agents
  - path: TOOLS.md
    template: tools
cronJobs:
  - id: lead-triage
    schedule: "*/30 7-23 * * 1-5"
    timezone: "America/New_York"
    agentId: "{{teamId}}-lead"
    enabledByDefault: true
    message: "Triage inbox, advance tickets, update notes/status.md."
---
```

Drop that under `~/.hermes/recipes/` (or any directory passed via
`--recipes-dir`) and `hermes recipes scaffold-team --recipe-id
development-team --team-id my-team` produces:

```
~/.hermes/workspace-my-team/
├── TEAM.md, TICKETS.md
├── inbox/, outbox/, work/{backlog,in-progress,testing,done}/
├── shared-context/{priorities,workflow-runs,workflow-queues}/
├── notes/{plan,status,QA_CHECKLIST}.md
└── roles/{lead,dev,test}/{SOUL,AGENTS,TOOLS}.md
```

…plus three new Hermes profiles (`my-team-lead`, `my-team-dev`,
`my-team-test`) and one cron job per role.

## Why a plugin and not just a skill

Recipes need to do things that don't fit a single skill:

- create durable named agents (Hermes profiles, one per role)
- maintain on-disk ticket state across sessions
- register a recurring scheduler that survives the chat loop
- expose a CLI surface so humans + cron jobs can drive it

Hermes's plugin system gives all four. Skills sit on top of this — agents
can call `hermes recipes dispatch …` via the terminal tool from within any
session.

## Roadmap

The big remaining piece is the **workflow worker + node executor** (Phase
4c on the roadmap). The scheduler enqueues workflow tasks onto per-agent
JSON queues today; node execution (LLM calls via `ctx.llm` / `PluginLlm`,
tool calls via `tools.registry`, approval bindings via the gateway) is the
next milestone. See [`ROADMAP.md`](ROADMAP.md) for the full plan plus a
list of smaller follow-ups (remaining media drivers, slash commands,
built-in recipe distribution, `hermes plugins list` upstream PR).

## Develop

```bash
git clone https://github.com/JIGGAI/hermes-recipes.git
cd hermes-recipes
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

233 tests cover the recipe DSL, scaffolding, ticket lifecycle, workflow
scheduler, cron reconciliation, integrations, and the Hermes plugin
registration contract (which simulates `importlib.metadata` the exact way
Hermes loads plugins on startup).

## Origin

Ported from [`@jiggai/recipes`](https://github.com/JIGGAI/ClawRecipes) — a
TypeScript OpenClaw plugin that's been running this same recipe + team +
workflow model for over a year. `hermes-recipes` is the Hermes-native
sibling: same primitives, same on-disk layout, fresh Python implementation
against Hermes's plugin / profile / cron APIs. The OpenClaw plugin remains
first-class on OpenClaw — this expands the surface to Hermes.

See [`docs/MAPPING.md`](docs/MAPPING.md) for the full clawrecipes → Hermes
concept map with file-and-line citations into both source trees.

## License

[Apache-2.0](LICENSE) — matches upstream ClawRecipes.
