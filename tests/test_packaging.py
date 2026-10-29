"""The packaging metadata has to agree with the code, and the docs have to build.

Both of these fail silently. A version that says one thing on PyPI and another in
``jevqueue.__version__`` is the kind of thing nobody notices until a bug report arrives
with the wrong version in it. A documentation link that points nowhere is the kind of thing
nobody notices until a reader gives up.

No TOML parser is used here on purpose: ``tomllib`` only exists from Python 3.11, and this
package supports 3.10.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _project_field(name: str) -> str:
    """Read one scalar field out of the ``[project]`` table of pyproject.toml."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, f"pyproject.toml has no {name}"
    return match.group(1)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "build_docs_index", ROOT / "scripts" / "build_docs_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheVersion:
    def test_the_package_version_and_the_module_version_agree(self):
        from jevqueue import __version__

        assert __version__ == _project_field("version")

    def test_the_changelog_has_an_entry_for_the_current_version(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        assert f"## [{_project_field('version')}]" in changelog

    def test_the_readme_points_at_the_pypi_project(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "pypi.org/project/jevqueue" in readme


class TestTheDocumentationIndex:
    def test_the_generator_rewrites_repository_links_for_the_site(self):
        module = _load_generator()

        rewritten = module.rewrite(
            "See [docs/limits.md](docs/limits.md) and [LICENSE](LICENSE) and "
            "[example](examples/local_first.py) and [skill](skills/some-skill/SKILL.md)."
        )

        assert "](limits.md)" in rewritten
        assert "blob/main/LICENSE" in rewritten
        assert "blob/main/examples/local_first.py" in rewritten
        assert "blob/main/skills/some-skill/SKILL.md" in rewritten
        assert "](docs/limits.md)" not in rewritten

    def test_no_readme_link_points_outside_the_site_unrewritten(self):
        """A link that escapes the site and is not rewritten breaks ``mkdocs --strict``."""
        module = _load_generator()
        module.main()
        rewritten = module.rewrite((ROOT / "README.md").read_text(encoding="utf-8"))

        escaping = re.findall(r"\]\((?!https?://|#)([^)]+)\)", rewritten)
        for target in escaping:
            path = target.split("#")[0]
            if not path:
                continue
            assert (module.SITE / path).exists(), (
                f"the site links to {path}, which is not a page in the site"
            )

    def test_the_generator_produces_the_site_home_page(self):
        module = _load_generator()

        assert module.main() == 0
        assert module.INDEX.exists()
        assert "jevqueue" in module.INDEX.read_text(encoding="utf-8")

    def test_every_relative_link_in_the_readme_resolves(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        missing = []
        for target in re.findall(r"\]\((?!https?://|#)([^)]+)\)", readme):
            path = target.split("#")[0]
            if not path:
                continue
            if not (ROOT / path).exists():
                missing.append(path)

        assert missing == []

    def test_the_site_nav_points_at_files_that_exist(self):
        module = _load_generator()
        module.main()

        config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        pages = re.findall(r":\s*([a-z0-9\-]+\.md)\s*$", config, re.MULTILINE)

        assert pages, "the nav is empty, which means the regex stopped matching"
        for page in pages:
            assert (module.SITE / page).exists(), f"mkdocs nav points at a missing {page}"
