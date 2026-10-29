#!/usr/bin/env python3
"""The SessionStart hook: tell the agent what this plugin is, without being asked.

A plugin whose only artefact is a README has already failed. The agent that is about to run
does not read READMEs -- it reads what is in its context -- so the awareness has to arrive
there, unprompted, or it does not arrive at all.

This hook prints a short document at session start:

* Claude Code and Codex -- ``SessionStart``, whose output carries ``additionalContext``.
* Gemini CLI -- ``BeforeAgent``, which carries the same field.

The text is short on purpose. It is injected into **every** session, so every paragraph costs
tokens in every conversation -- including the ones where jevqueue has nothing to do. The full
explanation lives in the docs; this is the version an agent can act on in a dozen lines.

Failures here are silent and harmless. An agent that starts without the document is in
exactly the position it was in before the plugin was installed.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _payload() -> dict:
    try:
        raw = sys.stdin.buffer.read()
    except (AttributeError, ValueError, OSError):
        return {}
    if not raw:
        return {}
    try:
        text = raw.decode("utf-8-sig", "replace").lstrip("﻿").strip()
        message = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return message if isinstance(message, dict) else {}


def main() -> int:
    payload = _payload()
    event = payload.get("hook_event_name") or ""

    try:
        from jevqueue.awareness import SHORT_AWARENESS
    except Exception:
        return 0

    # Claude Code and Gemini each have their own field for "here is extra context", and
    # both ignore the other's. Sending the right one to the right runtime is the whole
    # reason this file branches.
    if event == "BeforeAgent":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "BeforeAgent",
                "additionalContext": SHORT_AWARENESS,
            }
        }))
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": SHORT_AWARENESS,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
