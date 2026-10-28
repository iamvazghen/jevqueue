# jevqueue

A decision queue in front of an agent's tools. Before a tool runs, a decision model is asked
whether it should, and the call is refused when the answer is no.

Read `README.md` first. This file is the short version, for an agent that is about to work on
this repository.

## What this is

A **plugin** for CLI agents. The engine is the decision layer; the plugin is the surface that
puts it in front of tool calls.

- `hooks/jevqueue_gate.py` — the `PreToolUse` hook. It reads the hook payload on stdin and
  prints a deny decision on stdout, or exits silently.
- `hooks/jevqueue_prompt.py` — the `UserPromptSubmit` hook. It caches the current request,
  because the transcript lags and by the time the first tool call fires the newest user turn
  in the transcript is usually the *previous* one.
- `jevqueue/core.py` — the engine. Two engines: the real decision layer (`jev-governor`) and
  a dependency-free fallback policy.
- `skills/` — the portable core. Two skills that work in any agent that reads `SKILL.md`.
- `mcp/jevqueue_mcp.py` — the portable core as an MCP server, for agents that cannot hook.
- `commands/` — `/jevqueue:setup`, `/jevqueue:check`, `/jevqueue:status`.

## The rules that matter

**Fail open.** Any internal error, unreadable transcript or missing dependency results in the
tool being *allowed*, with a diagnostic on stderr. Never raise a failure that blocks the
agent.

**Fail narrow.** The queue refuses a small number of steps. It does not steer every step, and
it never refuses on low confidence — an undecided decision is allowed, because a gate that
refuses on doubt is a wall.

**Leak nothing.** A refusal reason says what was refused and why. It never carries the
transcript, the tool input, the credential or a response body.

**Advisory mode governs everything.** When the user sets `advisory`, nothing blocks — not the
risk gate, not the completion gate, not the catastrophic floor. The verdict is still computed
and still reported.

**The floor is under the model, not instead of it.** The catastrophic-operation list is
consulted before the decision layer, because a decision model that shrugs at `rm -rf /` should
not overrule a list this short.

## Layout rules

- One repository, several manifests: `.claude-plugin/`, `.codex-plugin/`, `.agents/plugins/`.
  The engine is shared; only the manifest changes.
- `bin/` holds shims so `jevqueue` is on `PATH` while the plugin is enabled. `scripts/` holds
  the real entry points.
- The plugin's own environment lives under `${CLAUDE_PLUGIN_DATA}`, never in the user's
  project and never in their system Python.

## Development

```bash
uv venv && uv pip install -e "..[dev]" pytest
uv run pytest
claude plugin validate .
```

The suite is offline by design: no network, no API key, no provider. A test that needs a
credential does not run, and one that does not run is decoration.

A new gate needs a test that fails without it. Docstrings explain **why** a check exists, not
what the line below does.

## The hard part, and what it is not

A pre-tool hook **cannot constrain the provider's tool choice** — the provider is not ours to
constrain from a hook. What a hook can do is refuse a step the decision layer says should not
run, and escalate a risky one. That is the guardrail guarantee, not the enforcement one.

The stronger guarantee — the provider constrained to a named tool, and the result checked
against it — lives in the decision layer itself, installed as a library in the agent you are
building. Both are worth having and they are not the same thing. Never describe this plugin
as providing the stronger one.
