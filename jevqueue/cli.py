"""The jevqueue command line.

Two commands, and that is enough:

``status``
    Which engine is active, how it is configured, where the state lives.

``decide``
    Ask the queue about one pending step and print the verdict as JSON. This is the same
    call the pre-tool hook makes, so what you see here is exactly what the hook sees.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import gate


def _status() -> int:
    engine = gate.engine_name()
    key = gate.api_key()
    print("jevqueue")
    print(f"  version       : {_version()}")
    print(f"  engine        : {engine}")
    print(f"  model         : {'Jev (hosted)' if key else 'offline rules baseline'}")
    print(f"  mode          : {gate.mode()}")
    print(f"  confidence    : {gate.confidence_floor():.2f}")
    print(f"  credential    : {'set' if key else 'not set (offline rules baseline is used)'}")
    print(f"  plugin data   : {os.environ.get('CLAUDE_PLUGIN_DATA') or gate.state_dir()}")
    print(f"  python        : {sys.executable}")
    if not key:
        print()
        print("  The hosted model needs an API key. Set it in the plugin's own settings")
        print("  (/config in Claude Code); it is never read from your environment.")
    return 0


def _version() -> str:
    from . import __version__

    return __version__


def _decide(args: argparse.Namespace) -> int:
    tool_input: dict = {}
    if args.input:
        try:
            parsed = json.loads(args.input)
        except (ValueError, TypeError):
            # A shell command pasted without the JSON wrapper is the common case, and
            # refusing it would make the CLI annoying for no safety gained -- the text
            # still reaches the decision layer, just as a command.
            if args.tool in ("Bash", "PowerShell", "Shell"):
                print(
                    "jevqueue: --input was not JSON; treating it as a shell command",
                    file=sys.stderr,
                )
                parsed = {"command": args.input}
            else:
                print(f"jevqueue: --input is not valid JSON: {args.input!r}", file=sys.stderr)
                return 2
        if not isinstance(parsed, dict):
            print("jevqueue: --input must be a JSON object", file=sys.stderr)
            return 2
        tool_input = parsed

    verdict = gate.decide(
        args.tool,
        tool_input,
        transcript_path=args.transcript,
        session_id=args.session or os.environ.get("CLAUDE_SESSION_ID", ""),
    )
    print(json.dumps(verdict.as_dict(), indent=2, ensure_ascii=False))
    return 0 if verdict.allow else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jevqueue", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show which engine is active and how it is configured")

    check = sub.add_parser("decide", help="ask the queue about one pending step")
    check.add_argument("--tool", required=True, help="the tool about to be called")
    check.add_argument("--input", default="", help="the tool input, as a JSON object")
    check.add_argument("--transcript", default=None, help="a session transcript to include")
    check.add_argument("--session", default=None, help="the session id, for the prompt cache")

    args = parser.parse_args(argv)
    if args.command == "status":
        return _status()
    return _decide(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
