#!/usr/bin/env python3
"""The PreToolUse hook: refuse a tool call the decision layer says should not run.

Reads the hook payload on stdin and either prints a deny decision on stdout or exits
silently. **Silence means "no opinion", not "approved"** -- Claude Code continues through its
normal permission flow, which is the whole point of a gate rather than a wall.

Two rules this file never breaks:

* **Fail open.** A crash, a missing interpreter, an unreadable transcript: the tool is
  allowed and a diagnostic goes to stderr. A governance layer that bricks the agent on a bad
  day is worse than no governance layer.
* **Leak nothing.** The deny reason says what was refused and why. It never carries the
  transcript, the tool input, the credential or the response body.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _ensure_engine() -> None:
    """Re-exec into the plugin's own virtualenv when that is where the engine lives.

    ``/jevqueue:setup`` creates ``${CLAUDE_PLUGIN_DATA}/venv`` and installs the decision
    layer into it. When the hook runs under a different interpreter, it hands over to that
    one rather than silently downgrading to the fallback policy.
    """
    try:
        import jev_governor  # noqa: F401

        return
    except ImportError:
        pass

    base = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not base:
        return
    for parts in (("venv", "Scripts", "python.exe"), ("venv", "bin", "python")):
        candidate = os.path.join(base, *parts)
        if os.path.exists(candidate):
            try:
                os.execv(candidate, [candidate, os.path.abspath(__file__)])
            except OSError:
                return


def _payload() -> dict:
    """Read the hook payload from stdin.

    Decoded with ``utf-8-sig`` because a byte-order mark is a real thing that turns up on
    the wire -- and a BOM in front of the JSON makes ``json.load`` raise, which would turn
    into a silent fail-open on every single call. Reading the bytes ourselves and stripping
    the mark if it is there is the difference between "the queue works" and "the queue never
    runs".
    """
    try:
        raw = sys.stdin.buffer.read()
    except (AttributeError, ValueError, OSError):
        raw = b""
    if not raw:
        return {}
    try:
        text = raw.decode("utf-8-sig", "replace")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")
    # `utf-8-sig` strips one byte-order mark. Some pipes write two.
    text = text.lstrip("﻿").strip()
    try:
        message = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return message if isinstance(message, dict) else {}


def main() -> int:
    _ensure_engine()

    payload = _payload()
    tool_name = payload.get("tool_name") or ""
    if not tool_name:
        return 0

    from jevqueue.core import decide

    try:
        decision = decide(
            tool_name,
            payload.get("tool_input") or {},
            transcript_path=payload.get("transcript_path"),
            session_id=payload.get("session_id") or "",
        )
    except Exception as error:  # noqa: BLE001 - never block the agent on our own failure
        print(f"jevqueue: internal error, allowing the tool: {error}", file=sys.stderr)
        return 0

    if decision.allow:
        print(
            f"jevqueue: allowed {tool_name} "
            f"(engine={decision.engine}, {decision.latency_ms:.0f}ms)",
            file=sys.stderr,
        )
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": decision.reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
