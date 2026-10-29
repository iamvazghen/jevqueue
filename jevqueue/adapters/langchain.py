"""Adapter for LangChain, as a chat-model wrapper.

LangChain gives this package the largest audience of any framework it supports, and the
install is the cleanest of them: a chat model is just a chat model, so wrapping one means
**no change to your agent, your tools, or your chain** -- you build the chain with
``GovernedChatModel(model)`` instead of ``model`` and nothing else moves.

.. code-block:: python

   from langchain.agents import create_agent
   from langchain.chat_models import init_chat_model
   from jevqueue.adapters.langchain import GovernedChatModel

   model = GovernedChatModel(init_chat_model("openai:gpt-4o"))
   agent = create_agent(model, tools=[check_port, read_log])

How the constraint is applied, which is the part specific to this framework. LangChain's
``bind_tools`` accepts ``tool_choice``, and a **named** ``tool_choice`` is a provider-level
constraint -- the same one OpenAI's ``tool_choice`` is -- not a prompt instruction. So to
force one tool, the request is re-issued with ``tool_choice=<that tool>``. To finish, the
request is re-issued with **no tools bound at all**, so prose is the only legal move.

Two honest limitations.

**The provider has to support a named ``tool_choice``.** OpenAI-compatible providers do.
Others may accept the field and ignore it, and LangChain's own ``bind_tools`` docstring
treats the argument as advisory for some providers. That is exactly why the constraint is
*verified* rather than trusted: :meth:`~jevqueue.governor.Governor.step` checks what came
back against what was asked for, and a provider that ignored the constraint raises before
anything executes. A provider that cannot constrain is not unsafe here -- it is simply
governed less tightly, and the check is what tells you so.

**Streaming is not governed.** This wrapper implements ``_generate``, the non-streaming path.
A streaming call goes to the wrapped model ungoverned, and says so in
[docs/limits.md](../../docs/limits.md) rather than pretending otherwise.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..client import DecisionModel, JevClient
from ..config import GovernorConfig
from ..errors import JevError
from ..governor import Governor

try:  # pragma: no cover - import shape depends on the installed extra
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.utils.function_calling import convert_to_openai_tool

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False


def _require_langchain() -> None:
    if not _AVAILABLE:
        raise JevError(
            "The LangChain adapter needs langchain-core "
            "(pip install 'jevqueue[langchain]')"
        )


def _messages(messages: list[Any]) -> list[dict]:
    """Project LangChain messages into the OpenAI-ish rows the state projection reads.

    Only text and tool calls are carried, which is all a routing decision needs. A tool call
    is projected into the OpenAI shape with ``arguments`` as a JSON string, because that is
    what the field means everywhere else in this package.
    """
    rows: list[dict] = []
    for message in messages:
        kind = getattr(message, "type", "")
        content = getattr(message, "content", "") or ""
        if kind == "system":
            rows.append({"role": "system", "content": content if isinstance(content, str) else ""})
        elif kind in ("human", "user"):
            rows.append({"role": "user", "content": content if isinstance(content, str) else ""})
        elif kind == "ai":
            row: dict[str, Any] = {
                "role": "assistant",
                "content": content if isinstance(content, str) else "",
            }
            calls = getattr(message, "tool_calls", None) or []
            if calls:
                row["tool_calls"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": json.dumps(call.get("args", {})),
                        },
                    }
                    for call in calls
                ]
            rows.append(row)
        elif kind == "tool":
            rows.append(
                {
                    "role": "tool",
                    "name": getattr(message, "name", "") or "",
                    "content": content if isinstance(content, str) else "",
                }
            )
    return rows


class _Host:
    """A :class:`~jevqueue.host.Host` over one LangChain model call."""

    def __init__(self, model: Any, messages: list[Any], tools: list[dict], kwargs: dict) -> None:
        self.model = model
        self._messages = messages
        self._tools = tools
        self._kwargs = kwargs

    def tools(self) -> list[dict]:
        return self._tools

    def messages(self) -> list[dict]:
        return _messages(self._messages)

    def interrupted(self) -> bool:
        return False  # LangChain cancels the run itself; there is no flag to consult.

    def generate(self, *, force_tool: str | None, directive: str) -> Any:
        messages = list(self._messages)
        if directive:
            messages = [*messages, HumanMessage(content=directive)]

        # `tools` and `tool_choice` are dropped: this host decides the constraint for this
        # step, so a caller's own `tool_choice` must not leak through and override it.
        kwargs = {
            key: value
            for key, value in self._kwargs.items()
            if key not in ("tools", "tool_choice")
        }

        if force_tool is not None:
            bound = self.model.bind_tools(self._tools, tool_choice=force_tool)
        else:
            # No tools bound: prose is the only legal move.
            bound = self.model

        return bound.invoke(messages, **kwargs)

    def called_tools(self, response: Any) -> list[str]:
        return [
            call.get("name", "")
            for call in (getattr(response, "tool_calls", None) or [])
        ]

    def say(self, text: str) -> Any:
        return AIMessage(content=text)

    def say_tool_call(self, name: str, arguments: dict) -> Any:
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": arguments, "id": "jevqueue-local"}],
        )


class GovernedChatModel(BaseChatModel if _AVAILABLE else object):  # type: ignore[misc,valid-type]
    """A LangChain chat model that routes each step through a decision model first.

    .. code-block:: python

       from langchain.chat_models import init_chat_model
       from jevqueue.adapters.langchain import GovernedChatModel

       model = GovernedChatModel(init_chat_model("openai:gpt-4o"))
       model = model.bind_tools([check_port, read_log])

    ``api_key`` defaults to ``TYPESAFE_API_KEY`` from the environment, so a deployment that
    already sets it needs no argument at all. Pass ``client=LocalDecisionModel()`` to govern
    with the offline rules baseline instead -- no credential, no network.
    """

    wrapped: Any = None
    governor: Any = None

    def __init__(
        self,
        wrapped: Any,
        *,
        api_key: str | None = None,
        config: GovernorConfig | None = None,
        client: DecisionModel | None = None,
        **kwargs: Any,
    ) -> None:
        _require_langchain()
        settings = config or GovernorConfig()
        if client is None:
            key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY", "")
            client = JevClient(key, model=settings.model, timeout=settings.timeout)
        super().__init__(wrapped=wrapped, governor=Governor(client, settings), **kwargs)

    @property
    def _llm_type(self) -> str:
        return f"jevqueue:{getattr(self.wrapped, '_llm_type', 'model')}"

    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Bind tools to *this* model, so the governor still runs.

        The base class leaves this to each provider, and a provider's implementation binds to
        the provider -- which would skip the governor entirely. Binding to ``self`` keeps the
        decision in the loop; the step's real constraint is applied later, by the host, where
        it can be checked.
        """
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        return self.bind(tools=formatted, tool_choice=tool_choice, **kwargs)

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        tools = kwargs.get("tools") or []
        host = _Host(self.wrapped, messages, list(tools), dict(kwargs))

        response = self.governor.step(host)

        return ChatResult(generations=[ChatGeneration(message=response)])
