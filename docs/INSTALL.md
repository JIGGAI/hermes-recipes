# Installing hermes-recipes into Hermes Agent

`hermes-recipes` is a Python package. After installing into the Hermes venv it
registers a `hermes recipes` CLI tree via the `hermes_agent.plugins` entry
point. End-to-end smoke (validated 2026-05-12 against Hermes v0.13.0):

```bash
hermes recipes --workspace-root /tmp/test dispatch \
    --team-id dev-team --request "Add a new clinic-team recipe" --owner lead
hermes recipes --workspace-root /tmp/test tickets --team-id dev-team --json
hermes recipes --workspace-root /tmp/test take     --team-id dev-team --ticket 1 --owner dev
hermes recipes --workspace-root /tmp/test handoff  --team-id dev-team --ticket 1
hermes recipes --workspace-root /tmp/test complete --team-id dev-team --ticket 1
```

…lands a ticket in `workspace-dev-team/work/done/0001-….md` with
`Status: done` and a `Completed:` timestamp.

There are two install paths. Pick one.

---

## Method A — Pip install (entry-point discovery)

**Best for:** most users. One command, no manual file management.

```bash
~/.hermes/venv/bin/pip install hermes-recipes      # production
# — or, for development —
~/.hermes/venv/bin/pip install -e /path/to/hermes-recipes
```

Then enable the plugin by adding it to `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - hermes_recipes
```

Verify the plugin loaded:

```bash
hermes recipes --help
```

If you see the `recipes` action tree, you're done. If argparse rejects
`recipes` as an "invalid choice", `plugins.enabled` doesn't include
`hermes_recipes` (or the pip install didn't land in Hermes's venv — see
*Troubleshooting* below).

### Why edit config.yaml by hand?

Hermes v0.13.0's `hermes plugins list` and `hermes plugins enable` only
discover **directory plugins** (files under `~/.hermes/plugins/`). The
runtime plugin loader DOES see pip entry-point plugins fine — but those
two CLI commands won't surface them. So with Method A:

- `hermes plugins list` → won't show `hermes_recipes` (UI gap)
- `hermes plugins enable hermes_recipes` → fails with "not installed or bundled" (UI gap)
- `hermes recipes …` → **works** (runtime sees it)

Either edit `config.yaml` directly, or use Method B below to also get the
nice CLI surface.

---

## Method B — Pip install + directory-plugin shim

**Best for:** users who want `hermes plugins list` / `hermes plugins enable`
to work normally. Adds a 2-file shim under `~/.hermes/plugins/` that points
at the pip-installed package.

```bash
# 1. Same pip install as Method A
~/.hermes/venv/bin/pip install hermes-recipes

# 2. Drop the shim
/path/to/hermes-recipes/scripts/install_dir_plugin.sh

# 3. Enable via the normal CLI
hermes plugins enable hermes_recipes

# 4. Verify
hermes plugins list                # hermes_recipes appears, status=enabled
hermes recipes --help
```

The shim creates exactly two files under `~/.hermes/plugins/hermes_recipes/`:

- `plugin.yaml` — copy of the package's manifest
- `__init__.py` — one-line `from hermes_recipes import register` shim

The package itself stays in Hermes's venv site-packages — the shim just
makes Hermes's directory scanner notice it.

To remove the shim:

```bash
/path/to/hermes-recipes/scripts/install_dir_plugin.sh --uninstall
```

(Or `rm -rf ~/.hermes/plugins/hermes_recipes/`.)

To uninstall the package itself:

```bash
~/.hermes/venv/bin/pip uninstall hermes-recipes
```

### Why this isn't pure "drop files in a folder"

A pure-directory install (no pip) would require copying the entire
`hermes_recipes/` package into `~/.hermes/plugins/hermes_recipes/`. That
works for simple plugins, but ours uses absolute imports
(`from hermes_recipes.tickets import …`) and depends on PyYAML 6+ being
present. Pip handles both — the directory shim is the lightest reliable
hand-off.

---

## Comparison

| Property | Method A (pip + config edit) | Method B (pip + dir shim) |
|---|---|---|
| Steps after `pip install` | edit `config.yaml` | run `install_dir_plugin.sh` + `hermes plugins enable` |
| `hermes plugins list` shows it | ❌ | ✅ |
| `hermes plugins enable` works | ❌ | ✅ |
| `hermes plugins disable` works | ❌ (delete from config) | ✅ |
| `hermes recipes …` works | ✅ | ✅ |
| Manages dependencies | ✅ (via pip) | ✅ (via pip) |
| Survives `~/.hermes/` reset | ✅ | ❌ (re-run install script) |
| Survives venv rebuild | ❌ (re-pip-install) | ❌ (both) |

**Recommendation:** use Method A if you live in `config.yaml` anyway. Use
Method B if you want the plugin to look first-class to Hermes's CLI.

---

## Use the CLI

```bash
hermes recipes tickets --team-id dev-team
hermes recipes --workspace-root /custom/path dispatch --team-id dev-team --request "…"
hermes recipes scaffold-team --recipe-id development-team --team-id dev-team \
    --provision-profiles --install-cron on
```

Note the **flag ordering**: `--workspace-root` and `--recipes-dir` belong to
the `recipes` sub-parser, so they go *between* `recipes` and the action
verb:

```bash
hermes recipes --workspace-root ~/work tickets --team-id dev-team   # ✓
hermes recipes tickets --workspace-root ~/work --team-id dev-team   # ✗ argparse error
```

The default workspace root is `~/.hermes/recipes/workspace/`.

---

## Troubleshooting

**`hermes recipes` returns "invalid choice" / "command not found".**
The plugin loaded but the runtime never imported it. Check:

1. `pip list | grep hermes-recipes` inside the Hermes venv — confirms install
2. `plugins.enabled` in `~/.hermes/config.yaml` includes `hermes_recipes`
3. `python -c 'from hermes_recipes import register; print(register)'` from
   the Hermes venv interpreter — confirms importability

**`pip install` succeeded but Hermes still doesn't see the plugin.**
Most often the install went into your shell's default Python rather than
Hermes's venv. Run:

```bash
head -1 $(which hermes)
```

…to find Hermes's interpreter, then use *that* pip explicitly:

```bash
$(head -1 $(which hermes) | sed 's|^#!||') -m pip install hermes-recipes
```

**Cron reconciliation errors with "hermes_agent.cron.jobs is not importable".**
You're running outside the Hermes venv, or the Hermes install is older
than the cron API surface we target. Run with `--install-cron off` for
now and report the version mismatch.

**Profile provisioning fails with "command not found: hermes".**
The `hermes` binary isn't on `$PATH` for the user running scaffolds. Add
it to `$PATH` or run scaffolds from a shell that already has it.

**End-to-end smoke** that exercises everything Phase 6 ships (validated
2026-05-12, Hermes v0.13.0):

```bash
export HERMES_HOME=/tmp/test-hermes-home && mkdir -p $HERMES_HOME

hermes recipes --workspace-root $HERMES_HOME/ws dispatch \
    --team-id dev-team --request "Add a new clinic-team recipe" --owner lead
hermes recipes --workspace-root $HERMES_HOME/ws tickets --team-id dev-team --json
hermes recipes --workspace-root $HERMES_HOME/ws take     --team-id dev-team --ticket 1 --owner dev
hermes recipes --workspace-root $HERMES_HOME/ws handoff  --team-id dev-team --ticket 1
hermes recipes --workspace-root $HERMES_HOME/ws complete --team-id dev-team --ticket 1

ls $HERMES_HOME/workspace-dev-team/work/done/
# expected: 0001-add-a-new-clinic-team-recipe.md (Status: done, Completed: <iso>)
```
