#!/usr/bin/env bash
# Install hermes-recipes as a Hermes *directory plugin* so it shows up in
# `hermes plugins list` and `hermes plugins enable` works normally.
#
# This is a thin shim on top of a pip install — it just creates
# ~/.hermes/plugins/hermes_recipes/{plugin.yaml,__init__.py}. The actual
# package still lives in the Hermes venv's site-packages (you must
# `pip install hermes-recipes` first).
#
# Why this exists:
#   Hermes v0.13.0's `plugins list` and `plugins enable` CLI commands only
#   discover directory-based plugins. The runtime plugin loader sees pip
#   entry-point plugins fine — but if you want the CLI surface to
#   acknowledge yours, you need a directory entry too.
#
# Usage:
#   scripts/install_dir_plugin.sh                # uses default ~/.hermes
#   HERMES_HOME=/path scripts/install_dir_plugin.sh
#   scripts/install_dir_plugin.sh --uninstall    # remove the shim

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/hermes_recipes"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "--uninstall" ]]; then
  if [[ -d "$PLUGIN_DIR" ]]; then
    rm -rf "$PLUGIN_DIR"
    echo "Removed $PLUGIN_DIR"
  else
    echo "Nothing to remove at $PLUGIN_DIR"
  fi
  exit 0
fi

mkdir -p "$PLUGIN_DIR"

# Copy the canonical manifest from the package root.
cp "$REPO_ROOT/plugin.yaml" "$PLUGIN_DIR/plugin.yaml"

# Write the shim __init__.py that delegates to the pip-installed package.
cat > "$PLUGIN_DIR/__init__.py" <<'PY'
"""Hermes directory-plugin shim for hermes-recipes.

Delegates to the pip-installed `hermes_recipes` package. Install the
package into Hermes's venv with:

    ~/.hermes/venv/bin/pip install hermes-recipes

…or for development:

    ~/.hermes/venv/bin/pip install -e /path/to/hermes-recipes
"""
from hermes_recipes import register  # noqa: F401
PY

echo "Installed Hermes directory plugin at: $PLUGIN_DIR"
echo
echo "Next steps:"
echo "  1. ~/.hermes/venv/bin/pip install hermes-recipes   # if you haven't already"
echo "  2. hermes plugins enable hermes_recipes"
echo "  3. hermes recipes --help"
