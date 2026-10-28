#!/usr/bin/env python3
"""An MCP server exposing the decision layer to any agent.

Hooks are the strong integration: they refuse a tool call before it runs. But hooks are not
universal -- not every agent runtime has them, and not every agent should be governed
automatically. This server is the portable half: any MCP-capable agent can ask the queue a
question and get the verdict, and then decide for itself.

One tool, ``jevqueue_decide``, because one tool that is genuinely useful beats six that are
merely available.

The protocol is JSON-RPC 2.0 over stdio, which is what MCP clients speak. Only the three
methods an agent actually needs are implemented: ``initialize``, ``tools/list`` and
``tools/call``.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jevqueue import core  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "jevqueue_decide",
        "description": (
            "Ask the decision layer whether a pending step should run, before running it. "
            "Returns the verdict, the action, the confidence, the risk triage and the "
            "completion probability. Use it before a destructive or irreversible step, and "
            "before continuing on work that may already be finished."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {
                    "type": "string",
                    "description": "The tool about to be called, for example Bash or Read.",
                },
                "input": {
                    "type": "object",
                    "description": "The tool's input, as an object.",
                    "additionalProperties": True,
                },
                "goal": {
                    "type": "string",
                    "description": (
                        "What the agent is currently trying to do, in the user's words. "
                        "Optional, and better than nothing."
                    ),
                },
            },
            "required": ["tool"],
        },
    }
]


def _result(request_id, payload) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _handle(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jevqueue", "version": _version()},
            },
        )

    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        if name != "jevqueue_decide":
            return _error(request_id, -32602, f"unknown tool {name!r}")
        arguments = params.get("arguments") or {}
        tool = arguments.get("tool")
        if not isinstance(tool, str) or not tool:
            return _error(request_id, -32602, "a tool name is required")
        decision = core.decide(tool, arguments.get("input") or {})
        return _result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(decision.as_dict(), indent=2, ensure_ascii=False),
                    }
                ],
                "isError": False,
            },
        )

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notifications carry no id and expect no answer

    if request_id is None:
        return None
    return _error(request_id, -32601, f"method not found: {method}")


def _version() -> str:
    try:
        from jevqueue import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "0.0.0"


def main() -> int:
    for raw in sys.stdin:
        # A byte-order mark on the first line is a real thing that happens: some clients and
        # every PowerShell pipe add one. It is not a reason to drop the request.
        line = raw.lstrip("﻿").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except (ValueError, TypeError) as error:
            # Never swallow a request silently. If the line carried an id, answer it with a
            # parse error, so a client waiting on a reply is not left hanging.
            match = re.search(r'"id"\s*:\s*([^,}\s]+)', line)
            if match:
                try:
                    identifier = json.loads(match.group(1))
                except ValueError:
                    identifier = match.group(1)
                response = _error(identifier, -32700, f"parse error: {error}")
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            continue
        try:
            response = _handle(message)
        except Exception as error:  # noqa: BLE001 - a server that dies takes the agent with it
            response = _error(message.get("id"), -32603, f"internal error: {error}")
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
