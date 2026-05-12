"""Tiny, safe template renderer: replaces {{key}} with vars[key].

No conditionals, no eval. Port of clawrecipes/src/lib/template.ts.
"""

import re
from typing import Mapping

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def render_template(raw: str, variables: Mapping[str, str]) -> str:
    """Substitute every {{key}} in *raw* with variables[key].

    Missing keys render as the empty string (matches the TS behavior).
    """

    def _sub(match: re.Match[str]) -> str:
        value = variables.get(match.group(1))
        return value if isinstance(value, str) else ""

    return _TEMPLATE_RE.sub(_sub, raw)
