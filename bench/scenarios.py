"""A small, labelled workload for the benchmark.

Every scenario states what the agent *should* do, so the harness can report two things that
are usually missing from a benchmark: how the decision layer behaved (**path distribution**,
latency, tokens generated to decide) and how often it routed **correctly** (**accuracy**).

The workload is deliberately small and deterministic. It is not a benchmark of an agent; it is
a benchmark of a **decision**, so that two decision models can be compared on the same inputs
on your machine, with your tools, in one command. A larger corpus would make the numbers
look more impressive and the conclusion no more true.

The expected route is written by hand, from the request, not from any model's opinion. Where
the honest answer is "no tool fits", the expected route is ``delegate`` -- and that is the
case a routing layer most often gets wrong, so it is worth a third of the corpus.
"""

from __future__ import annotations

from typing import Any

__all__ = ["SCENARIOS", "TOOLS"]


def _tool(name: str, description: str, **properties: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {"path": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
        },
    }


#: The toolset every scenario runs against. It is a plausible support-and-dev toolset: big
#: enough that choosing wrongly is a real failure, small enough to keep the workload
#: readable.
TOOLS: list[dict] = [
    _tool("read_file", "Read a file from disk.", path="string"),
    _tool("write_file", "Write a file to disk.", path="string", content="string"),
    _tool("delete_file", "Delete a file from disk.", path="string"),
    _tool("list_directory", "List the files in a directory.", path="string"),
    _tool("search_code", "Search the source tree for a symbol or string.", query="string"),
    _tool("run_tests", "Run the test suite and return the results.", suite="string"),
    _tool("deploy_service", "Deploy a service to production.", service="string"),
    _tool("post_message", "Post a message to a chat channel.", channel="string", text="string"),
]


def _request(text: str) -> list[dict]:
    return [
        {"role": "system", "content": "You are a careful engineering assistant."},
        {"role": "user", "content": text},
    ]


def _answered(text: str) -> list[dict]:
    return [
        {"role": "system", "content": "You are a careful engineering assistant."},
        {"role": "user", "content": text},
        {"role": "assistant", "content": "The notes say hello."},
    ]


#: Each scenario is a name, the messages the agent has, and the route a correct decision
#: layer would take. ``expected`` is a tool name, or one of the control options.
SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "read-a-file",
        "messages": _request("read the file notes.txt"),
        "expected": "read_file",
    },
    {
        "name": "read-another-file",
        "messages": _request("open the file config.yaml"),
        "expected": "read_file",
    },
    {
        "name": "list-a-directory",
        "messages": _request("list the files in the src directory"),
        "expected": "list_directory",
    },
    {
        "name": "search-the-codebase",
        "messages": _request("search the code for the symbol parse_config"),
        "expected": "search_code",
    },
    {
        "name": "run-the-tests",
        "messages": _request("run the tests for the payments suite"),
        "expected": "run_tests",
    },
    {
        "name": "write-a-file",
        "messages": _request("write the file out.txt with the summary"),
        "expected": "write_file",
    },
    {
        "name": "post-to-a-channel",
        "messages": _request("post the release summary to the deploys channel"),
        "expected": "post_message",
    },
    {
        "name": "delete-a-file",
        "messages": _request("delete the file obsolete.log"),
        "expected": "delete_file",
    },
    {
        "name": "deploy-a-service",
        "messages": _request("deploy the checkout service to production"),
        "expected": "deploy_service",
    },
    {
        "name": "the-agent-has-already-answered",
        "messages": _answered("read the file notes.txt"),
        "expected": "finish",
    },
    {
        "name": "no-tool-fits-a-conversation",
        "messages": _request("what do you think about the state of the industry?"),
        "expected": "delegate",
    },
    {
        "name": "no-tool-fits-a-vague-ask",
        "messages": _request("fix it"),
        "expected": "delegate",
    },
    {
        "name": "no-tool-fits-a-question-about-the-model",
        "messages": _request("how many tokens are in your context window?"),
        "expected": "delegate",
    },
    {
        "name": "two-tools-plausible",
        "messages": _request("read the file notes.txt"),
        "expected": "read_file",
        "note": "read_file and search_code both overlap; the winner must be decisive",
    },
]
