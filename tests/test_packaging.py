"""The packaging metadata has to agree with the code, and the docs have to build.

All of these fail silently. A version that says one thing in a manifest and another in
``jevqueue.__version__`` is the kind of thing nobody notices until a bug report arrives
with the wrong version in it. A documentation link that points nowhere is the kind of thing
nobody notices until a reader gives up. An install command for a package that was never
published is the kind of thing nobody notices until somebody tries it.

No TOML parser is used here on purpose: ``tomllib`` only exists from Python 3.11, and this
package supports 3.10.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest

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

    def test_the_readme_does_not_point_at_a_pypi_project(self):
        """There is no PyPI project, and there never was one.

        A link to a package that does not exist is not a shortcut -- it is a broken promise
        printed at the top of the README, and the reader finds out at the install step.
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        assert "pypi.org/project/jevqueue" not in readme
        assert "img.shields.io/pypi" not in readme

    def test_the_readme_says_how_to_install_the_library(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        assert 'pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"' in readme

    def test_every_manifest_version_is_the_package_version(self):
        """The manifests are the plugin's public contract, and the version is the first
        thing a reader checks.

        The GitHub Copilot manifest and the Gemini extension both drifted a release or two
        behind without anybody noticing, because nothing held them to the package version.
        """
        version = _project_field("version")
        manifests = [
            ".claude-plugin/plugin.json",
            ".codex-plugin/plugin.json",
            ".github/plugin/plugin.json",
            "gemini-extension.json",
            "package.json",
        ]

        for name in manifests:
            data = json.loads((ROOT / name).read_text(encoding="utf-8"))
            assert data["version"] == version, (
                f"{name} says {data['version']}, the package says {version}"
            )


class TestTheInstallCommands:
    """Every install command in the project has to work.

    The package is not on PyPI, so an install that names only ``jevqueue`` is an install
    that fails -- in the README, in a documentation page, and in the error message a
    developer sees when an adapter's extra is missing.

    The scan covers everything that can reach a reader. ``tests/`` is excluded because it
    is not shipped, and because this file is the checker: it necessarily contains the
    strings it looks for.
    """

    #: Where an install command can live.
    SUFFIXES: ClassVar[tuple[str, ...]] = (".md", ".py")

    #: The repository the package is installed from.
    REPOSITORY: ClassVar[str] = "git+https://github.com/iamvazghen/jevqueue.git"

    #: Changelogs record what happened, including commands that did not work at the time.
    EXEMPT: ClassVar[frozenset[str]] = frozenset(
        {"CHANGELOG.md", "decision-layer-changelog.md"}
    )

    #: Directories that are not shipped, so nothing in them reaches a reader.
    UNSHIPPED: ClassVar[frozenset[str]] = frozenset(
        {".git", ".venv", "site", "site_src", "dist", "node_modules", "__pycache__", "tests"}
    )

    def _sources(self) -> list[Path]:
        sources: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [name for name in dirnames if name not in self.UNSHIPPED]
            for name in filenames:
                if not name.endswith(self.SUFFIXES) or name in self.EXEMPT:
                    continue
                sources.append(Path(dirpath) / name)
        return sources

    def test_no_install_command_omits_the_repository(self):
        offenders = []
        for path in self._sources():
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "pip install" not in line or "jevqueue" not in line:
                    continue
                if self.REPOSITORY in line:
                    continue
                offenders.append(f"{path.relative_to(ROOT)}: {line.strip()}")

        assert offenders == [], "install commands that cannot work:\n" + "\n".join(offenders)

    def test_the_documentation_does_not_point_at_a_pypi_project(self):
        offenders = []
        for path in self._sources():
            text = path.read_text(encoding="utf-8")
            if "pypi.org/project/jevqueue" in text or "img.shields.io/pypi" in text:
                offenders.append(str(path.relative_to(ROOT)))

        assert offenders == [], f"pages still pointing at a PyPI project: {offenders}"


class TestTheMcpWiring:
    """The MCP server has to be *registered*, not merely shipped.

    The awareness document tells every agent that it can ask ``jevqueue_decide``. If the
    plugin does not declare the server, that instruction points at a tool that does not
    exist -- which is worse than saying nothing, because the agent will try to call it.
    """

    def test_the_claude_manifest_declares_the_mcp_server(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

        assert manifest["mcpServers"] == "./.mcp.json"

    def test_the_mcp_configuration_names_the_launcher(self):
        config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))

        server = config["mcpServers"]["jevqueue"]
        assert server["command"] == "node"
        assert any("jevqueue-mcp.mjs" in argument for argument in server["args"])

    def test_the_launcher_is_shipped(self):
        assert (ROOT / "bin" / "jevqueue-mcp.mjs").is_file()

    def test_the_codex_manifest_declares_its_own_mcp_configuration(self):
        """Codex's legacy plugin parser does not expand placeholders in MCP arguments,
        so it gets a configuration that resolves the path through the working directory
        instead. One file cannot satisfy both parsers, and a half-expanded path is a
        server that never starts.
        """
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        assert manifest["mcpServers"] == "./.codex-plugin/mcp.json"

        config = json.loads((ROOT / ".codex-plugin" / "mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["jevqueue"]
        assert server["cwd"] == "."
        assert server["args"] == ["bin/jevqueue-mcp.mjs"]

    def test_the_copilot_manifest_declares_the_mcp_server(self):
        manifest = json.loads(
            (ROOT / ".github" / "plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        assert manifest["mcpServers"] == "./.mcp.json"

    def test_the_launcher_is_valid_javascript(self):
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not installed here, so the launcher cannot be parsed")

        result = subprocess.run(
            [node, "--check", str(ROOT / "bin" / "jevqueue-mcp.mjs")],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr

    def test_the_awareness_document_names_the_tool_the_server_exposes(self):
        """The agent is told to call one tool by name. That name has to be the one the
        server actually exposes, or the instruction is a dead end.
        """
        from jevqueue.awareness import SHORT_AWARENESS

        server = (ROOT / "mcp" / "jevqueue_mcp.py").read_text(encoding="utf-8")
        match = re.search(r'"name":\s*"([a-z_]+)"', server)

        assert match is not None, "the MCP server declares no tool name"
        assert match.group(1) in SHORT_AWARENESS


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
