"""A governed agent step, with no key, no network and no provider.

This module is the payload of ``python -m jevqueue``. It exists so that the claim
"install it and see the machinery work" is one command, not a paragraph:

.. code-block:: console

    $ pip install jevqueue
    $ python -m jevqueue

The decision is made by :class:`~jevqueue.local.LocalDecisionModel`, the offline rules
baseline, so nothing here reaches the network. The provider is a stand-in that records what
it was asked to do and can be told to misbehave.

Three things are worth watching for.

**The constraint.** The rules route to ``read_file``, so the governor asks the provider for
the arguments of exactly that tool and says so in the directive it sends. The provider is not
asked to choose; it is asked to fill in a form.

**The verification.** A provider is free to call whatever it likes. One that ignores the
constraint is not merely disobedient -- it is wrong, and the whole point of a decision layer
is that a wrong tool call costs something. So the governor refuses to execute it and raises
before anything runs.

**The risk gate.** A destructive tool stops the turn before the provider is called at all,
and the user is told why.

Swap :class:`~jevqueue.local.LocalDecisionModel` for
:class:`~jevqueue.client.JevClient` and every line below still works, with a hosted
decision instead of rules.
"""

from __future__ import annotations

import sys
from typing import Any

from .errors import JevError
from .governor import Governor
from .local import LocalDecisionModel

__all__ = ["DemoHost", "main", "run_demo"]


def _tool(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    }


class DemoHost:
    """A stand-in provider that records what the governor asked it to do.

    It implements the same ``Host`` protocol the real adapters implement, which is what makes
    the demo a genuine exercise of the governor rather than a sketch of one. Set
    ``obey=False`` and the provider calls something other than the tool it was told to call.
    """

    def __init__(
        self,
        *,
        tools: list[dict],
        request: str,
        obey: bool = True,
    ) -> None:
        self._tools = tools
        self._messages = [
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": request},
        ]
        self.obey = obey
        self.generated: list[dict] = []
        self.said: list[str] = []
        self.executed: list[str] = []

    # -- the Host protocol -------------------------------------------------------------------

    def tools(self) -> list[dict]:
        return self._tools

    def messages(self) -> list[dict]:
        return self._messages

    def interrupted(self) -> bool:
        return False

    def generate(self, *, force_tool: str | None, directive: str) -> Any:
        self.generated.append({"force_tool": force_tool, "directive": directive})
        return {"kind": "generated", "force_tool": force_tool}

    def called_tools(self, response: Any) -> list[str]:
        forced = response.get("force_tool") if isinstance(response, dict) else None
        if not forced:
            return []
        if self.obey:
            return [forced]
        return ["delete_everything"]

    def say(self, text: str) -> Any:
        self.said.append(text)
        return {"kind": "said", "text": text}

    def say_tool_call(self, name: str, arguments: dict) -> Any:
        self.executed.append(name)
        return {"kind": "static", "name": name, "arguments": arguments}


def _rule(stream: Any, title: str) -> None:
    print("=" * 74, file=stream)
    print(title, file=stream)
    print("=" * 74, file=stream)


def _event(governor: Governor) -> Any:
    """The recorded event for the step just taken.

    The governor records one on every completed step, so this never returns ``None`` in
    practice; the check exists so a caller is not left with a type it has to guard twice.
    """
    event = governor.last
    if event is None:  # pragma: no cover - the governor always records
        raise JevError("The governor recorded no event for the step")
    return event


def run_demo(stream: Any = None) -> int:
    """Print the three scenarios. Returns a process exit code."""
    out = stream if stream is not None else sys.stdout
    tools = [
        _tool("read_file", "Read a file from disk."),
        _tool("write_file", "Write a file to disk."),
    ]

    _rule(out, "1. The provider is constrained to the tool the decision selected")
    governor = Governor(LocalDecisionModel())
    host = DemoHost(tools=tools, request="read the file notes.txt")
    governor.step(host)

    call = host.generated[0]
    event = _event(governor)
    print(f"   path          : {event.path}", file=out)
    print(f"   action        : {event.action}", file=out)
    print(f"   confidence    : {event.confidence}", file=out)
    print(f"   forced tool   : {call['force_tool']}", file=out)
    print(f"   decision_ms   : {event.decision_ms:.2f}", file=out)
    print("   directive     :", file=out)
    for line in call["directive"].splitlines():
        print(f"     {line}", file=out)

    print(file=out)
    _rule(out, "2. A provider that ignores the constraint is refused before it runs")
    governor = Governor(LocalDecisionModel())
    host = DemoHost(tools=tools, request="read the file notes.txt", obey=False)
    try:
        governor.step(host)
    except JevError as error:
        print(f"   raised        : {type(error).__name__}", file=out)
        print(f"   message       : {error}", file=out)
        print(f"   executed      : {host.executed or 'nothing'}", file=out)
        print(
            "   The error is raised before any effect, which is what makes it safe to retry.",
            file=out,
        )
    else:  # pragma: no cover - the governor must refuse this
        print("   UNEXPECTED: the ignored constraint was not refused", file=out)
        return 1

    print(file=out)
    _rule(out, "3. A destructive tool stops at the risk gate, before the provider is called")
    governor = Governor(LocalDecisionModel())
    host = DemoHost(
        tools=[_tool("delete_file", "Delete a file from disk.")],
        request="delete the file notes.txt",
    )
    governor.step(host)
    event = _event(governor)
    print(f"   path          : {event.path}", file=out)
    print(f"   risk          : {event.risk}", file=out)
    print(
        f"   generated     : {host.generated or 'nothing -- the provider was never called'}",
        file=out,
    )
    print(f"   told the user : {host.said[0][:96]}...", file=out)

    print(file=out)
    print("-" * 74, file=out)
    print(
        "No key. No network. No provider. Same guards as the hosted decision model.",
        file=out,
    )
    print("-" * 74, file=out)
    return 0


def main() -> int:
    """Entry point for ``python -m jevqueue``."""
    return run_demo()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
