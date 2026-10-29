# Decision layer changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-10-27

The release that makes the package reachable and runnable. Two of the changes are about
reach — it could not be installed, and it could not be found — and one is about depth: a
decision model that needs no account.

### Added

- **`LocalDecisionModel`** — an offline decision model that answers the same three typed
  questions with deterministic rules. It implements the same `DecisionModel` contract as
  `JevClient`, so it drops into a `Governor` wherever the hosted client does, and the whole
  machinery — the constraint, the verification, the gates — runs with **no credential and no
  network**. It is the hand-written-rules baseline described in
  [docs/comparison.md](docs/comparison.md), packaged: not a judgment model, and its confidence
  is rule-match strength rather than a calibrated probability.
  See [docs/local-decision-model.md](docs/local-decision-model.md).
- **`DecisionModel`** — a `Protocol` for the one method the governor needs from a decision
  model. `Governor` now accepts it, which is what makes the decision model pluggable.
- **A LangChain adapter** (`adapters/langchain.py`) — `GovernedChatModel`, a chat-model
  wrapper. `bind_tools` binds to the governed model rather than to the provider, so the
  governor stays in the loop; a named `tool_choice` is then applied as a provider-level
  constraint and verified. Tested against a real `BaseChatModel`. Install with
  `jevqueue[langchain]`.
- **`python -m jevqueue`** — the demo, with no key, no network and no provider: the
  provider constrained to the selected tool, a provider that ignores the constraint refused
  before anything executes, and a destructive tool stopped at the risk gate.
- **A benchmark harness** (`bench/`) — a labelled corpus with the expected route written by
  hand, reporting routing accuracy, the enforced rate, latency percentiles and the path
  distribution. A published run of the offline baseline is committed at
  `bench/results/local-rules-baseline.json`. The point is the harness rather than the
  number: it is how two decision models get compared on your traffic.
- **A PyPI release workflow** using Trusted Publishing, so a version reaches PyPI without a
  stored API token. Publishing a GitHub Release is the trigger.
- **A documentation site** — MkDocs configuration, a `Pages` workflow, and a script that
  generates the site home page from the README so the two cannot drift apart.
- **An agent skill** (`skills/jev-decision-layer-adapter/`) — the Host protocol, the four
  mandatory tests and the two reference implementations, as a recipe an agent can follow.
- **Issue templates, labels, and a seeded backlog** — a bug template built around the turn
  rather than the feature, an adapter-request template that asks how the constraint would be
  applied, and five `good first issue` items covering LangGraph, CrewAI, AutoGen, a
  TypeScript client, and OpenTelemetry spans.
- **[docs/ecosystem-submissions.md](docs/ecosystem-submissions.md)** — ready-to-paste entries
  for the three Jev ecosystem directories, in each one's own format.

### Changed

- The package description now leads with the problem it solves rather than the mechanism it
  uses, and the keyword set covers the terms someone would actually search for.
- The README leads with the two failures this addresses, gains a **"Works with"** table, a
  **"When not to use it"** section, and a keyless quickstart — and says plainly that deferring
  tool schemas is no longer a differentiator now that Tool Search ships in Claude Code. The
  durable ground is enforcement and the independent completion gate.

### Fixed

- The package was never published. CI built a wheel and uploaded it as an artifact, with no
  publish job and no release trigger, so `pip install jevqueue` failed with "no matching
  distribution found" — the README's very first command. The release workflow above fixes it.
- The LangChain and Pydantic AI adapter tests were **skipped in CI**, because the frameworks
  were not in the development extras. They are now installed in CI, so both adapters are
  tested against the real frameworks rather than only by their author.
- The `Host` protocol was documented as **six methods** throughout the project. It has seven —
  `interrupted()` was added after the count was first written down, and the number was never
  revised. Corrected in the protocol docstring, the docs, the NOTICE, the adapter issue
  template and the agent skill.

[0.2.0]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.2.0

## [0.1.0] — 2026-10-08

First release. Pre-1.0: the `Host` protocol and `GovernorConfig` fields may still change, and
breaking changes will be called out here.

### Added

- **`Governor`** — a seven-guard decision loop over one System One call per step. Nine recorded
  paths (`static_tool`, `tool_arguments`, `final_response`, `clarification`, `risk_stop`,
  `delegated`, `completion_held`, `truncated_hold`, `error`), each with the probabilities, the
  resolved model id, and the decision latency behind it.
- **Enforcement, not advice.** The host constrains the provider to the selected tool, and the
  result is checked against it — a provider that ignores `tool_choice` raises before anything
  executes. The inverse also holds: a tool call after a `finish` decision is blocked.
- **An independent completion gate.** `goal_met` is a separate question in the same request, so
  it cannot see the `action` answer; a `finish` below `completion_threshold` is refused.
- **A truncation hold.** A `finish` decided on a partial view of the transcript is refused,
  because the dropped history is where unfinished work would be.
- **A risk gate ahead of the confidence gate**, so uncertainty about risk never falls through to
  the generative model.
- **A distrust layer** (`decision.py`): rejects non-finite and `bool` probabilities, a
  distribution over the wrong option set or one that does not sum to one, and a choice that is
  not its own argmax; clamps reported confidence to the winning option's own mass.
- **A bounded state projection** (`state.py`) enforced on *serialized* length, built fresh per
  step, which never mutates or reorders the canonical transcript.
- **`JevClient` / `AsyncJevClient`** — one retry for `429`/`529` only, distinguishable `401`
  and `403` diagnoses, injectable transport, and no credential or response body in any
  exception message.
- **`GovernorConfig`** — validated at construction, with unknown keys an error rather than a
  warning.
- **`static_tools`** — zero-generative-cost execution for fixed payloads, validated against the
  tool's live JSON schema, remote `$ref` refused, and only on a `low` risk verdict.
- **Adapters**: `openai_chat` (any OpenAI-compatible loop), `hermes` (a six-line seam),
  `pydantic_ai` (`GovernedModel`, a `WrapperModel` that constrains via `function_tools` and
  `allow_text_output`), and `openclaw` (`OpenClawRouter` — fleet routing with `argv`-only
  dispatch, the message in a file, no `--deliver`, and an environment allowlist built from
  nothing).
- 210 hermetic tests — no network, no API key, no provider. `scripts/verify_live.py` covers the
  live path on demand.
- Documentation: architecture and the reasoning for each guard's position, Hermes install,
  limits, comparison, roadmap, and a guide to writing an adapter.

### Notes on provenance

This supersedes an earlier approach that forked Hermes Agent to add roughly 670 lines. The fork
meant every upstream release had to be merged rather than installed alongside, the decision
layer could not be tested without all of Hermes, and users of other frameworks could not use
any of it. This package contains **no Hermes source** and integrates through a seven-method host
protocol instead, so the decision layer and the agent framework version independently.

### Known gaps

Carried from [docs/limits.md](docs/limits.md) so they are visible in release notes:

- Streaming is not governed; `request_stream` falls through to the wrapped model.
- `Governor` is synchronous, so the Pydantic AI adapter runs it on a worker thread.
- The Pydantic AI, Hermes and OpenClaw adapters are **not verified in CI against live
  frameworks or a live gateway** — their logic and transport properties are tested, real round
  trips are not.
- Vendor latency and price figures are not reproduced here as measurements.

[0.1.0]: https://github.com/iamvazghen/jevqueue/releases/tag/v0.1.0
