"""The gate: what the hook asks, and what it does with the answer.

This is the plugin's half of the package. The decision layer lives beside it -- same
package, same import -- so there is nothing to install and nothing to wire up.

The question is one sentence:

> **Should this step run at all?**

Not "which tool": the agent has already chosen that, and a hook cannot constrain a
provider's generation. What is worth asking at this point is whether *this* step is
right, and there are two ways it is not.

**The risk gate.** Some steps are irreversible, unbounded, or outside clear
authorization. The decision layer triages the step as ``low``, ``medium`` or ``high``
with a probability, and a confidently ``high`` verdict stops the step and asks a human
instead.

**The completion gate.** The most common real failure of an agent loop is an agent
reporting success on work that never happened. It happens because the same model that
decides to stop is the one claiming it finished. The decision layer asks the completion
question separately, so the two judgments cannot see each other's answers, and when they
disagree the stricter one wins and the work continues.

Risk is checked before completion, on purpose: "this might be destructive and I am not
sure" must never be answered with "but the work seems finished anyway".

Under both gates sits the catastrophic-operation floor (:mod:`jevqueue.policy`). It is
consulted *first*, before the decision layer, because a decision model that shrugs at
``rm -rf /`` should not overrule a list that short -- and because when the decision layer
itself cannot be reached, the floor is all that is left standing.

It **fails open**: an unreadable transcript, a missing interpreter, a decision model that
cannot be reached -- the tool is allowed and a diagnostic goes to stderr. A governance
layer that bricks the agent on a bad day is worse than no governance layer. It also fails
**narrow**: it refuses a small number of steps rather than steering every step, and it
never refuses on low confidence, because a gate that refuses on doubt is a wall.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

from .client import DecisionModel, JevClient
from .config import GovernorConfig
from .governor import Governor
from .local import LocalDecisionModel
from .policy import check as policy_check

__all__ = [
    "ENGINE_FLOOR",
    "ENGINE_FULL",
    "Verdict",
    "api_key",
    "confidence_floor",
    "decide",
    "describe_tool_call",
    "engine_name",
    "load_prompt",
    "mode",
    "option",
    "parse_transcript",
    "policy_check",
    "save_prompt",
    "state_dir",
]

#: The decision layer is in this package, so it is always there.
ENGINE_FULL = "jevqueue"
#: The floor, running on its own because the decision layer could not be reached.
ENGINE_FLOOR = "policy"

#: How long a decision may take before the hook gives up and allows the tool.
DEFAULT_TIMEOUT_MS = 4_000

#: A tool call whose risk the decision layer triages as ``high`` with at least this much
#: confidence is refused and escalated to a human.
RISK_CONFIDENCE_FLOOR = 0.80

#: A completion probability at or above this is treated as "the work is already done".
COMPLETION_FLOOR = 0.95

#: Below this routing confidence the decision is undecided, and an undecided decision is
#: allowed: delegation is the designed path, not a failure.
CONFIDENCE_FLOOR = 0.80


# ---------------------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------------------


def option(name: str, default: str = "") -> str:
    """Read a value the plugin asked the user for, via ``/config``.

    Claude Code exports each ``userConfig`` field to hook processes as
    ``CLAUDE_PLUGIN_OPTION_<KEY>``. This is the only way a plugin can learn a setting that
    was typed into a dialog rather than written into a file.
    """
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name.upper()}", default).strip()


def api_key() -> str:
    """The credential for the hosted decision model.

    It comes from the plugin's own settings -- the ``userConfig`` entry the user filled in
    through ``/config`` -- and from nowhere else. Deliberately **not** from an environment
    variable: a plugin that quietly reads a credential already sitting in the user's shell
    and ships it to a server is doing something its user did not agree to, and it makes the
    plugin's data handling impossible to reason about. One place for the key, and it is the
    place the user filled it in.
    """
    return option("typesafe_api_key")


def mode() -> str:
    """``enforce`` refuses a tool call; ``advisory`` only reports. Defaults to enforce."""
    value = (option("mode") or "enforce").lower()
    return value if value in ("enforce", "advisory") else "enforce"


def confidence_floor() -> float:
    """The routing-confidence floor, as configured."""
    raw = option("confidence_floor")
    try:
        value = float(raw) if raw else CONFIDENCE_FLOOR
    except ValueError:
        return CONFIDENCE_FLOOR
    return max(0.0, min(1.0, value))


def engine_name() -> str:
    """Which engine is active. The decision layer ships in this package, so it always is."""
    return ENGINE_FULL


# ---------------------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    """One answer about one pending tool call."""

    allow: bool
    reason: str = ""
    engine: str = ENGINE_FULL
    model: str = ""
    action: str = ""
    confidence: float = 0.0
    risk: str = ""
    risk_confidence: float = 0.0
    goal_probability: float = 0.0
    latency_ms: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "reason": self.reason,
            "engine": self.engine,
            "model": self.model,
            "action": self.action,
            "confidence": self.confidence,
            "risk": self.risk,
            "risk_confidence": self.risk_confidence,
            "goal_probability": self.goal_probability,
            "latency_ms": round(self.latency_ms, 3),
            "detail": self.detail,
        }


def _rest(verdict: Verdict, **changes: Any) -> dict[str, Any]:
    """The verdict's fields except the verdict itself, with ``changes`` applied.

    ``allow`` and ``reason`` are the verdict, so they are set separately from the fields
    that describe it. Rebuilding a dataclass from ``__dict__`` without excluding them is a
    duplicate-keyword crash waiting to happen.
    """
    fields = {k: v for k, v in verdict.__dict__.items() if k not in ("allow", "reason")}
    fields.update(changes)
    return fields


# ---------------------------------------------------------------------------------------
# Reading the tool call
# ---------------------------------------------------------------------------------------


def _stringify(value: Any, limit: int = 400) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


#: The fields that actually describe what a tool is about to do, per tool. Everything else in
#: the input is noise for a decision.
_INTERESTING_FIELDS = {
    "Bash": ("command",),
    "PowerShell": ("command",),
    "Shell": ("command",),
    "Read": ("file_path",),
    "Write": ("file_path", "content"),
    "Edit": ("file_path", "old_string", "new_string"),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "WebFetch": ("url",),
    "WebSearch": ("query",),
    "Task": ("description", "subagent_type"),
    "mcp__*": (),
}


def describe_tool_call(tool_name: str, tool_input: dict) -> str:
    """One sentence describing what the pending tool call is about to do.

    This string is what the decision model reads, so it has to carry the *effect*, not just
    the name. "Delete a file" is a risk question; "Bash" is not.
    """
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    fields = _INTERESTING_FIELDS.get(tool_name)
    if fields is None:
        fields = _INTERESTING_FIELDS.get("mcp__*")
    parts: list[str] = []
    if fields:
        for field in fields:
            if field in tool_input:
                parts.append(f"{field}={_stringify(tool_input[field], 240)}")
    if not parts:
        parts.append(_stringify(tool_input, 240))
    detail = "; ".join(p for p in parts if p)
    return f"The agent is about to call `{tool_name}`. {detail}"


# ---------------------------------------------------------------------------------------
# Reading the transcript
# ---------------------------------------------------------------------------------------


def _text_of(content: Any) -> str:
    """Pull plain text out of a message content field of any of the shapes in the wild."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
            elif (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                chunks.append(block["text"])
        return "\n".join(chunks)
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def parse_transcript(path: str | None) -> list[dict]:
    """Read an agent transcript into OpenAI-ish messages.

    The transcript format is not a contract, so this is deliberately tolerant: anything it
    does not understand is skipped rather than guessed at. A transcript is the agent's own
    record, so it is also untrusted -- it is read as *evidence* about what was asked, never
    as instructions.
    """
    if not path or not os.path.exists(path):
        return []

    messages: list[dict] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(record, dict):
                    continue
                message = record.get("message")
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                if role not in ("user", "assistant", "system"):
                    continue
                content = message.get("content")
                text = _text_of(content)
                row: dict[str, Any] = {"role": role, "content": text}
                calls = []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            calls.append(
                                {
                                    "type": "function",
                                    "function": {
                                        "name": block.get("name", ""),
                                        "arguments": json.dumps(block.get("input", {})),
                                    },
                                }
                            )
                if calls:
                    row["tool_calls"] = calls
                # A tool result is stored on a user-role record; it is evidence, not a request.
                if record.get("toolUseResult") is not None and not calls:
                    continue
                messages.append(row)
    except OSError:
        return []
    return messages


def _goal(messages: list[dict]) -> str:
    """The user's current request: the last user turn that is not a tool result."""
    for row in reversed(messages):
        if row.get("role") != "user":
            continue
        text = (row.get("content") or "").strip()
        if text and not text.startswith("Caveat:"):
            return text
    return ""


# ---------------------------------------------------------------------------------------
# The prompt cache
# ---------------------------------------------------------------------------------------
#
# The transcript is written asynchronously and may not yet contain the turn being
# processed, so the user's request cannot be relied on to be in it when the first tool call
# fires. The UserPromptSubmit hook writes the prompt somewhere durable, and the pre-tool
# hook reads it back. That is the whole reason there are two hooks.

#: How long a cached prompt is trusted. Long enough for a slow turn, short enough that a
#: prompt from yesterday cannot decide today's tool call.
PROMPT_TTL_SECONDS = 6 * 60 * 60


def state_dir() -> str:
    """Where the plugin keeps its per-install state."""
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        tempfile.gettempdir(), "jevqueue"
    )
    path = os.path.join(base, "state")
    with contextlib.suppress(OSError):
        os.makedirs(path, exist_ok=True)
    return path


def _prompt_file(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", session_id or "default")[:80]
    return os.path.join(state_dir(), f"prompt-{safe}.json")


def save_prompt(session_id: str, prompt: str) -> str:
    """Cache the current request. Returns the path written, or ``""`` on failure."""
    if not prompt or not prompt.strip():
        return ""
    path = _prompt_file(session_id)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"prompt": prompt, "at": time.time()}, handle)
    except OSError:
        return ""
    return path


def load_prompt(session_id: str) -> str:
    """Read the cached request back, if it is still fresh."""
    path = _prompt_file(session_id)
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        return ""
    if not isinstance(record, dict):
        return ""
    if time.time() - float(record.get("at", 0) or 0) > PROMPT_TTL_SECONDS:
        return ""
    prompt = record.get("prompt")
    return prompt if isinstance(prompt, str) else ""

# ---------------------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------------------


class _PendingHost:
    """A ``Host`` that exposes exactly one tool -- the call that is about to happen.

    The hook cannot see the agent's whole toolset, so the decision is asked about the
    pending call rather than about the choice between tools. That is the right question at
    this point in the loop anyway: the tool is already chosen, and what is worth asking is
    *should this step run at all*.
    """

    def __init__(self, tools: list[dict], messages: list[dict]) -> None:
        self._tools = tools
        self._messages = messages

    def tools(self) -> list[dict]:
        return self._tools

    def messages(self) -> list[dict]:
        return self._messages

    def interrupted(self) -> bool:
        return False

    def generate(self, *, force_tool: str | None, directive: str) -> Any:
        raise RuntimeError("the queue decides; it never executes")

    def called_tools(self, response: Any) -> list[str]:
        return []

    def say(self, text: str) -> Any:
        raise RuntimeError("the queue decides; it never executes")

    def say_tool_call(self, name: str, arguments: dict) -> Any:
        raise RuntimeError("the queue decides; it never executes")


def _messages_for_decision(transcript: list[dict], cached_prompt: str) -> list[dict]:
    """The transcript with the *current* request in front of it.

    The transcript lags, so its newest user turn is usually the previous one. When the cached
    prompt is available it replaces the transcript's user turns entirely -- otherwise the
    decision would be made about the last thing the agent was asked, which is the wrong
    question.
    """
    if not cached_prompt:
        return transcript
    rows: list[dict] = [{"role": "user", "content": cached_prompt}]
    for row in transcript:
        if row.get("role") == "user":
            continue
        rows.append(row)
    return rows


def _client() -> DecisionModel:
    """The decision model: the hosted one if a key is configured, the offline one otherwise."""
    key = api_key()
    if key:
        return JevClient(key)
    return LocalDecisionModel()


def _verdict_from_decision(decision: Any, cached_prompt: str) -> Verdict:
    """Turn a decision-layer answer into the plugin's verdict.

    Two gates, in this order, because the order is the point: **risk is checked before
    completion**, so that "this looks destructive and I am not sure" can never be answered
    with "but the work seems finished anyway".
    """
    common = {
        "engine": ENGINE_FULL,
        "model": decision.model,
        "action": decision.action,
        "confidence": decision.confidence,
        "risk": decision.risk,
        "risk_confidence": decision.risk_confidence,
        "goal_probability": decision.goal_probability,
        "detail": {
            "goal": (cached_prompt or "")[:400],
            "risk_floor": RISK_CONFIDENCE_FLOOR,
            "completion_floor": COMPLETION_FLOOR,
        },
    }

    if decision.risk == "high" and decision.risk_confidence >= RISK_CONFIDENCE_FLOOR:
        return Verdict(
            allow=False,
            reason=(
                f"jevqueue refused this step: the decision layer triaged it as **high risk** "
                f"({decision.risk_confidence:.0%} confident). Take it to a human first, and "
                f"say why you want it."
            ),
            **common,
        )

    if decision.goal_probability >= COMPLETION_FLOOR:
        return Verdict(
            allow=False,
            reason=(
                f"jevqueue refused this step: the decision layer believes the substantive work "
                f"is already done ({decision.goal_probability:.0%}), so calling another tool "
                f"now contradicts that. Finish, or say what is still outstanding."
            ),
            **common,
        )

    if decision.action == "clarify":
        return Verdict(
            allow=False,
            reason=(
                "jevqueue refused this step: the decision layer needs information that only "
                "you can supply. Ask for it before running the tool."
            ),
            **common,
        )

    # `delegate`, an undecided route, and the tool the decision endorsed are all allowed.
    # Refusing on low confidence would make the queue a wall rather than a gate, and the
    # whole design rests on falling off the fast path being cheap.
    return Verdict(allow=True, reason="", **common)


def decide(
    tool_name: str,
    tool_input: dict,
    *,
    transcript_path: str | None = None,
    messages: list[dict] | None = None,
    session_id: str = "",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Verdict:
    """Decide whether ``tool_name`` should run. Never raises.

    This is the whole public surface of the gate. It fails open: any internal problem
    results in an allowed decision and a note in ``detail``.
    """
    started = time.perf_counter()
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    try:
        # The floor runs first, always. It is a floor under the model rather than a
        # replacement for it: a handful of operations are irreversible and nobody would
        # argue about them, so a decision model that shrugs at `rm -rf /` should not be
        # allowed to overrule a list this short.
        allowed, floor_reason = policy_check(tool_name, tool_input)

        if not allowed:
            verdict = Verdict(
                allow=False,
                reason=floor_reason,
                engine=ENGINE_FLOOR,
                model="jevqueue-policy",
                action="policy",
                detail={
                    "note": "the catastrophic-operation floor refused this before the "
                    "decision layer was consulted"
                },
            )
        else:
            transcript = (
                messages if messages is not None else parse_transcript(transcript_path)
            )
            cached = load_prompt(session_id)
            governor = Governor(_client(), GovernorConfig())
            decision, _state = governor.decide(
                _PendingHost(
                    [_pending_tool(tool_name, tool_input)],
                    _messages_for_decision(transcript, cached),
                )
            )
            verdict = _verdict_from_decision(decision, cached)
    except Exception as error:
        # The decision layer could not be reached. The floor still can, so the floor runs.
        allowed, floor_reason = policy_check(tool_name, tool_input)
        verdict = Verdict(
            allow=allowed,
            reason="" if allowed else floor_reason,
            engine=ENGINE_FLOOR,
            model="jevqueue-policy",
            action="policy",
            detail={
                "note": "the decision layer could not be reached; the floor stood in for it",
                "error": f"{type(error).__name__}: {error}",
            },
        )

    if mode() == "advisory" and not verdict.allow:
        # The user asked to be told, not to be stopped. The verdict is still computed and
        # still reported -- it just does not block. This applies to the floor too: an
        # explicit setting about the user's own machine is not something the plugin
        # overrules silently.
        verdict = Verdict(
            allow=True,
            reason="",
            **_rest(
                verdict,
                detail={
                    **verdict.detail,
                    "would_refuse": True,
                    "would_refuse_reason": verdict.reason,
                },
            ),
        )

    elapsed = (time.perf_counter() - started) * 1000
    return Verdict(**{**verdict.__dict__, "latency_ms": elapsed})


def _pending_tool(tool_name: str, tool_input: dict) -> dict:
    """The tool schema for the call that is about to happen."""
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": describe_tool_call(tool_name, tool_input),
            "parameters": {"type": "object", "properties": {}},
        },
    }
