---
name: jevqueue-adapter
description: >-
  Add a decision queue to an agent framework. Use when you are writing a host adapter for a
  framework that jevqueue does not cover yet, when you need to make a framework's tool calls
  constrainable, or when you are porting the decision layer into a new agent runtime. Covers
  the seven-method host protocol, the four mandatory tests, and the reference implementations
  for OpenAI-compatible loops and LangChain. Do not use when you only want to install the
  plugin, or when you are writing a plugin rather than an adapter.
---

# Adding a decision queue to a framework

A framework is governable when it can answer seven questions about one step. That is the
whole surface.

## The seven-method host protocol

```python
class Host:
    def tools(self) -> list[dict]:
        """The tools available for THIS step, as OpenAI-style schemas:
        [{"type": "function", "function": {"name", "description", "parameters"}}, ...]
        """

    def messages(self) -> list[dict]:
        """The conversation so far, oldest-first, in OpenAI message form:
        {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
        """

    def generate(self, *, force_tool: str | None, directive: str) -> Any:
        """Run the generative model for one step and return the framework's native response.
        When force_tool is a tool name, the host MUST constrain the provider to call exactly
        that function once. When it is None, the host must forbid tool calls entirely.
        """

    def called_tools(self, response: Any) -> list[str]:
        """The tool names the provider actually called. Used to verify the constraint.
        Return an empty list for a plain prose reply.
        """

    def say(self, text: str) -> Any:
        """A native response carrying text as the assistant's reply, with no model call."""

    def say_tool_call(self, name: str, arguments: dict) -> Any:
        """A native response that calls name with arguments, with no model call."""

    def interrupted(self) -> bool:
        """Whether the user asked to stop since the decision began."""
```

Two of these carry the architecture:

- **`generate` must genuinely constrain.** A named `tool_choice` is a provider-level
  constraint; a sentence in the prompt is a suggestion. With OpenAI-compatible APIs that is
  `tool_choice={"type": "function", "function": {"name": ...}}` plus
  `parallel_tool_calls=False`. If the framework cannot force a named tool, say so loudly in
  the adapter's docstring — an adapter that advises reads as a guarantee while providing none.
- **`called_tools` must report the truth.** It is the only way to notice a provider that
  ignored the constraint.

## The four mandatory tests

An adapter is not finished until these pass. They are the definition of an honest adapter.

1. **The constraint reaches the provider.** With a tool selected, the request names exactly
   that tool and forbids parallel calls.
2. **A provider that ignores the constraint is refused.** Return a different tool from
   `called_tools`. The turn must raise, and *nothing may execute*.
3. **Delegation is a true passthrough.** When the decision is `delegate`, the provider is
   called with no constraint at all — the agent behaves exactly as it did before the adapter
   was installed.
4. **`say` makes no network call.** The clarification and risk-stop paths must not reach the
   provider.

The inverse case is worth a fifth test where the framework allows it: **a tool call after a
`finish` decision is also refused.**

## Reference implementations

**OpenAI-compatible loops.** The host is a thin wrapper over the chat completion call.
Constrain with `tool_choice` and `parallel_tool_calls=False`; read the tool calls back off the
response.

**LangChain.** Implement `bind_tools` so it binds to *your* model rather than to the
provider — if it binds to the provider, the governor never runs. To force a tool, re-issue
with `model.bind_tools(tools, tool_choice=force_tool)`; to finish, re-issue with no tools
bound at all.

## Porting to an agent runtime that has hooks

A CLI agent that supports a **pre-tool hook** does not need the provider to be constrained,
because the hook can refuse the call instead. That is a different, weaker guarantee and it is
worth being precise about which one you have:

- **The provider-level constraint** picks the tool. The provider is constrained and the result
  is checked. This is the strong guarantee.
- **The pre-tool hook** verifies a tool the agent already chose. It cannot redirect the choice,
  but it can refuse a step the decision layer says should not run, and it can escalate a risky
  one. This is the guardrail guarantee.

Say which one your adapter provides. An agent that believes it has the first when it has the
second is the exact failure this whole design exists to prevent.

## Checklist

- [ ] All seven methods implemented, frameworks imported lazily so an uninstalled framework is
      an error at call time rather than import time.
- [ ] The four mandatory tests pass, and the "provider ignored the constraint" test asserts
      that **nothing executed**.
- [ ] The suite runs with no network, no API key and no provider.
- [ ] The docstring says what the adapter cannot do.
