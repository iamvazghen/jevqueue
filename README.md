# jevqueue

**A decision queue in front of your agent's tools.**

[![CI](https://github.com/iamvazghen/jevqueue/actions/workflows/ci.yml/badge.svg)](https://github.com/iamvazghen/jevqueue/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-iamvazghen.github.io%2Fjevqueue-blue)](https://iamvazghen.github.io/jevqueue/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/iamvazghen/jevqueue.svg)](https://github.com/iamvazghen/jevqueue/releases/latest)

Your agent picks a tool. Before it runs, jevqueue asks a decision model whether it should —
and refuses the call when the answer is no.

```text
   agent decides to call Bash ──► jevqueue ──► decision model
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
              allow the call                    refuse the call, with a reason
```

An ordinary agent loop asks one model to do two unrelated jobs: decide what to do next, and
write the thing. The two share a pass, so two things go unchecked. **The wrong tool runs**,
because nothing verifies the selection against anything. And **the agent reports success on
work that never happened**, because the model that decides to stop is the model claiming it
finished, and a model is a poor witness to its own reliability.

jevqueue moves the decision out of that pass and gives it a place to be enforced.

---

## One package, two guarantees

Both live here, in one install, with **no dependencies**.

| | What it is | Who it is for |
|---|---|---|
| **The decision layer** | The provider is constrained to a named tool, and the result is checked against it. A provider that ignores the constraint raises before anything executes. | People **building** an agent |
| **The gate** | A pre-tool hook that refuses a step the decision layer says should not run, and escalates a risky one. | People **running** an agent |

They are different guarantees and it matters which one you have. A hook cannot constrain a
provider's generation — the provider is not yours to constrain from a hook. What it can do is
refuse a step, and that is worth a great deal. See [Which guarantee do you
need?](#which-guarantee-do-you-need).

---

## Install

### As a plugin — Claude Code

```bash
claude plugin marketplace add iamvazghen/jevqueue
claude plugin install jevqueue@jevqueue
```

In one command, on Claude Code v2.1.292 or later:

```bash
claude plugin install jevqueue --marketplace iamvazghen/jevqueue
```

Or from inside a session, on v2.1.275 or later:

```
/plugin install jevqueue --marketplace iamvazghen/jevqueue
```

### As a plugin — Codex CLI

```bash
codex plugin marketplace add iamvazghen/jevqueue
codex plugin add jevqueue@jevqueue
```

### As an extension — Gemini CLI and Qwen Code

```bash
gemini extensions install https://github.com/iamvazghen/jevqueue --consent
```

Qwen Code takes the same format, but asks which plugin to install when the URL points at a
marketplace, so name the plugin and pass `--consent`:

```bash
qwen extensions install iamvazghen/jevqueue:jevqueue --consent
```

Both install from the published GitHub release, so a new version appears with
`gemini extensions update jevqueue` rather than a reinstall.

### As a plugin — opencode

opencode reads `opencode.json` from your project, so add the plugin there:

```json
{ "plugin": ["https://github.com/iamvazghen/jevqueue"] }
```

### Everywhere else

Cursor, Windsurf, Kiro, Cline, OpenClaw, GitHub Copilot and the `agents.md` standard all read
a rules file, and this repository ships one for each — copy the one your agent looks for, or
point it at the `jevqueue` skill. Every agent that speaks MCP gets the portable core as a
tool called `jevqueue_decide` — registered for you by Claude Code, Codex and GitHub Copilot
when the plugin installs — and the rules file tells the agent when to use it and what to do
when it says no.

### Where it runs, and what that buys you

| Agent | Mechanism | What it gets |
|---|---|---|
| **Claude Code** | `PreToolUse` hook | The gate refuses the call before it runs |
| **Codex CLI** | `PreToolUse` hook | The gate refuses the call before it runs |
| **Gemini CLI** / **Qwen Code** | extension: MCP server, skills, `BeforeTool` hook | The queue is available to ask, and the hook is configured |
| **opencode** | `tool.execute.before` plugin | The gate refuses the call before it runs |
| **Cursor, Windsurf, Kiro, Cline, OpenClaw, Copilot** | rules file + `AGENTS.md` | The agent is told to ask the queue first |
| **Any MCP agent** | `jevqueue_decide` tool | The agent can ask about any step before taking it |

Two dialects, one decision layer: Claude Code and Codex speak `PreToolUse`, Gemini speaks
`BeforeTool`, and the same gate script answers both. Where an agent has hooks, the refusal
happens before the tool runs. Where it does not, the rules file makes the agent ask first.

**One honest caveat.** Gemini CLI 0.45 loads an extension's hooks from `hooks/hooks.json` —
the same path Claude Code uses — and the two dialects cannot both live in one file. The
repository therefore keeps them apart: `hooks/claude-hooks.json` for Claude Code and Codex,
`hooks/hooks.json` in Gemini's dialect. Claude Code still inspects `hooks/hooks.json`, finds
an event it does not know, and reports one harmless warning while ignoring it; the hook Claude
Code actually runs is the one its manifest declares.

### As a library — in the agent you are building

```bash
pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"
```

The package is **not on PyPI**, so the install names the repository. There are no required
dependencies. `httpx` is needed only for the hosted decision model, and is an extra:

```bash
pip install "jevqueue[hosted] @ git+https://github.com/iamvazghen/jevqueue.git"
```

If you would rather work from a checkout, `pip install -e .` does the same thing without the
network round-trip.

```python
from jevqueue import Governor, JevClient
from jevqueue.adapters.openai_chat import OpenAIChatHost

governor = Governor(JevClient(key))
response = governor.step(OpenAIChatHost(request, send_it))
```

### As a skill — any agent that reads `SKILL.md`

The two skills in `skills/` work in any agent that reads `SKILL.md`: Claude Code, Codex,
Cursor, Windsurf, and anything else that follows the open skill format. Copy them into your
agent's skills directory and they work on their own, with no hooks and no setup.

### As an MCP server — any MCP-capable agent

Claude Code, Codex and GitHub Copilot register the server themselves when you install the
plugin; there is nothing to configure. For any other MCP-capable agent, expose it by hand:

```bash
python mcp/jevqueue_mcp.py
```

Either way the agent gains one tool, `jevqueue_decide`, which answers the same question the
hook answers. The plugin launches the server through `bin/jevqueue-mcp.mjs`, which finds a
Python interpreter — `python3`, `python` or `py -3`, whichever is actually there — and hands
the process over, because `python` and `python3` are not the same interpreter and on macOS
`python` may not exist at all.

---

## Configure it

| Setting | Meaning |
|---|---|
| **TypeSafe API key** | Optional. With it, decisions come from the hosted Jev model. Without it, the offline rules baseline — no account, no network, no cost. |
| **Mode** | `enforce` refuses a step. `advisory` reports the same verdicts and never blocks. |
| **Confidence floor** | Below this routing confidence the step is delegated rather than gated. |

**The key is read from the plugin's own settings, and nowhere else.** Not from
`TYPESAFE_API_KEY`, not from any environment variable. A plugin that quietly picks up a
secret already sitting in your shell and ships it somewhere is doing something you did not
agree to, and it makes the data handling impossible to reason about. See
[PRIVACY.md](PRIVACY.md).

For the library, `JevClient(key)` takes the key explicitly, and the framework adapters read
`TYPESAFE_API_KEY` the way every Python library reads one — that is a library's job, and it
is a different surface from the plugin's.

---

## What it does

On every tool call, the gate asks one question about the pending step:

> **Should this step run at all?**

Not "which tool" — the agent has already chosen that, and a hook cannot constrain a
provider's generation. The question worth asking at this point is whether *this* step is
right, and there are exactly two ways it is not.

### The risk gate

Some steps are irreversible, unbounded, or outside clear authorization: deleting things,
rewriting production, force-pushing, dropping tables, piping a download into a shell. The
decision layer triages the step as `low`, `medium` or `high` with a probability, and a
confidently `high` verdict stops the step and asks a human instead.

### The completion gate

The most common real failure of an agent loop is an agent reporting success on work that
never happened. It happens because the same model that decides to stop is the one claiming it
finished. The decision layer asks the completion question **separately**, so the two
judgments cannot see each other's answers, and when they disagree the stricter one wins and
the work continues.

**Risk is checked before completion.** That order is the point: "this might be destructive
and I am not sure" must never be answered with "but the work seems finished anyway".

### The floor

Underneath both gates is a short, explicit list of operations nobody would argue about —
`rm -rf /`, a download piped into a shell, `dd` onto a block device, `DROP TABLE`. A decision
model that shrugs at one of those does not get to overrule the list.

### It fails open

If the decision layer is unreachable, the transcript is unreadable, or something inside the
plugin breaks: the tool is allowed and a diagnostic goes to stderr. A governance layer that
bricks the agent on a bad day is worse than no governance layer.

It also fails **narrow**. The queue refuses a small number of steps rather than steering
every step. A gate that refuses on doubt is a wall.

---

## Which guarantee do you need?

**You are running an agent and want its steps checked.** Install the plugin. The hook runs
before each tool call, asks the decision layer, and refuses the step when the answer is no.
This is the **guardrail** guarantee.

**You are building an agent and want its tool choice constrained.** Use the library. The
host sets `tool_choice` to a named function with `parallel_tool_calls=False`, and the
result is checked: a provider that called something else raises `JevError` before anything
executes. This is the **enforcement** guarantee, and it is the stronger one.

Both are the same code. The difference is where the constraint is applied.

---

## The engines

| Engine | What it is | Needs |
|---|---|---|
| `jevqueue` | The decision layer: calibrated answers, a distrust layer, a guard order | Nothing — it is in this package |
| `policy` | The catastrophic-operation floor, running alone because the decision layer could not be reached | Nothing |

Check which one you have:

```bash
jevqueue status
```

With a credential configured, decisions come from **Jev**, the hosted System One model.
Without one, they come from the **offline rules baseline**, which needs no account and no
network. Both are honest about what they are; the fallback says so on every run.

---

## Using it by hand

```bash
jevqueue status
jevqueue decide --tool Bash --input '{"command": "rm -rf build/"}'
jevqueue decide --tool Read --input '{"file_path": "/etc/shadow"}'
```

`decide` prints the verdict, the engine, the model, the action, the confidence, the risk and
the completion probability. It is the same call the hook makes.

---

## What it runs, sends and fetches

Short version: **two Python scripts on your machine, one bounded summary sent to a decision
model if you configured a key, nothing fetched, one small cached file written.** The full
detail, including exactly what is in the request, is in [PRIVACY.md](PRIVACY.md).

The short version of the short version: the plugin makes **no network request at all** unless
you have configured an API key, and when it does, the request goes to
`https://api.typesafe.ai/v1/systemone` and nowhere else.

---

## Frameworks

| Framework | Integration | Extra |
|---|---|---|
| **Any OpenAI-compatible loop** | `OpenAIChatHost` | — |
| **LangChain** | `GovernedChatModel`, a chat-model wrapper | `jevqueue[langchain]` |
| **Pydantic AI** | `GovernedModel`, a `WrapperModel` | `jevqueue[pydantic-ai]` |
| **Hermes Agent** | a six-line seam in `agent/turn_api_call.py` | — |
| **OpenClaw** | `OpenClawRouter` — fleet routing, *not* governed | — |
| **Your own** | seven methods — see [docs/adapters.md](docs/adapters.md) | — |

---

## What this is not

- **It is not a planner.** It decides one step at a time. It does not decompose a goal.
- **It is not an authorization layer.** A `low` risk verdict is not permission to loosen your
  own tool permissions. Your existing authorization must stay correct on its own.
- **It is not always right.** A confident wrong verdict is possible. That is why the gates
  are narrow and why the floor exists.
- **It does not replace your model.** The generative model still writes the arguments and the
  prose. jevqueue decides whether the step runs; the model still does the work.

And the honest limitation, stated up front: **a pre-tool hook cannot constrain the
provider's tool choice.** If you need the stronger guarantee, use the library.

---

## How it fits together

```text
jevqueue/
├── jevqueue/                 the package
│   ├── client.py             the hosted model, and the DecisionModel protocol
│   ├── decision.py           the parser, and the distrust layer
│   ├── governor.py           the guards, in order
│   ├── questions.py          the three typed questions
│   ├── state.py              the bounded, read-only projection
│   ├── local.py              the offline rules baseline
│   ├── policy.py             the catastrophic-operation floor
│   ├── gate.py               the hook-facing engine
│   ├── cli.py                the command line
│   └── adapters/             Hermes, LangChain, OpenAI, OpenClaw, Pydantic AI
├── hooks/                    the PreToolUse and UserPromptSubmit hooks
├── commands/                 /jevqueue:setup, /jevqueue:check, /jevqueue:status
├── skills/                   the portable core: jevqueue, jevqueue-adapter
├── mcp/jevqueue_mcp.py       the portable core as an MCP server
├── .mcp.json                 registers that server with the plugin
├── scripts/                  the bare-import check, the icon, the CLI shim
├── bin/                      shims so `jevqueue` is on PATH, and the MCP launcher
├── docs/                     architecture, limits, comparison, adapters, roadmap
└── PRIVACY.md                what this plugin runs, sends and fetches
```

## Documentation

| | |
|---|---|
| [docs/install.md](docs/install.md) | **Install, enable, test** — every agent, and how to check it is working |
| [docs/benefits.md](docs/benefits.md) | **What it buys the owner of the agent**, with measured token costs |
| [docs/architecture.md](docs/architecture.md) | The two-tier split, the guard order, and why each guard sits where it does |
| [docs/adapters.md](docs/adapters.md) | Writing a `Host` for a framework not listed here |
| [docs/install-hermes.md](docs/install-hermes.md) | Copy-paste Hermes integration and how to keep merging upstream |
| [docs/limits.md](docs/limits.md) | What this cannot do, and when not to use it |
| [docs/comparison.md](docs/comparison.md) | Against a standard loop, and against other routing approaches |
| [docs/local-decision-model.md](docs/local-decision-model.md) | The offline rules baseline: what it is, what it is not, and how to use it |
| [docs/roadmap.md](docs/roadmap.md) | Possible improvements, with the reasoning for each |

There is a full site at <https://iamvazghen.github.io/jevqueue/>.

## Development

```bash
uv venv && uv pip install -e ".[dev,langchain,pydantic-ai]"
uv run pytest
uv run ruff check jevqueue tests hooks mcp scripts
uv run mypy
claude plugin validate --strict .
```

368 tests, offline: no network, no API key, no provider. A test that needs a credential does
not run, and one that does not run is decoration.

## License

**[MIT](LICENSE)**, and it covers everything in this repository: the decision layer, the gate,
the hook scripts, the plugin manifests, the skills, the MCP server and the documentation.
Copyright (c) 2026 Vazghen Vardanian.

**No third-party code is vendored.** The package has no required dependencies — the decision
layer is pure standard library — and `httpx`, needed only for the hosted decision model, is an
optional extra. [NOTICE](NOTICE) carries the attribution.

**The hosted model is not part of this license.** *Jev* is TypeSafe's System One model, a
separately hosted service reached over the network at `api.typesafe.ai`. It is not distributed
here: this repository ships no model weights, no API keys and no usage credits, and using that
service is subject to [TypeSafe's terms](https://docs.typesafe.ai/legal). Everything that *is*
in this repository — including the offline rules baseline, which needs no account and makes no
network request at all — is covered by the MIT license above.

`jevqueue` is an independent community project. It is not affiliated with, endorsed by, or
supported by TypeSafe AI or Nous Research. [PRIVACY.md](PRIVACY.md) documents what the plugin
runs, reads, sends and writes.
