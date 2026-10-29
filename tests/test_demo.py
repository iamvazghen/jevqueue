"""The demo has to keep working, because it is the first thing a visitor runs.

If the demo needs a key, or reaches the network, or silently stops showing the refusal, it
has stopped being the proof it was written to be. These tests pin the parts that matter.
"""

from __future__ import annotations

import io

import pytest
from jevqueue import demo


class TestTheDemo:
    def test_it_runs_to_completion_and_exits_zero(self):
        stream = io.StringIO()

        assert demo.run_demo(stream) == 0

    def test_it_shows_the_constraint_reaching_the_provider(self):
        stream = io.StringIO()
        demo.run_demo(stream)
        output = stream.getvalue()

        assert "tool_arguments" in output
        assert "read_file" in output

    def test_it_shows_the_ignored_constraint_being_refused(self):
        stream = io.StringIO()
        demo.run_demo(stream)
        output = stream.getvalue()

        assert "JevError" in output
        assert "ignored the selected tool" in output
        assert "nothing" in output

    def test_it_shows_the_risk_gate_firing_before_the_provider(self):
        stream = io.StringIO()
        demo.run_demo(stream)
        output = stream.getvalue()

        assert "risk_stop" in output
        assert "the provider was never called" in output

    def test_it_needs_no_credential_and_no_network(self, monkeypatch):
        # No key in the environment, and any attempt to reach the network is a failure.
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

        def explode(*args, **kwargs):
            raise AssertionError("the demo must not open a socket")

        monkeypatch.setattr("socket.socket.connect", explode)

        stream = io.StringIO()
        assert demo.run_demo(stream) == 0

    def test_the_module_entry_point_is_wired_to_the_demo(self):
        import jevqueue.__main__ as entry

        assert entry.main is demo.main


@pytest.mark.parametrize(
    "heading",
    [
        "The provider is constrained to the tool the decision selected",
        "A provider that ignores the constraint is refused before it runs",
        "A destructive tool stops at the risk gate",
    ],
)
def test_the_demo_shows_every_scenario_it_claims_to_show(heading: str):
    stream = io.StringIO()
    demo.run_demo(stream)
    output = stream.getvalue()

    assert heading in output
    assert output.count("=" * 74) >= 6
