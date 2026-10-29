"""The LangChain adapter, against a real LangChain chat model.

The fake below is a genuine ``BaseChatModel``, so the plumbing under test is LangChain's:
``bind_tools`` binds to the model, ``invoke`` reaches ``_generate``, and the bound kwargs
arrive there. That matters because the adapter's whole job is to keep the governor in the
middle of that path, and a mock would not prove it does.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from jevqueue import JevError, LocalDecisionModel
from jevqueue.adapters.langchain import GovernedChatModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableBinding
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

READ = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file from disk.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}
WRITE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write a file to disk.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}


class FakeChatModel(BaseChatModel):
    """A provider that honours a named ``tool_choice`` -- and can be told not to."""

    obey: bool = True
    seen: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        return self.bind(tools=formatted, tool_choice=tool_choice, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append({"kwargs": dict(kwargs), "messages": list(messages)})
        tool_choice = kwargs.get("tool_choice")
        if isinstance(tool_choice, str):
            name = tool_choice if self.obey else "some_other_tool"
            message = AIMessage(
                content="",
                tool_calls=[{"name": name, "args": {"path": "notes.txt"}, "id": "call-1"}],
            )
        else:
            message = AIMessage(content="The notes say hello.")
        return ChatResult(generations=[ChatGeneration(message=message)])


def governed(model: FakeChatModel) -> GovernedChatModel:
    return GovernedChatModel(model, client=LocalDecisionModel())


class TestTheConstraint:
    def test_binding_tools_keeps_the_governor_in_the_loop(self):
        model = governed(FakeChatModel())

        bound = model.bind_tools([READ])

        # Not bound to the provider: bound to the governed model, or the governor never runs.
        assert isinstance(bound, RunnableBinding)
        assert bound.bound is model

    def test_the_provider_is_constrained_to_the_selected_tool(self):
        provider = FakeChatModel()
        model = governed(provider)
        bound = model.bind_tools([READ, WRITE])

        response = bound.invoke(
            [
                SystemMessage(content="You are a careful assistant."),
                HumanMessage(content="read the file notes.txt"),
            ]
        )

        assert response.tool_calls[0]["name"] == "read_file"
        # The constraint was a named tool_choice, which is the provider-level constraint.
        assert provider.seen[-1]["kwargs"]["tool_choice"] == "read_file"

    def test_a_provider_that_ignores_the_constraint_is_refused(self):
        provider = FakeChatModel(obey=False)
        model = governed(provider)
        bound = model.bind_tools([READ, WRITE])

        with pytest.raises(JevError, match="ignored the selected tool"):
            bound.invoke(
                [
                    SystemMessage(content="You are a careful assistant."),
                    HumanMessage(content="read the file notes.txt"),
                ]
            )

    def test_a_finish_binds_no_tools_at_all(self):
        provider = FakeChatModel()
        model = governed(provider)
        bound = model.bind_tools([READ, WRITE])

        response = bound.invoke(
            [
                SystemMessage(content="You are a careful assistant."),
                HumanMessage(content="read the file notes.txt"),
                AIMessage(content="The notes say hello."),
            ]
        )

        # Prose is the only legal move, so no tools were offered and none were called.
        assert response.tool_calls == []
        assert "tools" not in provider.seen[-1]["kwargs"]


class TestTheProjection:
    def test_it_projects_langchain_messages_into_the_state_shape(self):
        from jevqueue.adapters.langchain import _messages

        rows = _messages(
            [
                SystemMessage(content="You are a careful assistant."),
                HumanMessage(content="read the file notes.txt"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_file", "args": {"path": "a"}, "id": "1"}],
                ),
                ToolMessage(content="hello", tool_call_id="1"),
            ]
        )

        assert rows[0] == {"role": "system", "content": "You are a careful assistant."}
        assert rows[1] == {"role": "user", "content": "read the file notes.txt"}
        assert rows[2]["role"] == "assistant"
        assert rows[2]["tool_calls"][0]["function"]["name"] == "read_file"
        assert rows[3]["role"] == "tool"

    def test_tool_call_arguments_are_carried_as_json(self):
        import json

        from jevqueue.adapters.langchain import _messages

        rows = _messages(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_file", "args": {"path": "a"}, "id": "1"}],
                )
            ]
        )

        arguments = rows[0]["tool_calls"][0]["function"]["arguments"]
        assert json.loads(arguments) == {"path": "a"}


class TestItsLimits:
    def test_it_needs_langchain_core_installed(self):
        import jevqueue.adapters.langchain as adapter

        # The adapter raises a JevError naming the extra rather than an ImportError.
        adapter._AVAILABLE = False
        try:
            with pytest.raises(JevError, match="langchain"):
                governed(FakeChatModel())
        finally:
            adapter._AVAILABLE = True

    def test_the_llm_type_names_the_governed_model(self):
        model = governed(FakeChatModel())

        assert model._llm_type == "jevqueue:fake"
