#!/usr/bin/env python
"""Generate the documentation site's sources from the README and the docs pages.

The site is built from ``site_src/``, which is generated rather than committed, so the
README and the docs pages cannot drift from what the site shows.

Every relative link is rewritten:

* ``docs/architecture.md`` becomes ``architecture.md``, because inside the site the page is
  a sibling rather than a subdirectory.
* Anything else that points outside the site -- ``LICENSE``, ``examples/``, ``skills/``,
  ``src/``, ``tests/`` -- becomes an absolute GitHub URL, because those files are not part of
  the site build.

An unrewritten link that escapes the site makes ``mkdocs build --strict`` fail, which is why
this script exists rather than a copy.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DOCS = ROOT / "docs"
SITE = ROOT / "site_src"

REPOSITORY = "https://github.com/iamvazghen/jevqueue"

#: The generated home page.
INDEX = SITE / "index.md"

#: A markdown link to a relative path.
LINK = re.compile(r"\]\((?!https?://|mailto:|#)([^)\s]+)([^)]*)\)")


def rewrite(markdown: str) -> str:
    """Return ``markdown`` with its relative links rewritten for the site."""

    def replace(match: re.Match[str]) -> str:
        target, tail = match.group(1), match.group(2)
        path, _, anchor = target.partition("#")
        if not path:
            return match.group(0)
        path = (
            path[len("docs/"):]
            if path.startswith("docs/")
            else f"{REPOSITORY}/blob/main/{path}"
        )
        return f"]({path}{'#' + anchor if anchor else ''}{tail})"

    return LINK.sub(replace, markdown)


def main() -> int:
    if not README.exists():
        print(f"missing {README}", file=sys.stderr)
        return 1

    SITE.mkdir(parents=True, exist_ok=True)
    written = []

    index = SITE / "index.md"
    index.write_text(rewrite(README.read_text(encoding="utf-8")), encoding="utf-8")
    written.append(index.name)

    for page in sorted(DOCS.glob("*.md")):
        if page.name == "index.md":
            continue
        target = SITE / page.name
        target.write_text(rewrite(page.read_text(encoding="utf-8")), encoding="utf-8")
        written.append(target.name)

    print(f"wrote {len(written)} site pages to {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
