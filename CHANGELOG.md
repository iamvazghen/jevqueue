# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-10-29

The decision layer and the plugin are one project now.

### Changed

- **The decision layer moved into this package.** The judgment model, the typed questions, the
  distrust layer, the guard order and the framework adapters are now `jevqueue/` rather than a
  separate library. There is nothing to install alongside the plugin, and the two halves
  cannot drift apart.
- **No required dependencies.** The offline decision layer is pure standard library, and
  `httpx` -- needed only for the hosted model -- is an optional extra (`jevqueue[hosted]`).
  A plugin that needs an install step before it works is a plugin people do not install.
- **`/jevqueue:setup` no longer installs anything.** There is nothing to install. It now
  checks the installation, walks through the two settings, and runs a self-test that proves
  the queue refuses what it should.
- **The hook engine moved to `jevqueue/gate.py`**, and the catastrophic-operation floor to
  `jevqueue/policy.py`. The floor is now consulted *before* the decision layer rather than
  only when it is unavailable: a decision model that shrugs at `rm -rf /` should not overrule
  a list that short, and when the decision layer cannot be reached the floor is all that is
  left standing.
- **The command line moved into the package** (`jevqueue.cli`), so `pip install jevqueue`
  gives you `jevqueue` on your `PATH`.

### Added

- **A benchmark harness** (`bench/`): a labelled corpus, a runner, and a published result.
  It reports routing accuracy, the enforced rate and the latency spread, and a test fails if
  the code drifts away from the published numbers.
- **A `DecisionModel` protocol** in `client.py`, so the decision model is pluggable and the
  governor cannot tell a hosted model from a local one.
- **A `pyproject.toml`**, so the package is installable, buildable and publishable like any
  other Python project.
- **`python -m jevqueue`** and a `jevqueue` console script.

### Fixed

- The MCP server imported the old module name and would not start.
- The async client tests needed `asyncio_mode = "auto"` to run at all.
- The credential test was scoped too broadly: the plugin surface must never read a credential
  from the environment, but the framework adapters are library surface and read the key the
  way every Python library does. The test now says exactly that.

## [0.2.0] — 2026-10-28

Public availability in both ecosystems.

### Added

- A release workflow with PyPI Trusted Publishing, so publishing needs no stored token.
- `PRIVACY.md` and `NOTICE`: what the plugin runs, reads, sends, fetches and writes, and the
  attribution.
- A `userConfig` entry for the API key, marked `sensitive`.

### Changed

- The key is read from the plugin's own settings and from nowhere else. It used to fall back
  to `TYPESAFE_API_KEY` in the environment, which meant the plugin could pick up a secret
  already sitting in the user's shell and ship it to a server.
- The `.gitattributes` is scoped to the one file that genuinely needs it.
- CI validates with `--strict`.

## [0.1.0] — 2026-10-28

The first release.

### Added

- A `PreToolUse` hook that asks a decision model whether a step should run, and refuses the
  call when the answer is no.
- A `UserPromptSubmit` hook that caches the current request, because the transcript lags.
- Two skills, three commands, an MCP server, and a command line.
- Manifests for Claude Code, Codex CLI and the agents.md standard.

[0.3.0]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.3.0
[0.2.0]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.2.0
[0.1.0]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.1.0
