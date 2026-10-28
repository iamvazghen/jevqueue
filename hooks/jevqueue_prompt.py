#!/usr/bin/env python3
"""The UserPromptSubmit hook: remember what was asked.

The transcript is written asynchronously and may not yet contain the turn being processed,
so by the time the first tool call fires the newest user turn in the transcript is usually
the *previous* one. This hook caches the live prompt, and the pre-tool hook reads it back.

Without this, the queue would decide about the last thing the agent was asked rather than
the thing it is being asked now, which is the wrong question often enough to matter.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    # Read the bytes ourselves and strip a byte-order mark if one is there. `json.load` on a
    # BOM-prefixed stream raises, and a hook that raises on every prompt is a hook that
    # never caches anything.
    try:
        raw = sys.stdin.buffer.read()
    except (AttributeError, ValueError, OSError):
        return 0
    if not raw:
        return 0
    try:
        payload = json.loads(raw.decode("utf-8-sig", "replace").lstrip("﻿").strip())
    except (ValueError, TypeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return 0

    from jevqueue.core import save_prompt

    try:
        save_prompt(payload.get("session_id") or "", prompt)
    except Exception:  # noqa: BLE001 - caching a prompt must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
