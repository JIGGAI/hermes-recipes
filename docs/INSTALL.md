# Installing hermes-recipes into Hermes Agent

This package registers itself as a Hermes plugin via the `hermes_agent.plugins`
entry-point group. After installing into the Hermes venv, Hermes's plugin
loader discovers it automatically — there's no `~/.hermes/plugins/`
directory to manage.

## Prerequisites

- Hermes Agent installed (`curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash`)
- The Hermes Python venv reachable on disk (usually `~/.hermes/venv/`)

## Install

### 1. Drop the package into the Hermes venv

From a checkout of this repo:

```bash
~/.hermes/venv/bin/pip install /path/to/hermes-recipes
```

For development (editable install — picks up edits without reinstalling):

```bash
~/.hermes/venv/bin/pip install -e /path/to/hermes-recipes
```

Verify the entry point landed:

```bash
~/.hermes/venv/bin/python -c '
import importlib.metadata as md
eps = md.entry_points()
group = eps.select(group="hermes_agent.plugins") if hasattr(eps, "select") else []
for ep in group:
    print(f"  {ep.name} = {ep.value}")
'
```

You should see `hermes_recipes = hermes_recipes`.

### 2. Enable the plugin

Hermes plugins are **opt-in by default**. Add `hermes_recipes` to the
`plugins.enabled` array in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - hermes_recipes
```

> **Gotcha:** As of Hermes v0.13.0, `hermes plugins enable hermes_recipes`
> fails with *"Plugin 'hermes_recipes' is not installed or bundled."* and
> `hermes plugins list` does **not** show entry-point plugins — both of those
> CLI commands only walk the directory-plugin source. The runtime plugin
> loader DOES see entry-point plugins; you just have to edit
> `~/.hermes/config.yaml` by hand to enable yours.

### 3. Verify the plugin loaded

`hermes plugins list` won't display entry-point plugins (see gotcha above),
so probe it directly via the CLI surface it registered:

```bash
hermes recipes --help
```

If you see the `recipes` action-tree, the plugin loaded successfully. If
argparse rejects `recipes` as an "invalid choice", `plugins.enabled` doesn't
include `hermes_recipes` (or the pip install didn't land in Hermes's venv).

### 4. Flag ordering

The `--workspace-root` and `--recipes-dir` flags belong to the `recipes`
sub-parser, so they go **between** `recipes` and the action verb:

```bash
hermes recipes --workspace-root ~/work/team-x tickets --team-id dev-team
```

Putting `--workspace-root` after the action verb (`tickets`) makes argparse
treat it as an unrecognized top-level arg.

### 5. Use the CLI

```bash
hermes recipes tickets --team-id dev-team
hermes recipes dispatch --team-id dev-team --request "Add a new clinic-team recipe"
hermes recipes scaffold-team --recipe-id development-team --team-id dev-team \
    --provision-profiles --install-cron on
```

The default workspace root is `~/.hermes/recipes/workspace/`. Override with
`hermes recipes --workspace-root /some/path <action> …` for testing.

## End-to-end smoke (validated 2026-05-12, Hermes v0.13.0)

```bash
hermes recipes --workspace-root /tmp/test-ws dispatch \
    --team-id dev-team --request "Add a new clinic-team recipe" --owner lead
hermes recipes --workspace-root /tmp/test-ws tickets --team-id dev-team --json
hermes recipes --workspace-root /tmp/test-ws take     --team-id dev-team --ticket 1 --owner dev
hermes recipes --workspace-root /tmp/test-ws handoff  --team-id dev-team --ticket 1
hermes recipes --workspace-root /tmp/test-ws complete --team-id dev-team --ticket 1
```

…lands a ticket in `workspace-dev-team/work/done/0001-add-a-new-clinic-team-recipe.md`
with `Status: done` and a `Completed:` timestamp.

## Uninstall

```bash
~/.hermes/venv/bin/pip uninstall hermes-recipes
```

…and remove `hermes_recipes` from `plugins.enabled` in `~/.hermes/config.yaml`.

## Troubleshooting

**`hermes plugins list` doesn't show `hermes_recipes`.**
Make sure you installed into the *Hermes* venv, not your shell's default
Python. `which hermes` + `head -1 $(which hermes)` typically points at the
interpreter Hermes is using.

**`hermes recipes ...` returns "command not found" / argparse rejects the
subcommand.**
The plugin loaded but the CLI registration didn't run. Set
`HERMES_PLUGINS_DEBUG=1 hermes plugins list` to see why — most often it
means the plugin is discovered but not in `plugins.enabled`.

**Cron reconciliation errors with "hermes_agent.cron.jobs is not importable".**
You're running outside the Hermes venv (so the `cron.jobs` module isn't on the
path) or the Hermes install is older than the cron API surface we target. Run
with `--install-cron off` for now and report the version mismatch.

**Profile provisioning fails with "command not found: hermes".**
Either `hermes` is not on `$PATH` for the user running scaffolds, or you're
inside a sandbox that's hiding it. Set the `hermes` binary path explicitly by
running the scaffold command in a shell that has Hermes in `$PATH`.

## Alternative: directory plugin (advanced)

If you can't `pip install` into the Hermes venv (read-only filesystem,
sandboxed install, etc.), you can drop a directory plugin under
`~/.hermes/plugins/hermes_recipes/`:

1. Copy the entire `hermes_recipes/` package directory there.
2. Copy `plugin.yaml` alongside it (so it lives at
   `~/.hermes/plugins/hermes_recipes/plugin.yaml`).
3. Add `hermes_recipes` to `plugins.enabled` in `~/.hermes/config.yaml`.

This path requires the same Python dependencies (PyYAML 6+) to be present in
whatever interpreter Hermes uses. It's identical to the pip path at runtime;
the entry-point install is preferred because pip handles the dependency
install for you.
