#!/usr/bin/env python3
"""The pre-tool hook: refuse a step the decision layer says should not run.

One script, several runtimes. The mechanics are the same everywhere -- JSON on stdin, JSON on
stdout, stderr for logs -- but the dialects differ:

============  ==============  ===========================================
Runtime       Event          Refusal
============  ==============  ===========================================
Claude Code   ``PreToolUse`` ``{"hookSpecificOutput": {"permissionDecision": "deny"}}``
Gemini CLI    ``BeforeTool``  ``{"decision": "deny", "reason": "..."}``
Codex CLI     ``PreToolUse`` ``{"hookSpecificOutput": {"permissionDecision": "deny"}}``
============  ==============  ===========================================

So the payload is chosen from the event name the runtime sends, and an unrecognised runtime
gets both shapes at once -- extra keys are ignored by every runtime that reads this, and a
gate that fails to speak the dialect silently is worse than one that speaks two.

Three rules this file never breaks:

* **Fail open.** A crash, a missing interpreter, an unreadable transcript: the tool is
  allowed and a diagnostic goes to stderr. A governance layer that bricks the agent on a bad
  day is worse than no governance layer.
* **Leak nothing.** The refusal reason says what was refused and why. It never carries the
  transcript, the tool input, the credential or a response body.
* **Say nothing on success.** The only thing on stdout is the final JSON.
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


def _refusal(event: str, reason: str) -> str:
    """Build the refusal payload in the dialect the runtime understands."""
    payload: dict = {}
    if event in ("", "PreToolUse"):
        payload["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    if event in ("", "BeforeTool"):
        payload["decision"] = "deny"
        payload["reason"] = reason
    if not payload:
        # An unrecognised runtime gets both dialects: it reads whichever it knows.
        payload["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
        payload["decision"] = "deny"
        payload["reason"] = reason
    return json.dumps(payload)


def main() -> int:
    payload = _payload()
    tool_name = payload.get("tool_name") or ""
    if not tool_name:
        return 0

    from jevqueue.gate import decide

    try:
        verdict = decide(
            tool_name,
            payload.get("tool_input") or {},
            transcript_path=payload.get("transcript_path"),
            session_id=payload.get("session_id") or "",
        )
    except Exception as error:
        print(f"jevqueue: internal error, allowing the tool: {error}", file=sys.stderr)
        return 0

    if verdict.allow:
        print(
            f"jevqueue: allowed {tool_name} "
            f"(engine={verdict.engine}, {verdict.latency_ms:.0f}ms)",
            file=sys.stderr,
        )
        return 0

    reason = verdict.reason
    print(_refusal(payload.get("hook_event_name") or "", reason))
    print(f"jevqueue: refused {tool_name} ({verdict.engine})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
