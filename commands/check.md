---
description: Ask the queue whether a specific step should run, before running it
argument-hint: "<tool> [json input]"
allowed-tools: Bash(jevqueue:*), Bash(python:*)
---

# jevqueue check

Check one pending step against the decision layer **before** taking it.

The argument is a tool name and, optionally, its input as JSON. Examples:

```bash
jevqueue decide --tool Bash --input '{"command": "rm -rf build/"}'
jevqueue decide --tool Read --input '{"file_path": "/etc/shadow"}'
jevqueue decide --tool WebFetch --input '{"url": "https://example.com"}'
```

If the argument is not valid JSON, treat the whole argument as the tool input and ask which
tool it looks like.

Run the check, then report:

- **The verdict** — allowed or refused — first.
- **The reason**, in the queue's own words, when it refused.
- **The evidence**: the action, the confidence, the risk and its confidence, and the
  completion probability.

Then, if it was refused, say what to do next in one line:

- **High risk** → do not retry the same command. State what you wanted to do and why, and
  let a human decide.
- **The work looks done** → stop calling tools and write the answer.
- **Information missing** → ask the user.

If it was allowed, say so in one line and stop. Do not editorialise about a step that passed.
