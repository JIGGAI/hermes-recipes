# hermes-recipes

A Hermes-native expansion of [ClawRecipes](https://github.com/JIGGAI/ClawRecipes) — markdown recipes that scaffold agents, teams, and file-first workflows on top of the [Hermes Agent](https://github.com/NousResearch/hermes-agent) runtime, alongside the existing OpenClaw plugin.

> **Status: early port in progress.** Phase 1 (recipe DSL parser) is implemented. Phases 2–6 are scaffolded but not yet written.

## Why

ClawRecipes is a ~5,200-LOC TypeScript plugin that ships on OpenClaw and stays the primary runtime there. This package expands the same primitives to Hermes — sibling to the OpenClaw plugin, not a replacement for it. Recipes authored once should work on either platform.

Hermes already ships an `openclaw-migration` skill that imports identity, memories, and command allowlists from `~/.openclaw`, but it does **not** cover the recipe DSL, the team / ticket workflow, or the JSON workflow runner. `hermes-recipes` fills that gap by reimplementing those pieces directly against Hermes's primitives (skills, plugins, kanban, cron, MCP), so a user running both platforms gets the same recipe surface on each.

## What's being ported

| ClawRecipes subsystem | Hermes target | Status |
|---|---|---|
| Recipe DSL (markdown + YAML frontmatter, `{{var}}` templates, `cronJobs`, `files`, `templates`) | Pure-Python reimplementation; no Hermes-API dependency | **Phase 1 — done** |
| Scaffold (agents + teams), workspace layout, agent-config snippet writer | `~/.hermes/recipes/` + per-team workspace dirs; writes Hermes config entries | Phase 2 |
| Tickets, lanes, dispatch/take/handoff/complete | Delegates to Hermes's existing kanban (`~/.hermes/kanban.db`); thin recipe-aware wrapper | Phase 3 |
| Workflow runner (LLM/tool/approval/handoff/writeback nodes, queue, worker tick) | Python port of the deterministic state machine; node executor calls Hermes tools registry; approvals via Hermes messaging gateway | Phase 4 |
| Cron declarations on recipes | Translated into Hermes cron jobs (`~/.hermes/cron/jobs.json`) via `cron.jobs` API | Phase 5 |
| Outbound posting + media drivers (DALL-E, Kling, Runway, Luma, NanoBanana) | Reused as HTTP/SDK clients; auth via Hermes config | Phase 5 |
| `openclaw recipes …` CLI tree | Exposed as Hermes plugin CLI: `hermes recipes …` | Phase 6 |

See [`docs/MAPPING.md`](docs/MAPPING.md) for the full concept-mapping with file:line citations into both source trees.

## Layout

```
hermes-recipes/
├── pyproject.toml
├── plugin.yaml                  # Hermes plugin manifest
├── SKILL.md                     # also installable as a Skills-Hub skill
├── README.md
├── docs/
│   └── MAPPING.md               # clawrecipes → hermes concept map
├── hermes_recipes/
│   ├── __init__.py              # register(ctx) — Hermes plugin entrypoint
│   ├── constants.py
│   ├── template.py              # {{var}} renderer (Phase 1)
│   ├── recipe_frontmatter.py    # YAML frontmatter + cronJobs (Phase 1)
│   ├── recipe_id.py             # id collision + auto-increment (Phase 1)
│   └── recipe_lint.py           # team-recipe sanity lints (Phase 1)
└── tests/
    ├── test_template.py
    ├── test_recipe_frontmatter.py
    └── test_recipe_id.py
```

## Install (into a real Hermes Agent)

Two install paths — pick one. Both validated end-to-end against Hermes
v0.13.0.

**Method A — pip + config edit** (simplest):

```bash
~/.hermes/venv/bin/pip install /path/to/hermes-recipes
# add hermes_recipes to plugins.enabled in ~/.hermes/config.yaml
hermes recipes --help
```

**Method B — pip + directory-plugin shim** (so `hermes plugins list` shows it):

```bash
~/.hermes/venv/bin/pip install /path/to/hermes-recipes
/path/to/hermes-recipes/scripts/install_dir_plugin.sh
hermes plugins enable hermes_recipes
hermes recipes --help
```

See [`docs/INSTALL.md`](docs/INSTALL.md) for the full comparison,
troubleshooting, and the end-to-end smoke test.

## Develop

```bash
cd hermes-recipes
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The test suite includes a `test_plugin_discovery.py` module that walks
`importlib.metadata.entry_points(group="hermes_agent.plugins")` exactly the
way Hermes does on startup and verifies `register(ctx)` lands without an
actual Hermes install.

## Source attribution

This is a port of [`@jiggai/recipes`](https://github.com/JIGGAI/ClawRecipes) (Apache-2.0). The TS source lives at `../clawrecipes/`. Where this package translates a specific TS file, the Python module's header points back to its origin.

## License

Apache-2.0 (matches upstream ClawRecipes).
