---
description: Check the installation, configure the key and mode, and run a self-test
argument-hint: ""
allowed-tools: Bash(jevqueue:*), Bash(python:*), Read
---

# jevqueue setup

There is nothing to install: the decision layer ships inside the plugin. This command checks
that everything is wired up, sets the two things that need setting, and proves the queue
refuses what it should.

## 1. Check the installation

```bash
jevqueue status
```

If `jevqueue` is not on PATH, run it directly:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/jevqueue.py" status
```

Report what it says: the version, the engine, the model it is using, the mode, and whether a
credential is set. If the engine is not `jevqueue`, something is wrong with the plugin
install and the rest of this command will not work — say so rather than continuing.

## 2. The two settings

- **The TypeSafe API key** — optional, and **never read from the environment**. It is set in
  the plugin's own settings: `/config` in Claude Code, or the equivalent in the agent you are
  running in. Ask the user to set it there; do not ask them to paste a key into the chat, and
  never offer to read one out of their shell.
- **The mode** — `enforce` refuses a step, `advisory` reports the same verdicts without
  blocking. `enforce` is the default and is what the plugin is for. If the user has been
  surprised by a refusal, `advisory` is the setting to point them at, because it shows every
  verdict without blocking any of them.

Without a key the queue runs the offline rules baseline: no network, no account, no cost.
That is a real configuration, not a broken one — say so plainly.

## 3. Prove it works

Run the self-test. It refuses a command that is not safe to run, and it never executes
anything:

```bash
jevqueue decide --tool Bash --input '{"command": "rm -rf /"}'
```

The exit code is 1 and the output is a refusal. Report the refusal reason.

Then confirm an ordinary step is allowed:

```bash
jevqueue decide --tool Read --input '{"file_path": "README.md"}'
```

The exit code is 0 and the output says `allow: true`.

## 4. Report

Say, in this order: the version, the engine and model in use, whether a credential is
configured, the mode, and whether both self-test steps behaved as expected.

If anything failed, report it verbatim and say what it means. Do not paper over it.
