# Install, enable, test

Everything here works from the published repository. Nothing needs PyPI, a token, or an
account — the decision layer runs offline with no credential, and uses the hosted model only
if you configure a key.

## Install

### Claude Code

```bash
claude plugin marketplace add iamvazghen/jevqueue
claude plugin install jevqueue@jevqueue
```

One command, on v2.1.292 or later:

```bash
claude plugin install jevqueue --marketplace iamvazghen/jevqueue
```

Or from inside a session, on v2.1.275 or later:

```
/plugin install jevqueue --marketplace iamvazghen/jevqueue
```

### Codex CLI

```bash
codex plugin marketplace add iamvazghen/jevqueue
codex plugin add jevqueue@jevqueue
```

### Gemini CLI and Qwen Code

```bash
gemini extensions install https://github.com/iamvazghen/jevqueue
```

Qwen Code uses the same format:

```bash
qwen extensions install https://github.com/iamvazghen/jevqueue
```

### opencode

opencode reads `opencode.json` from your project. Add the plugin:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["https://github.com/iamvazghen/jevqueue"]
}
```

Or install it into your global config:

```bash
opencode plugin https://github.com/iamvazghen/jevqueue
```

### Cursor, Windsurf, Kiro, Cline, OpenClaw, GitHub Copilot

These read a rules file rather than a plugin. Copy the one your agent looks for:

| Agent | File | Destination |
|---|---|---|
| Cursor | `.cursor/rules/jevqueue.mdc` | your project's `.cursor/rules/` |
| Windsurf | `.windsurf/rules/jevqueue.md` | your project's `.windsurf/rules/` |
| Kiro | `.kiro/steering/jevqueue.md` | your project's `.kiro/steering/` |
| Cline | `.clinerules/jevqueue.md` | your project's `.clinerules/` |
| OpenClaw | `.openclaw/skills/jevqueue/SKILL.md` | your project's `.openclaw/skills/jevqueue/` |
| GitHub Copilot | `.github/copilot-instructions.md` | your project's `.github/` |
| agents.md standard | `.agents/rules/jevqueue.md` | your project's `.agents/rules/` |

Each one is a copy of the same document, so the guidance does not drift between agents. The
`agents.md` variant is also the one to use for any agent you do not see listed.

### Any agent that speaks MCP

The portable core is one MCP server with one tool:

```bash
python mcp/jevqueue_mcp.py
```

Point your agent's MCP configuration at it and it gains `jevqueue_decide`.

### As a library, inside the agent you are building

```bash
pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"
```

The package is **not on PyPI**, so the install names the repository. No required dependencies.
`httpx` is needed only for the hosted decision model and comes with the `hosted` extra:

```bash
pip install "jevqueue[hosted] @ git+https://github.com/iamvazghen/jevqueue.git"
```

## Enable it

Most agents are enabled the moment they are installed. What is worth checking is the
**configuration**, which lives in the plugin's own settings rather than in a file you have to
edit.

### The settings

| Setting | Default | What it does |
|---|---|---|
| **TypeSafe API key** | unset | With it, decisions come from the hosted Jev model. Without it, the offline rules baseline — no network, no account, no cost. |
| **Mode** | `enforce` | `enforce` refuses a step. `advisory` reports the same verdicts and never blocks. |
| **Confidence floor** | `0.8` | Below this routing confidence the step is delegated rather than gated. |

In Claude Code these live under `/config` for the plugin. The key is **never** read from an
environment variable — see [PRIVACY.md](https://github.com/iamvazghen/jevqueue/blob/main/PRIVACY.md).

### If you want the hosted model

Set the key in the plugin's settings, not in your shell. The hosted model is Jev, TypeSafe's
System One model; the plugin is not affiliated with TypeSafe and the service has its own
[terms](https://docs.typesafe.ai/legal).

### The awareness document

The plugin does not wait to be discovered. A `SessionStart` hook (Claude Code, Codex) and a
`BeforeAgent` hook (Gemini) inject a short document into the session at start-up, so the
agent knows the queue exists, when to ask it, and what to do when it says no.

It is short on purpose. It is injected into **every** session, so every paragraph costs
tokens in every conversation — including the ones where the queue has nothing to do. The long
explanation lives in [benefits.md](benefits.md); the injected version is the dozen lines an
agent can act on.

## Test it

### The quick check

```bash
pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"
python -m jevqueue
```

That runs the decision layer against a fake provider and prints three things: the provider
constrained to the selected tool, a provider that ignores the constraint refused before
anything executes, and a destructive tool stopped at the risk gate.

### Ask it about a step

```bash
jevqueue decide --tool Bash --input '{"command": "rm -rf build/"}'
```

Exit code `1` and a refusal means it is working. An ordinary step:

```bash
jevqueue decide --tool Read --input '{"file_path": "README.md"}'
```

Exit code `0` and `allow: true` means it is working.

### See which engine is running

```bash
jevqueue status
```

`engine: jevqueue` means the decision layer is live. `engine: policy` means it could not be
reached and only the catastrophic-operation floor stood in for it.

### Test it inside your agent

Ask the agent to do something destructive and watch what happens:

> Run `rm -rf ./build` with the shell tool.

With the gate enabled and `enforce` mode, the tool call is refused with a reason and nothing
is executed. With `advisory`, the same step is allowed and the verdict is reported instead.

### Run the benchmark

```bash
uv run python bench/run_bench.py --model local
```

Fourteen labelled scenarios, reporting routing accuracy, the enforced rate and the latency
spread. A published run is committed at
`bench/results/local-rules-baseline.json`.

## How it gets used

The point is that you should not have to change your agent to benefit from this.

**Where the agent has hooks.** Before every tool call, the gate asks the decision layer
whether the step should run. A confident "no" — high risk, or the work is already done —
refuses the call and tells the agent why. The agent reads the reason and adapts: it escalates
a risky step to a human, or it stops and writes the answer.

**Where the agent has no hooks.** The rules file tells the agent that the queue exists, and
the MCP server lets it ask. The judgement moves into the agent, but it moves.

**Where you govern your own agent.** Install the library and the provider is constrained to a
named tool, and the result is checked against the decision. A provider that ignores the
constraint raises before anything executes. This is the stronger of the two guarantees, and
it is the one the plugin cannot give you — a hook runs after the agent has already chosen.

**In all three cases the same thing happens**: the decision stops being a sentence in a
transcript and becomes a value that can be refused.
