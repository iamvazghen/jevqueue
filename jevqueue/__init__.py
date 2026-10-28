"""jevqueue -- the decision queue in front of an agent's tools.

A pre-tool hook for CLI agents. Before a tool runs, a decision model is asked whether it
should, and the call is refused when the answer is no.

The public surface is :func:`jevqueue.core.decide`. Everything else here is convenience.
"""

from __future__ import annotations

from .core import (
    ENGINE_FULL,
    ENGINE_POLICY,
    Decision,
    api_key,
    confidence_floor,
    decide,
    describe_tool_call,
    engine_name,
    mode,
    option,
    parse_transcript,
)

__version__ = "0.1.0"

__all__ = [
    "ENGINE_FULL",
    "ENGINE_POLICY",
    "Decision",
    "__version__",
    "api_key",
    "confidence_floor",
    "decide",
    "describe_tool_call",
    "engine_name",
    "mode",
    "option",
    "parse_transcript",
]
