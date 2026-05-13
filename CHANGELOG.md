# Changelog

All notable changes to **hermes-recipes** will be documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-05-12

Ships two real recipes out of the box. After install, `hermes recipes
scaffold-team --recipe-id development-team --team-id my-team` (or
`marketing-team`) lays out a working multi-role team workspace with no
extra files to drop.

### Added

- **Bundled recipes** at `hermes_recipes/bundled_recipes/`:
  - `development-team` — 5 roles (lead, dev, devops, test,
    workflow-runner), 9 cron jobs (lead triage loop, per-role work loops,
    workflow runner loop, PR watcher, testing-lane loop, 3-hour backup).
    Same shape as upstream `@jiggai/recipes`, OpenClaw-isms swapped for
    Hermes equivalents.
  - `marketing-team` — 12 roles (lead, seo, copywriter, ads, social,
    designer, analyst, video, compliance, offer, funnel, lifecycle), 13
    cron jobs.
- **Bundled-recipe discovery.** `recipe_loader` and the CLI's
  `_resolve_recipe_dirs` now append the package's `bundled_recipes/`
  directory after any explicit `--recipes-dir` flags and after
  `<workspace_root>/../recipes`, so new users can scaffold a team with
  zero workspace setup.
- **Role-prefix template resolution** in `scaffold_team_from_recipe`.
  Bare template names in `recipe.files[]` get rewritten to
  `<role>.<template>` at per-role scaffold time; dotted names
  (`sharedContext.priorities`) pass through unchanged. Matches the
  upstream behavior in `clawrecipes/src/handlers/team.ts:241-248`.
- **Per-agent `tools:` override.** Each entry in `recipe.agents[]` can
  specify its own `tools:` block; the scaffolder uses it in place of the
  recipe-level `tools:`.
- **Per-role continuity bootstrap** (matches `team.ts:273-309`):
  `MEMORY.md`, `memory/YYYY-MM-DD.md`, and `agent-outputs/README.md`
  written unconditionally under every role dir.
- **Default file set fallback.** When `recipe.files[]` is omitted, the
  scaffolder falls back to `{SOUL,AGENTS,TOOLS,STATUS,NOTES}.md` so a
  team recipe missing `files:` still produces usable role workspaces.

### Notes

- `[tool.setuptools.package-data]` includes `bundled_recipes/*.md` so
  pip install ships the recipes alongside the code.
- 6 new tests under `tests/test_bundled_recipes.py` cover discovery,
  parse, no-residual-OpenClaw-refs, and end-to-end scaffold for both
  bundled recipes.
- Validated end-to-end against Hermes v0.13.0: development-team produces
  a 71-file workspace, marketing-team produces 118 files, both via a
  single `hermes recipes scaffold-team` call.

## [0.2.1] — 2026-05-12

Docs + tooling polish. Same code surface as 0.2.0; the package now ships
a second install path that makes `hermes plugins list` / `hermes plugins
enable` work without manual `config.yaml` edits.

### Added

- **`scripts/install_dir_plugin.sh`** — drops a 2-file directory-plugin
  shim under `~/.hermes/plugins/hermes_recipes/` so Hermes's CLI surfaces
  the plugin like any bundled one. `--uninstall` removes the shim
  cleanly.
- **`docs/INSTALL.md` rewrite.** Leads with the validated smoke test,
  then documents both install paths (Method A: pip + config edit;
  Method B: pip + directory-plugin shim) with a comparison table.
- **`plugin.yaml`** bumped to 0.2.1 to match `pyproject.toml`.

### Fixed

- Doc framing in v0.2.0 lead with the *gotcha* about `hermes plugins
  enable` failing, which read as "the plugin doesn't work". It does — the
  gotcha is a Hermes UX gap around entry-point plugins. Method B above
  routes around it entirely.

## [0.2.0] — 2026-05-12

The package now installs as a real Hermes plugin and the file-first ticket +
workflow-scheduler surfaces work end-to-end against `hermes` v0.13.0.

### Added

- **Hermes plugin discovery via `hermes_agent.plugins` entry-point group.**
  `pip install hermes-recipes` into the Hermes venv is the install path; no
  `~/.hermes/plugins/hermes_recipes/` directory required. Three regression
  tests under `tests/test_plugin_discovery.py` simulate Hermes's exact load
  flow against `importlib.metadata`.
- **`hermes recipes` CLI tree.** All ticket actions (`tickets`, `dispatch`,
  `take`, `handoff`, `assign`, `move-ticket`, `complete`), scaffold actions
  (`scaffold`, `scaffold-team`), and workflow scheduler actions
  (`workflows run|runner-once|runner-tick|approve|resume|poll-approvals|
  cleanup-queues`).
- **Hermes profile provisioning.** `integrations.hermes_profiles.HermesProfileProvisioner`
  shells out to `hermes profile create` (idempotent on "already exists").
  `--provision-profiles` / `--provision-profile` flags wire it into the
  scaffold commands.
- **Cron reconciliation.** `cron_reconcile.reconcile_recipe_cron_jobs`
  + `integrations.hermes_cron.HermesCronApi` (lazy-imports
  `hermes_agent.cron.jobs`). `--install-cron {off|prompt|on}` flag on scaffold
  commands.
- **Phases 1–5 + 6a/6b modules** — DSL parser, scaffold + workspace,
  tickets + lanes, workflow types/utils/approvals/queue/runner/tick,
  cron + outbound + media drivers (OpenAI image-gen driver, others deferred).
- **Documentation.** `README.md`, `docs/INSTALL.md` (with end-to-end smoke
  recipe), `docs/MAPPING.md` (clawrecipes → Hermes concept map with file:line
  citations).

### Validated against Hermes Agent v0.13.0

Full ticket lifecycle (dispatch → backlog → in-progress → testing → done) and
team scaffold + workflow-run + runner-once all execute against a real
`hermes` process. See [`docs/INSTALL.md`](docs/INSTALL.md#end-to-end-smoke-validated-2026-05-12-hermes-v0130)
for the copy-pasteable smoke commands.

### Known limitations

- **Workflow node execution is not implemented yet.** The runner enqueues
  tasks onto per-agent JSON queues; nothing consumes them. The worker +
  node executor is Phase 4c on the roadmap.
- **`hermes plugins enable hermes_recipes` does not work** on the pure-pip
  install path. Hermes v0.13.0's `plugins enable` / `plugins list` only
  walk directory plugins, not entry-point plugins. Two workarounds:
  edit `~/.hermes/config.yaml` directly, or use the directory-shim
  install (`scripts/install_dir_plugin.sh`, added in 0.2.1).
- **4 media drivers deferred.** NanoBananaPro, RunwayVideo, KlingVideo,
  LumaVideo. Same pattern as `openai_image_gen.py`; trivial to add when
  needed.
- **Workspace scaffolding intentionally minimal.** The OpenClaw plugin's
  team scaffolder writes ~30 bootstrap files (priorities, DECISIONS,
  GLOSSARY, HEARTBEAT, GOALS, agent-outputs README, memory jsonl files,
  per-role files). The Python port writes the essential subset (TEAM.md,
  TICKETS.md, priorities, plan, status, QA_CHECKLIST when applicable); the
  rest can be added via the recipe's `files:` block on a per-recipe basis.

### Statistics

- **27 Python modules**, ~3,700 LOC
- **233 unit tests**, all passing
- **20 docs/MAPPING.md cross-references** into both source trees

## [0.1.0] — Phase 1 milestone (internal)

Initial recipe DSL parser (`recipe_frontmatter`, `template`, `recipe_id`,
`recipe_lint`, `constants`). 21 tests. Not released externally.
