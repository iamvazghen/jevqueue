# jevqueue

**A decision queue in front of your agent's tools.**

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

## Install

**Claude Code** — from a marketplace:

```bash
claude plugin marketplace add iamvazghen/jevqueue
claude plugin install jevqueue@jevqueue
```

**Or from a clone**, for development:

```bash
claude plugin marketplace add ./jevqueue
claude plugin install jevqueue@jevqueue
```

**Codex CLI** and other agent tools use the same repository with their own manifest — see
[Other agents](#other-agents).

Then run the setup once, so the queue stops running on its fallback policy:

```
/jevqueue:setup
```

That installs the decision layer into the plugin's own environment. Nothing touches your
system Python, your project, or your shell.

---

## What it does

On every tool call, jevqueue asks one question about the pending step:

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
never happened. It happens because the same model that decides to stop is the one claiming
it finished. The decision layer asks the completion question **separately**, so the two
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

## The engines

| Engine | What it is | Needs |
|---|---|---|
| `jev-governor` | The real decision layer: calibrated answers, a distrust layer, a guard order | The package, which `/jevqueue:setup` installs |
| `policy` | A dependency-free fallback that knows about the catastrophic list and nothing else | Nothing |

Check which one you have:

```bash
jevqueue status
```

With a credential configured, decisions come from **Jev**, the hosted System One model.
Without one, they come from the **offline rules baseline**, which needs no account and no
network. Both are honest about what they are; the fallback says so on every run.

---

## Configuration

`/config` shows the plugin's settings, which you set when the plugin was enabled:

| Setting | Meaning |
|---|---|
| **TypeSafe API key** | Optional. With it, decisions come from the hosted model. Without it, the offline baseline. |
| **Mode** | `enforce` refuses a step. `advisory` reports the same verdicts and never blocks. |
| **Confidence floor** | Below this routing confidence the step is delegated rather than gated. |

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

## Other agents

One repository, one engine, several runtimes. The manifests are per-tool, the engine is
shared.

| Agent | What it gets |
|---|---|
| **Claude Code** | `PreToolUse` hook, commands, skills — the full integration |
| **Codex CLI** | `.codex-plugin/` — hooks, skills, and the shared engine |
| **agents.md standard** | `.agents/plugins/marketplace.json` — the portable manifest |
| **MCP-capable agents** | An MCP server exposing `jevqueue_decide`, for agents that cannot hook |

The portable pieces are the two skills (`jevqueue` and `jevqueue-adapter`) and the MCP
server. The hook is the strong integration, and it is the only part that needs a runtime with
hooks.

---

## What this is not

- **It is not a planner.** It decides one step at a time. It does not decompose a goal.
- **It is not an authorization layer.** A `low` risk verdict is not permission to loosen your
  own tool permissions. Your existing authorization must stay correct on its own.
- **It is not always right.** A confident wrong verdict is possible. That is why the gates
  are narrow and why the fallback exists.
- **It does not replace your model.** The generative model still writes the arguments and the
  prose. jevqueue decides whether the step runs; the model still does the work.

And the honest limitation, stated up front: **a pre-tool hook cannot constrain the provider's
tool choice**, because the provider is not ours to constrain from a hook. What it can do is
refuse a step the decision layer says should not run, and escalate a risky one. If you need
the stronger guarantee — the provider constrained to a named tool, and the result checked
against it — that is the [decision layer](https://github.com/iamvazghen/jev-governor) itself,
installed as a library in the agent you are building. Both are worth having; they are not the
same thing.

---

## How it fits together

```text
jevqueue/
├── .claude-plugin/          Claude Code manifest + marketplace entry
├── .codex-plugin/          Codex CLI manifest
├── .agents/plugins/        the agents.md standard manifest
├── hooks/
│   ├── hooks.json          UserPromptSubmit + PreToolUse
│   ├── jevqueue_gate.py    the decision, and the refusal
│   └── jevqueue_prompt.py  remembers what was asked
├── skills/                 the portable core: jevqueue, jevqueue-adapter
├── commands/               /jevqueue:setup, /jevqueue:check, /jevqueue:status
├── mcp/jevqueue_mcp.py     the portable core as an MCP server
├── jevqueue/core.py        the engine
├── scripts/jevqueue.py     the command line
└── bin/                    shims so `jevqueue` is on PATH
```

## Development

```bash
uv venv && uv pip install -e "..[dev]" pytest
uv run pytest
claude plugin validate .
```

The suite is offline by design: no network, no API key, no provider. A test that needs a
credential does not run, and one that does not run is decoration.

## License

[MIT](LICENSE).

`jevqueue` is an independent community project. It is not affiliated with, endorsed by, or
supported by TypeSafe AI or Nous Research. **Jev** and **TypeSafe** are names of a separately
hosted service; use of that service is subject to [TypeSafe's terms](https://docs.typesafe.ai/legal).
