---
description: Install the decision layer into the plugin's own environment
argument-hint: ""
allowed-tools: Bash(python:*), Bash(pip:*), Bash(uv:*), Read, Write
---

# jevqueue setup

Install the full decision layer so the queue stops running on the fallback policy.

The plugin keeps its environment in `${CLAUDE_PLUGIN_DATA}`, which survives plugin updates and
is deleted only when the plugin is uninstalled. That is where the virtualenv goes.

## What to do

1. Check what is already there:

   ```bash
   jevqueue status
   ```

   If the engine is already `jev-governor`, stop here and report that there is nothing to do.

2. Create the environment and install the decision layer into it:

   ```bash
   python -m venv "${CLAUDE_PLUGIN_DATA}/venv"
   "${CLAUDE_PLUGIN_DATA}/venv/bin/python" -m pip install --upgrade pip
   "${CLAUDE_PLUGIN_DATA}/venv/bin/python" -m pip install jev-governor
   ```

   On Windows the interpreter is `${CLAUDE_PLUGIN_DATA}\venv\Scripts\python.exe`; use
   `Scripts\python.exe` in place of `bin/python` and `Scripts\pip.exe` in place of
   `bin/pip`. Run the commands with the right one for the platform rather than guessing.

   **If that install fails**, the decision layer may not be on PyPI yet. Install it from
   source instead — it is the same package, and it is the version this plugin is developed
   against:

   ```bash
   "${CLAUDE_PLUGIN_DATA}/venv/bin/python" -m pip install \
     "jev-governor @ git+https://github.com/iamvazghen/jev-governor.git"
   ```

   Install from source rather than from PyPI if the PyPI install fails. Report which one you
   used.

3. Confirm it worked:

   ```bash
   jevqueue status
   ```

   The engine should now read `jev-governor`.

4. Report what happened, including the version installed and whether a credential is set. If
   the install failed, report the error verbatim and say the queue is still running on the
   fallback policy — which works, but is a much weaker guarantee.

## Notes

- **The credential is optional.** Without one, the queue uses the offline rules baseline,
  which needs no network and no account. With one, decisions come from Jev, the hosted
  System One model. The user can set it later with `/config`.
- **This installs one package into one directory.** It does not touch the user's Python,
  their project, or their shell configuration.
- **Do not** run `pip install` against the system interpreter or into the user's active
  environment. Everything belongs under `${CLAUDE_PLUGIN_DATA}`.
