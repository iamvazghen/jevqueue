"""Run the decision benchmark on your own machine.

.. code-block:: console

    $ python bench/run_bench.py --model local
    $ TYPESAFE_API_KEY=... python bench/run_bench.py --model hosted --json results.json

What it measures, and what it does not.

It measures **the decision**, not the agent: how long a decision took, which path the turn
took, how many tokens the decision itself cost, and how often the route matched the labelled
expected route. Those are the numbers that decide whether a decision layer is worth its
keep, and they are the numbers every vendor publishes *about themselves* rather than *about
your traffic*.

It does **not** measure end-to-end agent quality, latency of the whole loop, or cost. Those
need your provider and your traffic, and a benchmark that pretends otherwise is worse than no
benchmark. Run this on your own logs and compare two decision models on identical inputs; that
comparison is the point.

The corpus is small on purpose -- see ``bench/scenarios.py``. It is a labelled workload for
comparing decision models, not a claim about the world.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _path in (os.path.join(ROOT, "src"), ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bench.scenarios import SCENARIOS, TOOLS  # noqa: E402
from jevqueue import Governor, GovernorConfig, JevClient, LocalDecisionModel  # noqa: E402


class _Host:
    """A minimal host for the benchmark: the tools, the transcript, and a provider that
    always obeys, so the measurement is of the decision and not of a provider's misbehaviour.
    """

    def __init__(self, messages: list[dict]) -> None:
        self._messages = messages
        self._tools = TOOLS

    def tools(self) -> list[dict]:
        return self._tools

    def messages(self) -> list[dict]:
        return self._messages

    def interrupted(self) -> bool:
        return False

    def generate(self, *, force_tool: str | None, directive: str) -> Any:
        return {"kind": "generated", "force_tool": force_tool}

    def called_tools(self, response: Any) -> list[str]:
        forced = response.get("force_tool") if isinstance(response, dict) else None
        return [forced] if forced else []

    def say(self, text: str) -> Any:
        return {"kind": "said", "text": text}

    def say_tool_call(self, name: str, arguments: dict) -> Any:
        return {"kind": "static", "name": name, "arguments": arguments}


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)

    def at(fraction: float) -> float:
        index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
        return ordered[index]

    return {
        "p50": round(at(0.50), 3),
        "p95": round(at(0.95), 3),
        "max": round(ordered[-1], 3),
        "mean": round(statistics.mean(ordered), 3),
    }


def run(model_name: str, repeat: int = 1) -> dict[str, Any]:
    """Run the corpus and return a report."""
    if model_name == "local":
        client: Any = LocalDecisionModel()
    elif model_name == "hosted":
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise SystemExit("The hosted model needs TYPESAFE_API_KEY in the environment.")
        client = JevClient(key, model=GovernorConfig().model, timeout=GovernorConfig().timeout)
    else:
        raise SystemExit(f"Unknown model {model_name!r}. Use 'local' or 'hosted'.")

    governor = Governor(client, GovernorConfig())
    paths: dict[str, int] = {}
    latencies: list[float] = []
    tokens: list[int] = []
    rows: list[dict[str, Any]] = []
    correct = 0
    scored = 0
    enforced = 0

    for _ in range(repeat):
        for scenario in SCENARIOS:
            host = _Host(scenario["messages"])
            started = time.perf_counter()
            governor.step(host)
            elapsed_ms = (time.perf_counter() - started) * 1000

            event = governor.last
            paths[event.path] = paths.get(event.path, 0) + 1
            latencies.append(elapsed_ms)
            tokens.append(int(event.usage.get("input_tokens", 0) or 0))

            expected = scenario["expected"]
            if expected == "finish":
                actual = "finish" if event.action == "finish" else event.action
            elif expected == "delegate":
                actual = "delegate" if event.action == "delegate" else event.action
            else:
                actual = (event.action or "").removeprefix("tool:")

            scored += 1
            if actual == expected:
                correct += 1

            # A correct decision that gets delegated is still correct, but nothing was
            # enforced by it. Those are two different numbers and conflating them would
            # overstate the result.
            if event.path != "delegated":
                enforced += 1

            rows.append(
                {
                    "scenario": scenario["name"],
                    "expected": expected,
                    "actual": actual,
                    "path": event.path,
                    "enforced": event.path != "delegated",
                    "confidence": event.confidence,
                    "risk": event.risk,
                    "decision_ms": round(elapsed_ms, 3),
                }
            )

    return {
        "model": model_name,
        "scenarios": len(SCENARIOS),
        "repeat": repeat,
        "decisions": scored,
        "routing_accuracy": round(correct / scored, 4) if scored else None,
        "correct": correct,
        "enforced_rate": round(enforced / scored, 4) if scored else None,
        "enforced": enforced,
        "path_distribution": dict(sorted(paths.items(), key=lambda kv: -kv[1])),
        "decision_ms": _percentiles(latencies),
        "mean_input_tokens_per_decision": round(statistics.mean(tokens), 1) if tokens else None,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default="local",
        choices=["local", "hosted"],
        help="Which decision model to measure. 'local' needs no credential.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to run the whole corpus. Use it to see the latency spread.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Write the full report to this path as JSON.",
    )
    args = parser.parse_args(argv)

    report = run(args.model, max(1, args.repeat))

    print(f"model               : {report['model']}")
    print(f"decisions           : {report['decisions']}")
    print(
        f"routing accuracy    : {report['routing_accuracy']:.1%} "
        f"({report['correct']}/{report['decisions']})"
    )
    print(
        f"enforced rate       : {report['enforced_rate']:.1%} "
        f"({report['enforced']}/{report['decisions']})"
    )
    print(f"decision_ms p50/p95 : {report['decision_ms']['p50']} / {report['decision_ms']['p95']}")
    print(f"input tokens/decision: {report['mean_input_tokens_per_decision']}")
    print("path distribution   :")
    for path, count in report["path_distribution"].items():
        print(f"    {path:<18} {count}")
    print()
    print("per-scenario:")
    for row in report["rows"]:
        mark = "ok " if row["actual"] == row["expected"] else "MISS"
        acted = "acted" if row["enforced"] else "deleg"
        print(
            f"    {mark} {row['scenario']:<34} expected={row['expected']:<14} "
            f"actual={row['actual']:<14} {row['path']:<16} {acted}"
        )

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(f"\nwrote {args.json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
