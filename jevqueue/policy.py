"""The catastrophic-operation floor.

A short, explicit list of operations that are irreversible, unbounded, or that execute code
the agent did not write. It is deliberately small: this list has no judgement in it, so every
entry has to be one nobody would argue about.

It sits **under** the decision model rather than instead of it. A decision layer that shrugs
at ``rm -rf /`` should not be allowed to overrule a list this short. And when the decision
layer itself cannot be reached -- the hosted model is down, the network is gone -- the floor
is still there, which is exactly when you want it.

It is also consulted by the hook before anything else, so the floor holds whether the full
decision layer is running or not.
"""

from __future__ import annotations

import re

__all__ = ["CATASTROPHIC", "SHELL_TOOLS", "check"]

#: Operations that are irreversible, unbounded, or that execute code the agent did not write.
CATASTROPHIC: tuple[tuple[re.Pattern[str], str], ...] = (
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
    (
        re.compile(r"\bgit\s+push\b[^|]*\s--force\b|\bgit\s+push\b[^|]*\s-f\b"),
        "force push",
    ),
    (re.compile(r"\bDROP\s+(TABLE|DATABASE)\b", re.IGNORECASE), "dropping a table or database"),
    (re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE), "truncating a table"),
    (re.compile(r"\bhistory\s+-c\b"), "clearing shell history"),
)

#: Tools whose whole purpose is to run what the agent says, so the floor has to look inside.
#: The names differ per runtime -- Claude Code calls it `Bash`, Gemini CLI calls it
#: `run_shell_command`, opencode calls it `bash`, Cursor calls it `run_terminal_cmd` -- and a
#: floor that only knew one of them would be a floor that only worked in one agent.
SHELL_TOOLS = frozenset(
    {
        # Claude Code, Codex
        "Bash",
        "PowerShell",
        "Shell",
        "ShellCommand",
        # Gemini CLI
        "run_shell_command",
        "run_shell",
        # opencode
        "bash",
        "zsh",
        "sh",
        # Cursor
        "run_terminal_cmd",
        # Aider, goose, and the usual suspects
        "run_command",
        "execute_command",
        "exec_command",
        "terminal",
        "shell_command",
    }
)


def check(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """The floor. Returns ``(allow, reason)``."""
    if tool_name not in SHELL_TOOLS:
        return True, ""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    command = tool_input.get("command")
    if not isinstance(command, str):
        return True, ""
    for pattern, why in CATASTROPHIC:
        if pattern.search(command):
            return False, f"the catastrophic-operation floor blocks this command: {why}"
    return True, ""
