"""jevqueue -- a decision queue in front of an agent's tools.

Two halves in one package, because one install should be enough.

**The decision layer.** A judgment model answers three typed questions about the state --
*action* (which tool, or finish / clarify / delegate), *goal_met* (is the substantive work
already done?), and *risk* (low / medium / high) -- and the generative model is then
constrained to that decision and checked against it. This is the stronger guarantee: the
provider is constrained to a named tool, and a provider that ignores the constraint raises
before anything executes.

**The gate.** A pre-tool hook for CLI agents, which cannot constrain the provider but can
refuse a step the decision layer says should not run, and escalate a risky one. That is the
guardrail guarantee, and it is a different thing.

Both are here, in the same package, with no dependencies to install.

    from jevqueue import Governor, JevClient        # the decision layer
    from jevqueue import Governor, LocalDecisionModel # ...with no credential and no network
    from jevqueue.gate import decide                  # what the hook asks
"""

from __future__ import annotations

from .client import DEFAULT_MODEL, AsyncJevClient, DecisionModel, JevClient
from .config import ON_ERROR_POLICIES, GovernorConfig
from .decision import RISK_LEVELS, Decision, choice, noul, probability
from .errors import JevError
from .gate import (
    ENGINE_FLOOR,
    ENGINE_FULL,
    Verdict,
    api_key,
    confidence_floor,
    decide,
    describe_tool_call,
    engine_name,
    load_prompt,
    mode,
    option,
    parse_transcript,
    save_prompt,
    state_dir,
)
from .governor import MAX_EVENTS, PATHS, Event, Governor
from .host import Host
from .local import LOCAL_MODEL_ID, LocalDecisionModel
from .policy import CATASTROPHIC
from .policy import check as policy_check
from .questions import CONTROL_OPTIONS, MAX_CRITERIA
from .questions import build as build_questions
from .state import project

__version__ = "0.3.0"

__all__ = [
    "CATASTROPHIC",
    "CONTROL_OPTIONS",
    "DEFAULT_MODEL",
    "ENGINE_FLOOR",
    "ENGINE_FULL",
    "LOCAL_MODEL_ID",
    "MAX_CRITERIA",
    "MAX_EVENTS",
    "ON_ERROR_POLICIES",
    "PATHS",
    "RISK_LEVELS",
    "AsyncJevClient",
    "Decision",
    "DecisionModel",
    "Event",
    "Governor",
    "GovernorConfig",
    "Host",
    "JevClient",
    "JevError",
    "LocalDecisionModel",
    "Verdict",
    "__version__",
    "api_key",
    "build_questions",
    "choice",
    "confidence_floor",
    "decide",
    "describe_tool_call",
    "engine_name",
    "load_prompt",
    "mode",
    "noul",
    "option",
    "parse_transcript",
    "policy_check",
    "probability",
    "project",
    "save_prompt",
    "state_dir",
]
