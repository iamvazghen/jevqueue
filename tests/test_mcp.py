"""The MCP server's protocol behaviour.

The server has one job it must never fail at: answer a request that carried an id. A client
waiting on a reply that never comes is worse than a client that gets an error, so these tests
are mostly about what happens when the input is not what we expected.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "jevqueue_mcp.py")


def run(lines: list[str]) -> list[dict]:
    """Feed lines to the server and collect the JSON responses.

    The payload goes over as UTF-8 bytes on purpose: a byte-order mark is not
    representable in the default Windows encoding, and a test that cannot send the thing it
    is testing is worse than no test.
    """
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    result = subprocess.run(
        [sys.executable, SERVER],
        input=payload,
        capture_output=True,
        timeout=90,
    )
    responses = []
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line:
            responses.append(json.loads(line))
    return responses


class TestTheProtocol:
    def test_initialize_is_answered(self):
        responses = run(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"},
                    }
                )
            ]
        )

        assert len(responses) == 1
        assert responses[0]["id"] == 1
        assert "protocolVersion" in responses[0]["result"]
        assert responses[0]["result"]["serverInfo"]["name"] == "jevqueue"

    def test_a_byte_order_mark_does_not_swallow_the_request(self):
        # A BOM on the first line is a real thing: every PowerShell pipe adds one.
        responses = run(
            [
                "﻿"
                + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            ]
        )

        assert len(responses) == 1
        assert responses[0]["id"] == 1

    def test_tools_list_is_answered(self):
        responses = run(
            [json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})]
        )

        assert responses[0]["result"]["tools"][0]["name"] == "jevqueue_decide"

    def test_a_notification_gets_no_answer(self):
        responses = run(
            [
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}),
            ]
        )

        assert len(responses) == 1
        assert responses[0]["id"] == 3

    def test_a_malformed_request_with_an_id_gets_an_error_not_silence(self):
        responses = run(['{"jsonrpc":"2.0","id":9,"method":'])

        assert len(responses) == 1
        assert responses[0]["id"] == 9
        assert responses[0]["error"]["code"] == -32700

    def test_an_unknown_method_gets_an_error(self):
        responses = run([json.dumps({"jsonrpc": "2.0", "id": 4, "method": "nope", "params": {}})])

        assert responses[0]["error"]["code"] == -32601

    def test_the_decision_tool_refuses_a_catastrophic_command(self):
        responses = run(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {
                            "name": "jevqueue_decide",
                            "arguments": {"tool": "Bash", "input": {"command": "rm -rf /"}},
                        },
                    }
                )
            ]
        )

        text = responses[0]["result"]["content"][0]["text"]
        verdict = json.loads(text)
        assert verdict["allow"] is False

    def test_the_decision_tool_allows_an_ordinary_command(self):
        responses = run(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 6,
                        "method": "tools/call",
                        "params": {
                            "name": "jevqueue_decide",
                            "arguments": {"tool": "Bash", "input": {"command": "ls -la"}},
                        },
                    }
                )
            ]
        )

        text = responses[0]["result"]["content"][0]["text"]
        assert json.loads(text)["allow"] is True
