---
description: Show which decision engine is active, how it is configured, and what it refuses
argument-hint: ""
allowed-tools: Bash(jevqueue:*), Bash(python:*), Read
---

# jevqueue status

Report the state of the queue in this environment.

Run this and read the output:

```bash
jevqueue status
```

If the `jevqueue` command is not on PATH, run the script directly:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/jevqueue.py" status
```

Then report, in this order:

1. **Which engine is active.** `jev-governor` means the real decision layer is installed and
   every step is judged by it. `policy` means only the dependency-free fallback is running,
   which knows about a short list of catastrophic operations and nothing else — say so
   plainly, because it is a much weaker guarantee and the user should know which one they
   have.
2. **Whether the hosted model is in use.** With a credential, decisions come from Jev; without
   one, from the offline rules baseline. Neither is a problem; they are different strengths.
3. **The mode.** `enforce` refuses a step. `advisory` reports the same verdicts and never
   blocks.
4. **Where the state lives**, so the user can find the decision log.
5. **How to strengthen it**, if the fallback is active: `/jevqueue:setup` installs the
   decision layer into the plugin's own environment.

If the engine is `policy`, finish with the one-line setup instruction. Do not pad the answer.
