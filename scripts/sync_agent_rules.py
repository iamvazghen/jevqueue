"""Write the per-agent rule files.

Every CLI agent that reads a rules file gets the same instruction in the same dialect, so
the guidance cannot drift between Cursor and Windsurf. The formats differ only in their
frontmatter, so the body is written once and wrapped per target.

Run it after changing the body:

    python scripts/sync_agent_rules.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TITLE = "jevqueue â€” a decision queue in front of your tools"

BODY = """# jevqueue â€” a decision queue in front of your tools

This agent may be governed by **jevqueue**. Before a risky or irreversible step, a decision
model is asked whether it should run, and the call is refused when the answer is no.

## What a refusal means

A refused tool call is a decision, not an error. The reason says what was refused and why.

- **Do not retry the same call.** A refusal means the step was wrong, not unlucky. If the
  reason is that the step looks destructive, do not run it anyway â€” say what you wanted and
  why, and let a human decide.
- **If the reason is that the work looks done**, stop calling tools and write the answer.
  Continuing to look for more work is the loop the gate exists to close.
- **If the reason is that information is missing**, ask the user. That question is part of
  the work, not a detour from it.

## What an allowed call means

Less than it looks like. The gate fails open: if the decision layer cannot be reached, tools
run normally. An allowed call means nothing objected, not that the step was safe.

## Asking the queue directly

The `jevqueue_decide` tool answers the same question about any step:

```
jevqueue_decide(tool="Bash", input={"command": "rm -rf build/"})
```

It returns the verdict, the action, the confidence, the risk triage and the completion
probability.

## Where the full instructions live

The `jevqueue` skill, and <https://github.com/iamvazghen/jevqueue>.
"""

SKILL_BODY = """---
name: jevqueue
description: >-
  Work under a decision queue: check a step before taking it. Use when you are about to run a
  destructive or irreversible command, when you are about to keep going on work that may
  already be finished, when a step touches production, credentials or the filesystem
  destructively, or when a tool call was refused and you need to know what to do next.
  Do not use when the task is purely writing, or when the answer is obviously yes and
  obviously harmless.
---

""" + BODY

OPENCODE_COMMAND = """---
description: Ask the decision queue whether a step should run
agent: build
---

""" + BODY

MDC = """---
description: jevqueue -- a decision queue in front of your tools. Use before a risky step.
globs:
alwaysApply: true
---

""" + BODY

KIRO = """---
title: jevqueue â€” a decision queue in front of your tools
inclusion: always
---

""" + BODY

PLAIN = BODY

FILES = {
    ".cursor/rules/jevqueue.mdc": MDC,
    ".windsurf/rules/jevqueue.md": PLAIN,
    ".kiro/steering/jevqueue.md": KIRO,
    ".clinerules/jevqueue.md": PLAIN,
    ".agents/rules/jevqueue.md": PLAIN,
    ".openclaw/skills/jevqueue/SKILL.md": SKILL_BODY,
    ".github/copilot-instructions.md": PLAIN,
    ".opencode/command/jevqueue.md": OPENCODE_COMMAND,
}

OPENCODE_PLUGIN = '''/**
 * jevqueue -- refuse a tool call the decision layer says should not run.
 *
 * opencode has no hook configuration file; a plugin is the hook. This one asks the same
 * question the Claude Code and Gemini hooks ask, using the same Python gate, so all four
 * runtimes judge a step identically instead of each reimplementing the rules.
 *
 * The gate fails open. If the interpreter cannot be found, or the gate errors, the tool
 * call is allowed -- a governance layer that breaks the agent is worse than none. The
 * refusal path is the only one that can stop anything.
 *
 * Throwing from `tool.execute.before` is how opencode blocks a tool call, and the message
 * is what the agent sees.
 */

import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const GATE = join(HERE, "..", "..", "hooks", "jevqueue_gate.py")

// The order matters only in that the first one that exists wins; `py` is the Windows
// launcher, and it is last because it needs an argument.
const INTERPRETERS = ["python3", "python", "py"]

function askTheGate(tool, args) {
  const payload = JSON.stringify({
    session_id: "opencode",
    tool_name: tool,
    tool_input: args ?? {},
    hook_event_name: "PreToolUse",
  })

  return new Promise((resolve) => {
    let index = 0

    const attempt = () => {
      if (index >= INTERPRETERS.length) {
        resolve(null)
        return
      }
      const interpreter = INTERPRETERS[index++]
      let child
      try {
        child = spawn(interpreter, [GATE], { stdio: ["pipe", "pipe", "ignore"] })
      } catch {
        attempt()
        return
      }

      let out = ""
      child.stdout.on("data", (chunk) => {
        out += chunk
      })
      child.on("error", () => attempt())
      child.on("close", () => {
        try {
          resolve(JSON.parse(out || "{}"))
        } catch {
          resolve(null)
        }
      })
      child.stdin.write(payload)
      child.stdin.end()
    }

    attempt()
  })
}

export const Jevqueue = async () => {
  return {
    "tool.execute.before": async (input, output) => {
      const verdict = await askTheGate(input.tool, output.args)
      const denial = verdict?.hookSpecificOutput
      if (denial?.permissionDecision === "deny") {
        throw new Error(denial.permissionDecisionReason)
      }
    },
  }
}
'''

OPENCODE_JSON = """{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["./.opencode/plugins/jevqueue.mjs"]
}
"""

COPILOT_PLUGIN = {
    "name": "jevqueue",
    "description": (
        "A decision queue in front of your agent's tools. Before a tool runs, a decision "
        "model is asked whether it should, and the call is refused when the answer is no."
    ),
    "version": "0.4.0",
    "author": {"name": "Vazghen Vardanian", "url": "https://github.com/iamvazghen"},
    "homepage": "https://github.com/iamvazghen/jevqueue",
    "repository": "https://github.com/iamvazghen/jevqueue",
    "license": "MIT",
    "keywords": [
        "agent-governance",
        "agent-safety",
        "decision-layer",
        "guardrails",
        "tool-calling",
    ],
    "commands": "commands/",
    "skills": "skills/",
    "hooks": "hooks/claude-hooks.json",
}

COPILOT_MARKETPLACE = {
    "name": "jevqueue",
    "description": (
        "A decision queue in front of your agent's tools. Refuses the tool calls a decision "
        "model says should not run."
    ),
    "owner": {"name": "Vazghen Vardanian", "url": "https://github.com/iamvazghen"},
    "plugins": [
        {
            "name": "jevqueue",
            "description": (
                "A decision layer for existing agents: a judgment model picks the tool, the "
                "provider is constrained to it and checked, and an independent goal_met "
                "question gates whether the agent may stop."
            ),
            "source": "./",
            "category": "productivity",
            "tags": ["agent-governance", "guardrails", "decision-layer", "tool-calling"],
            "commands": "commands/",
            "skills": "skills/",
            "hooks": "hooks/claude-hooks.json",
        }
    ],
}


def main() -> int:
    written = []
    for relative, content in FILES.items():
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(relative)

    for relative, content in {
        ".opencode/plugins/jevqueue.mjs": OPENCODE_PLUGIN,
        "opencode.json": OPENCODE_JSON,
        ".github/plugin/plugin.json": json.dumps(COPILOT_PLUGIN, indent=2) + "\n",
        ".github/plugin/marketplace.json": json.dumps(COPILOT_MARKETPLACE, indent=2) + "\n",
    }.items():
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(relative)

    for relative in sorted(written):
        print(f"  wrote {relative}")
    print(f"\n{len(written)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

