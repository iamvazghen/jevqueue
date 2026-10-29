"""The benchmark has to keep running, and its numbers have to stay honest.

A harness that silently stops measuring is worse than no harness, and a published result that
drifts from what the code does is worse than no published result. These tests pin both.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "src"), ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bench import run_bench  # noqa: E402
from bench.scenarios import SCENARIOS  # noqa: E402

RESULTS = os.path.join(ROOT, "bench", "results", "local-rules-baseline.json")


class TestTheHarness:
    def test_it_runs_without_a_credential(self):
        report = run_bench.run("local")

        assert report["decisions"] == len(SCENARIOS)
        assert 0.0 <= report["routing_accuracy"] <= 1.0

    def test_it_reports_enforcement_separately_from_accuracy(self):
        report = run_bench.run("local")

        # The two numbers answer different questions, so they must both be present and
        # they must not be the same measurement.
        assert "routing_accuracy" in report
        assert "enforced_rate" in report
        assert report["enforced_rate"] <= 1.0

    def test_it_records_a_path_for_every_decision(self):
        report = run_bench.run("local")

        assert sum(report["path_distribution"].values()) == report["decisions"]
        assert len(report["rows"]) == report["decisions"]

    def test_it_rejects_an_unknown_model(self):
        with pytest.raises(SystemExit):
            run_bench.run("gpt-9")

    def test_the_hosted_model_refuses_to_run_without_a_key(self, monkeypatch):
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

        with pytest.raises(SystemExit):
            run_bench.run("hosted")


class TestThePublishedResult:
    def test_the_committed_result_exists(self):
        assert os.path.exists(RESULTS)

    def test_the_committed_result_matches_what_the_code_produces_now(self):
        with open(RESULTS, encoding="utf-8") as handle:
            published = json.load(handle)

        current = run_bench.run("local", repeat=published["repeat"])

        # The accuracy and the path mix must not drift from what the code does today.
        assert current["routing_accuracy"] == published["routing_accuracy"]
        assert current["enforced_rate"] == published["enforced_rate"]
        assert current["path_distribution"] == published["path_distribution"]
