# jevqueue

A decision queue in front of an agent's tools. Before a tool runs, a decision model is asked
whether it should, and the call is refused when the answer is no.

Read `README.md` first. This file is the short version, for an agent that is about to work on
this repository.

## What this is

One package with two halves, and the difference matters:

- **The decision layer** (`jevqueue/client.py`, `decision.py`, `governor.py`, `questions.py`,
  `state.py`, `local.py`, `adapters/`) — a judgment model answers three typed questions, the
  generative model is constrained to that decision, and the result is checked against it.
- **The gate** (`jevqueue/gate.py`, `jevqueue/policy.py`) — a pre-tool hook asks the decision
  layer whether a pending step should run, and refuses it when the answer is no.

The plugin surface is `hooks/`, `commands/`, `skills/`, `mcp/`, `scripts/`, `bin/`. The library
surface is the `jevqueue/` package.

**The hook cannot constrain the provider's tool choice** — the provider is not ours to
constrain from a hook. What a hook can do is refuse a step the decision layer says should not
run, and escalate a risky one. That is the guardrail guarantee, not the enforcement one. Never
describe the plugin as providing the stronger one.

## The rules that matter

**Fail open.** Any internal error, unreadable transcript or missing dependency results in the
tool being *allowed*, with a diagnostic on stderr. Never raise a failure that blocks the
agent.

**Fail narrow.** The queue refuses a small number of steps. It does not steer every step, and
it never refuses on low confidence — an undecided decision is allowed, because a gate that
refuses on doubt is a wall.

**Leak nothing.** A refusal reason says what was refused and why. It never contains the
transcript, the tool input, the credential or a response body. That is a property the test
suite pins, not a promise.

**Advisory mode governs everything.** When the user sets `advisory`, nothing blocks — not the
risk gate, not the completion gate, not the catastrophic floor. The verdict is still computed
and still reported.

**The floor is under the model, not instead of it.** The catastrophic-operation list is
consulted *before* the decision layer, because a decision model that shrugs at `rm -rf /`
should not overrule a list this short — and because when the decision layer cannot be
reached, the floor is all that is left standing.

**The key comes from the plugin's settings, and from nowhere else.** `userConfig` with
`sensitive: true`, and the `CLAUDE_PLUGIN_OPTION_TYPESAFE_API_KEY` channel the runtime
exports for it. Never `os.environ["TYPESAFE_API_KEY"]` in the plugin's own code. A plugin
that quietly picks up a secret already sitting in the user's shell and ships it somewhere is
doing something the user did not agree to. A test pins this for the plugin surface; the
framework adapters are library surface and read the key the way every Python library does.

**No required dependencies.** The offline decision layer is pure standard library. `httpx` is
an extra, needed only for the hosted model. A plugin that needs an install step is a plugin
people do not install.

## Layout rules

- One repository, several manifests: `.claude-plugin/`, `.codex-plugin/`, `.agents/plugins/`.
  The engine is shared; only the manifest changes.
- `bin/` holds shims so `jevqueue` is on `PATH` while the plugin is enabled. `scripts/` holds
  the real entry points.
- The plugin's own state lives under `${CLAUDE_PLUGIN_DATA}`, never in the user's project and
  never in their system Python.

## Development

```bash
uv venv && uv pip install -e ".[dev,langchain,pydantic-ai]"
uv run pytest
uv run ruff check jevqueue tests hooks mcp scripts examples
uv run mypy
claude plugin validate --strict .
```

The suite is offline by design: no network, no API key, no provider. A test that needs a
credential does not run, and one that does not run is decoration.

A new gate needs a test that fails without it. Docstrings explain **why** a check exists, not
what the line below does.

## The measurement, and the caveat

`bench/` holds a labelled corpus and a harness that reports routing accuracy, the enforced
rate and the latency spread. A published run is committed at
`bench/results/local-rules-baseline.json`, and a test fails if the code drifts away from it.

Two numbers in that report are worth reading twice. The rules picked the right tool every
time and acted on only 71% of them — the gap is the honest part, because a correct decision
that is not enforced is worth much less than a correct decision that is. And the two
`risk_stop` cases never reached the provider at all, which is the whole exercise in one line.
