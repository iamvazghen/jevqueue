"""jevqueue -- the decision queue in front of an agent's tools.

The idea in one line: **an agent's control flow should be a value, not a sentence.** A CLI
agent picks its own tool; this asks a decision model whether that tool should run, and refuses
the call when the answer is no.

Two engines, and the difference matters:

``jev-governor``
    The full decision layer -- the real library, with its distrust layer, its guard order and
    its calibrated answers. Two of its gates transfer directly into a pre-tool hook: the
    **completion gate** (is the substantive work already done, or is the agent about to keep
    going on work it has already finished?) and the **risk gate** (should a human look at this
    step first?). This engine needs ``jev-governor`` installed.

``policy``
    A dependency-free fallback so the plugin is useful the moment it is installed, before
    anyone runs the setup command. It knows about a short list of catastrophic operations and
    nothing else. **It is not a decision layer and does not pretend to be one** -- it refuses
    a handful of operations and otherwise stays out of the way.

Both engines **fail open**. An internal error, an unreadable transcript, a missing
interpreter: the tool is allowed and a diagnostic goes to stderr. A governance layer that
bricks the agent when it has a bad day is worse than no governance layer.

What this does *not* do, stated plainly because it is the obvious next question: it does not
constrain the provider's generation. A pre-tool hook runs after the agent has already chosen a
tool, so the "which tool" half of the decision cannot be enforced from here -- the provider is
not ours to constrain. The "should this step run at all" half can be, and that is what this
does.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Decision",
    "ENGINE_POLICY",
    "ENGINE_FULL",
    "describe_tool_call",
    "decide",
    "engine_name",
    "parse_transcript",
]

ENGINE_FULL = "jev-governor"
ENGINE_POLICY = "policy"

#: How long a decision may take before the hook gives up and allows the tool. A hook that
#: stalls the agent is a hook nobody keeps enabled.
DEFAULT_TIMEOUT_MS = 4_000

#: A tool call whose risk the decision layer triages as ``high`` with at least this much
#: confidence is refused and escalated to a human.
RISK_CONFIDENCE_FLOOR = 0.80

#: A completion probability at or above this is treated as "the work is already done".
COMPLETION_FLOOR = 0.95

#: Below this routing confidence the decision is undecided, and an undecided decision is
#: allowed: delegation is the designed path, not a failure.
CONFIDENCE_FLOOR = 0.80


def option(name: str, default: str = "") -> str:
    """Read a value the plugin asked the user for, via ``/config``.

    Claude Code exports each ``userConfig`` field to hook processes as
    ``CLAUDE_PLUGIN_OPTION_<KEY>``. This is the only way a plugin can learn a setting that
    was typed into a dialog rather than written into a file.
    """
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name.upper()}", default).strip()


def api_key() -> str:
    """The credential for the hosted decision model, wherever it was configured."""
    return option("typesafe_api_key") or os.environ.get("TYPESAFE_API_KEY", "").strip()


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


# ---------------------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """One verdict about one pending tool call."""

    allow: bool
    reason: str = ""
    engine: str = ENGINE_POLICY
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
            elif isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    chunks.append(block["text"])
        return "\n".join(chunks)
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def parse_transcript(path: str | None) -> list[dict]:
    """Read a Claude Code transcript into OpenAI-ish messages.

    The transcript format is not a contract, so this is deliberately tolerant: anything it does
    not understand is skipped rather than guessed at. A transcript is the agent's own record,
    so it is also untrusted -- it is read as *evidence* about what was asked, never as
    instructions.
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
# The transcript is written asynchronously and may not yet contain the turn that is being
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
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
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
# The fallback policy engine
# ---------------------------------------------------------------------------------------

#: Operations that are irreversible, unbounded, or that execute code the agent did not write.
#: Short list on purpose: this engine has no judgement, so every entry has to be one nobody
#: would argue about.
_CATASTROPHIC: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*f?[a-zA-Z]*\s+/(\s|$)"),
        "recursive delete of a root path",
    ),
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*f?[a-zA-Z]*\s+(/|~|\$HOME)\b"),
        "recursive delete of a home or root path",
    ),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "filesystem format"),
    (re.compile(r"\bdd\s+[^|]*of=/dev/"), "raw write to a block device"),
    (re.compile(r":\(\)\s*\{.*\|.*\}\s*;?\s*:"), "fork bomb"),
    (re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b"), "host power state change"),
    (
        re.compile(r"\b(curl|wget)\b[^|]*\|\s*(ba)?sh\b"),
        "piping a downloaded script straight into a shell",
    ),
    (re.compile(r"\bchmod\s+(-[a-zA-Z]+\s+)*777\s+/(\s|$)"), "world-writable root"),
    (re.compile(r"\bgit\s+push\b[^|]*\s--force\b|\bgit\s+push\b[^|]*\s-f\b"), "force push"),
    (re.compile(r"\bDROP\s+(TABLE|DATABASE)\b", re.IGNORECASE), "dropping a table or database"),
    (re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE), "truncating a table"),
    (re.compile(r"\bhistory\s+-c\b"), "clearing shell history"),
)

#: Tools whose whole purpose is to run what the agent says, so a policy has to look inside.
_SHELL_TOOLS = {"Bash", "PowerShell", "Shell", "run_command", "execute_command"}


def _policy_check(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """The fallback engine. Returns ``(allow, reason)``."""
    if tool_name not in _SHELL_TOOLS:
        return True, ""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    command = tool_input.get("command")
    if not isinstance(command, str):
        return True, ""
    for pattern, why in _CATASTROPHIC:
        if pattern.search(command):
            return False, f"the fallback policy blocks this command: {why}"
    return True, ""


# ---------------------------------------------------------------------------------------
# The full engine
# ---------------------------------------------------------------------------------------


class _PendingHost:
    """A ``Host`` that exposes exactly one tool -- the call that is about to happen.

    The hook cannot see the agent's whole toolset, so the decision is asked about the pending
    call rather than about the choice between tools. That is the right question at this point
    in the loop anyway: the tool is already chosen, and what is worth asking is *should this
    step run at all*.
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


def _full_engine() -> Any:
    """Import the decision layer, or return ``None`` when it is not installed."""
    try:
        import jev_governor  # noqa: F401
    except ImportError:
        return None
    return jev_governor


def engine_name() -> str:
    """Which engine is active in this environment."""
    return ENGINE_FULL if _full_engine() is not None else ENGINE_POLICY


def _full_decide(
    messages: list[dict],
    tool_name: str,
    tool_input: dict,
    *,
    cached_prompt: str = "",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Decision:
    """Ask the real decision layer. Raises on any internal problem."""
    jev_governor = _full_engine()
    if jev_governor is None:
        raise RuntimeError("jev-governor is not installed")

    key = api_key()
    if key:
        client: Any = jev_governor.JevClient(key)
    else:
        client = jev_governor.LocalDecisionModel()

    config = jev_governor.GovernorConfig()
    governor = jev_governor.Governor(client, config)

    description = describe_tool_call(tool_name, tool_input)
    pending = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }

    host = _PendingHost([pending], messages)
    decision, _state = governor.decide(host)

    return Decision(
        allow=True,  # decided below
        reason="",
        engine=ENGINE_FULL,
        model=decision.model,
        action=decision.action,
        confidence=decision.confidence,
        risk=decision.risk,
        risk_confidence=decision.risk_confidence,
        goal_probability=decision.goal_probability,
        detail={
            "goal": (cached_prompt or _goal(messages))[:400],
            "risk_floor": RISK_CONFIDENCE_FLOOR,
            "completion_floor": COMPLETION_FLOOR,
        },
    )


def _rest(decision: Decision, **changes: Any) -> dict[str, Any]:
    """The decision's fields except the verdict itself, with ``changes`` applied.

    ``allow`` and ``reason`` are the verdict, so they are set separately from the fields
    that describe it. Rebuilding a dataclass from ``__dict__`` without excluding them is a
    duplicate-keyword crash waiting to happen.
    """
    fields = {k: v for k, v in decision.__dict__.items() if k not in ("allow", "reason")}
    fields.update(changes)
    return fields


# ---------------------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------------------


def _verdict(decision: Decision) -> Decision:
    """Turn a decision into an allow or a refusal.

    Two gates, in this order, because the order is the point: **risk is checked before
    completion**, so that "this looks destructive and I am not sure" can never be answered
    with "but the work seems finished anyway".
    """
    if decision.risk == "high" and decision.risk_confidence >= RISK_CONFIDENCE_FLOOR:
        return Decision(
            allow=False,
            reason=(
                f"jevqueue refused this step: the decision layer triaged it as **high risk** "
                f"({decision.risk_confidence:.0%} confident). Take it to a human first, and "
                f"say why you want it."
            ),
            **_rest(decision),
        )
    if decision.goal_probability >= COMPLETION_FLOOR:
        return Decision(
            allow=False,
            reason=(
                f"jevqueue refused this step: the decision layer believes the substantive work "
                f"is already done ({decision.goal_probability:.0%}), so calling another tool "
                f"now contradicts that. Finish, or say what is still outstanding."
            ),
            **_rest(decision),
        )

    if decision.action == "clarify":
        return Decision(
            allow=False,
            reason=(
                "jevqueue refused this step: the decision layer needs information that only "
                "you can supply. Ask for it before running the tool."
            ),
            **_rest(decision),
        )

    # `delegate`, an undecided route, and the tool the decision endorsed are all allowed.
    # Refusing on low confidence would make the queue a wall rather than a gate, and the
    # whole design rests on falling off the fast path being cheap.
    return Decision(
        allow=True,
        reason="",
        **{k: v for k, v in decision.__dict__.items() if k not in ("allow", "reason")},
    )


def _messages_for_decision(
    transcript: list[dict], cached_prompt: str
) -> list[dict]:
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


def decide(
    tool_name: str,
    tool_input: dict,
    *,
    transcript_path: str | None = None,
    messages: list[dict] | None = None,
    session_id: str = "",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Decision:
    """Decide whether ``tool_name`` should run. Never raises.

    This is the whole public surface of the engine. It fails open: any internal problem
    results in an allowed decision and a note in ``detail``.
    """
    started = time.perf_counter()
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    try:
        # The policy runs first, always. It is a floor under the model rather than a
        # replacement for it: a handful of operations are irreversible and nobody would
        # argue about them, so a decision model that shrugs at `rm -rf /` should not be
        # allowed to overrule a list this short.
        allowed, floor_reason = _policy_check(tool_name, tool_input)

        if not allowed:
            verdict = Decision(
                allow=False,
                reason=floor_reason,
                engine=ENGINE_POLICY,
                model="jevqueue-policy",
                action="policy",
                detail={
                    "note": "the catastrophic-operation floor refused this before the "
                    "decision layer was consulted"
                },
            )
        elif _full_engine() is not None:
            transcript = messages if messages is not None else parse_transcript(transcript_path)
            cached = load_prompt(session_id)
            decision = _full_decide(
                _messages_for_decision(transcript, cached),
                tool_name,
                tool_input,
                cached_prompt=cached,
            )
            verdict = _verdict(decision)
        else:
            verdict = Decision(
                allow=True,
                reason="",
                engine=ENGINE_POLICY,
                model="jevqueue-policy",
                action="policy",
                detail={"note": "the decision layer is not installed; the fallback policy ran"},
            )
    except Exception as error:  # noqa: BLE001 - a governance layer must never brick the agent
        verdict = Decision(
            allow=True,
            reason="",
            engine="error",
            model="",
            detail={"error": f"{type(error).__name__}: {error}"},
        )

    if mode() == "advisory" and not verdict.allow:
        # The user asked to be told, not to be stopped. The verdict is still computed and
        # still reported -- it just does not block. This applies to the floor too: an
        # explicit setting about the user's own machine is not something the plugin
        # overrules silently.
        verdict = Decision(
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
    return Decision(**{**verdict.__dict__, "latency_ms": elapsed})
