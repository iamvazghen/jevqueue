/**
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
