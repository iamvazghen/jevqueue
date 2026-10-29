# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.2] — 2026-10-29

The MCP server was shipped but never registered.

### Fixed

- **Claude Code, Codex and GitHub Copilot never saw `jevqueue_decide`.** The plugin shipped
  `mcp/jevqueue_mcp.py`, and the awareness document injected into every session told the
  agent to call `jevqueue_decide` — but no manifest declared the server, so the tool did
  not exist. The agent was told to ask a question it could not ask. The manifests now
  declare it, and `.mcp.json` at the plugin root registers it automatically.
- **A launcher, because one command has to work on three platforms.** The decision layer
  is Python and the agents that speak MCP are Node programs; `python` and `python3` are
  not the same interpreter, and on macOS `python` may not exist at all. `bin/jevqueue-mcp.mjs`
  finds an interpreter that is actually there and hands the process over, inheriting stdio
  so the JSON-RPC framing is untouched.
- **Codex gets its own configuration file.** Its legacy plugin parser resolves a relative
  `cwd` against the plugin root but does not expand placeholders in MCP arguments, so a
  single shared file would have handed it a path that cannot exist.

### Added

- A test that the awareness document names the tool the MCP server actually exposes, and
  that every manifest which should carry an MCP server does.

[0.5.2]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.5.2

## [0.5.1] — 2026-10-29

The distribution stops pretending to be on PyPI, and the license says exactly what it covers.

### Fixed

- **The project pointed at a PyPI package that does not exist.** There is no PyPI project —
  nothing was ever published, and the publish workflow was removed when the plugin stopped
  needing an install step. The README's badges, the install one-liners in the README and five
  documentation pages, the demo's own docstring, and the three adapter error messages all
  said `pip install jevqueue`, which fails. They now say
  `pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"`, which works.
- **The manifest versions had drifted.** The GitHub Copilot manifest said `0.4.0` and the
  Gemini extension said `0.3.0` while everything else said `0.5.0`. The manifests are the
  plugin's public contract, and a version is the first thing a reader checks, so all of them
  now agree — and a test holds them there.
- **The changelog claimed a release workflow that did not exist.** Two entries described a
  PyPI Trusted Publishing workflow as though it shipped. It never ran, and it is gone.

### Changed

- **The license statement is precise.** MIT covers everything in this repository: the decision
  layer, the gate, the hook scripts, the manifests, the skills, the MCP server and the docs.
  No third-party code is vendored, and the package has no required dependencies. The hosted
  *Jev* model is a separately hosted service under TypeSafe's terms — not distributed here,
  with no weights, keys or credits — and the offline rules baseline that *is* here is covered
  by the MIT license.

### Added

- A test that every manifest version matches the package version, and that no document
  anywhere in the project contains a `pip install jevqueue` that cannot work.

[0.5.1]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.5.1

## [0.5.0] — 2026-10-29

The plugin now explains itself to the agent that is using it.

### Added

- **An awareness document, injected automatically.** A `SessionStart` hook (Claude Code,
  Codex) and a `BeforeAgent` hook (Gemini) put a short document into the session at
  start-up, so the agent knows the queue exists, when to ask it, and what to do when it says
  no -- without anybody having to explain it. A plugin whose only artefact is a README has
  already failed: the agent does not read READMEs, it reads what is in its context.
- **`jevqueue/awareness.py`** -- the injected text, in two lengths. The short one is what goes
  into a session and is kept under 2,500 characters on purpose, because it is paid for in
  every conversation, including the ones where the queue has nothing to do.
- **[docs/install.md](docs/install.md)** -- install, enable, test and "how it gets used", for
  every agent in the matrix.
- **[docs/benefits.md](docs/benefits.md)** -- what the *owner* of the agent gets, with
  measured token numbers rather than assertions.
- **Tests for both** -- the injected text and the documentation are pinned against each other,
  so the two cannot quietly disagree.

### Measured

The token numbers in the documentation are measured, not asserted. On the benchmark's
eight-tool corpus:

| | Input | Output |
|---|---|---|
| A generative router choosing a tool | ~674 (schemas + state) | the reasoning tokens to emit a name |
| **The decision layer** | **215** (state only) | **0** |
| A step served from `static_tools` | — | **0** -- no model is called |

The 460-token gap is the tool schemas: a generative router has to *receive* every tool
definition to choose between them, while the decision layer scores criteria against them so
they never enter the context. That gap grows with the size of the toolset.

### Fixed

- The README had lost its documentation index in the merge. Restored, with the new pages.

[0.5.0]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.5.0

## [0.4.0] — 2026-10-29

The plugin stops being a Claude Code plugin and starts being a plugin for the CLI agent
ecosystem.

### Added

- **A Gemini CLI extension** (`gemini-extension.json`): the MCP server, the skills, and a
  `BeforeTool` hook in Gemini's dialect. Verified to install — the extension registers the
  `jevqueue` MCP server and picks up both skills.
- **An opencode plugin** (`.opencode/plugins/jevqueue.mjs`): opencode has no hook
  configuration file, a plugin *is* the hook, so this one subscribes to
  `tool.execute.before` and throws to refuse the call.
- **Rules files for seven more agents** — Cursor, Windsurf, Kiro, Cline, OpenClaw, GitHub
  Copilot and the `agents.md` standard — all generated from one body by
  `scripts/sync_agent_rules.py`, so the guidance cannot drift between agents.
- **A GitHub Copilot plugin** (`.github/plugin/`): its own marketplace and manifest, pointing
  at the same commands, skills and hooks.
- **Two hook dialects, two files.** Claude Code and Codex speak `PreToolUse`; Gemini speaks
  `BeforeTool`; the same gate script answers both by looking at the event name it is given.
- **The catastrophic floor now knows every runtime's shell tool** — `Bash`, `run_shell_command`,
  `bash`, `run_terminal_cmd` and the rest — so a floor written for one agent is not a floor
  that only works in one agent.
- **A test per agent surface** (`tests/test_agent_surfaces.py`): every rules file, every
  manifest, every dialect, and every shell-tool name, so a claim in the README cannot quietly
  stop being true.

### Changed

- CI now validates against **both** ecosystems: `claude plugin validate` and
  `gemini extensions validate`.

### Known

- Gemini CLI 0.45 does not load an extension's hooks from `settings.json`, and its
  `hooks/hooks.json` path collides with Claude Code's. The dialects are therefore kept in
  separate files, and Claude Code reports one harmless warning for the Gemini event it finds
  in `hooks/hooks.json`. The hook Claude Code runs is the one its manifest declares.

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
- **The command line moved into the package** (`jevqueue.cli`), so installing `jevqueue` from
  the repository gives you `jevqueue` on your `PATH`.

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

- A release workflow with PyPI Trusted Publishing, so publishing would need no stored token.
  It never ran — the package was never published — and the workflow was removed in 0.5.1,
  when distribution moved to the repository itself.
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
