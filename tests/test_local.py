"""The offline rules baseline, and the machinery it has to satisfy.

These tests deliberately use the same parser, the same guards and the same host as the hosted
model. A local model that was parsed more leniently would not exercise the machinery it
exists to exercise, so there is no lenient path here.
"""

from __future__ import annotations

import pytest
from jevqueue import (
    Decision,
    Governor,
    GovernorConfig,
    JevError,
    LocalDecisionModel,
)
from jevqueue.questions import build as build_questions
from jevqueue.state import project

from conftest import FakeHost, _tool

READ = _tool("read_file", "Read a file from disk.")
WRITE = _tool("write_file", "Write a file to disk.")
DELETE = _tool("delete_file", "Delete a file from disk.")

ALL_TOOLS = [READ, WRITE, DELETE]


def ask(model: LocalDecisionModel, goal: str, tools=ALL_TOOLS, history=None) -> dict:
    """Run one question round the way the governor does, and return the raw body."""
    messages = history if history is not None else [
        {"role": "system", "content": "You are a careful assistant."},
        {"role": "user", "content": goal},
    ]
    state = project(messages, 12_000)
    questions = build_questions(tools)
    return model.evaluate(state, questions)


class TestTheContract:
    def test_it_answers_the_three_typed_questions(self):
        body = ask(LocalDecisionModel(), "read the file notes.txt")

        assert body["model"] == "jevqueue-local"
        assert body["usage"]["output_tokens"] == 0
        assert set(body["answers"]) == {"action", "goal_met", "risk"}
        assert body["answers"]["action"]["type"] == "choice"
        assert body["answers"]["goal_met"]["type"] == "noul"
        assert body["answers"]["risk"]["type"] == "choice"

    def test_the_same_parser_that_guards_the_hosted_model_accepts_it(self):
        model = LocalDecisionModel()
        state = project(
            [
                {"role": "system", "content": "You are a careful assistant."},
                {"role": "user", "content": "read the file notes.txt"},
            ],
            12_000,
        )
        questions = build_questions(ALL_TOOLS)
        raw = model.evaluate(state, questions)

        decision = Decision.parse(raw, set(questions["action"]["criteria"]))

        assert decision.model == "jevqueue-local"
        assert decision.action == "tool:read_file"

    def test_the_distribution_covers_exactly_the_offered_options(self):
        body = ask(LocalDecisionModel(), "read the file notes.txt")
        questions = build_questions(ALL_TOOLS)
        options = set(questions["action"]["criteria"])

        distribution = body["answers"]["action"]["probabilities"]

        assert set(distribution) == options
        assert sum(distribution.values()) == pytest.approx(1.0, abs=1e-6)

    def test_it_needs_no_key_and_no_network(self):
        # The whole point: no credential, no transport, no endpoint.
        model = LocalDecisionModel()

        assert model.model_id == "jevqueue-local"
        assert not hasattr(model, "api_key")


class TestTheRouting:
    def test_it_routes_to_the_tool_the_request_names(self):
        body = ask(LocalDecisionModel(), "read the file notes.txt")

        assert body["answers"]["action"]["choice"] == "tool:read_file"

    def test_it_delegates_when_the_request_matches_nothing(self):
        body = ask(LocalDecisionModel(), "what is the airspeed velocity of an unladen swallow")

        assert body["answers"]["action"]["choice"] == "delegate"

    def test_it_delegates_rather_than_guessing_between_two_equally_good_tools(self):
        twin = _tool("read_file", "Read a file from disk.")
        other = _tool("read_file_backup", "Read a file from disk.")
        body = ask(
            LocalDecisionModel(),
            "read the file notes.txt",
            tools=[twin, other],
        )

        # Both score identically, so the rules cannot separate them and must not pretend to.
        assert body["answers"]["action"]["confidence"] < 0.8

    def test_it_never_asks_the_user_a_question_it_cannot_ground(self):
        body = ask(LocalDecisionModel(), "read the file notes.txt")

        assert body["answers"]["action"]["choice"] != "clarify"

    def test_a_thin_match_does_not_become_a_confident_route(self):
        # One shared word out of a four-word request: the match clears the threshold but
        # says almost nothing, so it must not be treated as decisive.
        docs = _tool("search_docs", "Search the documentation for a phrase.")
        body = ask(
            LocalDecisionModel(),
            "find the release notes in the documentation",
            tools=[docs],
        )

        assert body["answers"]["action"]["confidence"] < 0.8


class TestTheRiskTriage:
    def test_a_destructive_tool_is_high_risk(self):
        body = ask(LocalDecisionModel(), "delete the file notes.txt")

        assert body["answers"]["risk"]["choice"] == "high"

    def test_a_read_only_tool_is_low_risk(self):
        body = ask(LocalDecisionModel(), "read the file notes.txt")

        assert body["answers"]["risk"]["choice"] == "low"

    def test_risk_is_tiraged_for_the_tool_that_was_actually_selected(self):
        body = ask(LocalDecisionModel(), "read the file notes.txt")

        # The selected tool is a read, so the destructive sibling must not drag the risk up.
        assert body["answers"]["risk"]["choice"] == "low"


class TestTheCompletionQuestion:
    def test_it_refuses_to_certify_completion_after_a_tool_result(self):
        history = [
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "read the file notes.txt"},
            {"role": "assistant", "content": "", "tool_calls": [{"name": "read_file"}]},
            {"role": "tool", "content": "the notes say hello", "name": "read_file"},
        ]
        body = ask(LocalDecisionModel(), "read the file notes.txt", history=history)

        # A coin flip, and therefore not a claim that the work is done.
        assert body["answers"]["goal_met"]["noul"] == pytest.approx(0.5)

    def test_an_outstanding_tool_call_means_the_work_is_not_done(self):
        history = [
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "read the file notes.txt"},
            {"role": "assistant", "content": "", "tool_calls": [{"name": "read_file"}]},
        ]
        body = ask(LocalDecisionModel(), "read the file notes.txt", history=history)

        assert body["answers"]["goal_met"]["noul"] < 0.5

    def test_a_completed_answer_means_the_turn_is_over(self):
        history = [
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "read the file notes.txt"},
            {"role": "assistant", "content": "The notes say hello."},
        ]
        body = ask(LocalDecisionModel(), "read the file notes.txt", history=history)

        assert body["answers"]["action"]["choice"] == "finish"
        assert body["answers"]["goal_met"]["noul"] > 0.9


class TestItGovernsLikeAnythingElse:
    """The point of the module: the machinery is identical whichever model answers."""

    def test_the_provider_is_still_constrained_to_the_selected_tool(self):
        governor = Governor(LocalDecisionModel())
        host = FakeHost(tools=[READ], messages=[
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "read the file notes.txt"},
        ])

        governor.step(host)

        assert host.generated[0]["force_tool"] == "read_file"
        assert governor.last.path == "tool_arguments"

    def test_the_provider_ignoring_the_selected_tool_still_blocks_execution(self):
        governor = Governor(LocalDecisionModel())
        host = FakeHost(
            tools=[READ],
            messages=[
                {"role": "system", "content": "You are a careful assistant."},
                {"role": "user", "content": "read the file notes.txt"},
            ],
            tool_calls=["delete_file"],
        )

        with pytest.raises(JevError, match="ignored the selected tool"):
            governor.step(host)

    def test_the_risk_gate_still_stops_a_destructive_tool(self):
        governor = Governor(LocalDecisionModel())
        host = FakeHost(tools=[DELETE], messages=[
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "delete the file notes.txt"},
        ])

        governor.step(host)

        # The step is refused, and the user is told why -- no tool was executed.
        assert governor.last.path == "risk_stop"
        assert host.generated == []
        assert host.said

    def test_an_undecided_route_delegates_instead_of_guessing(self):
        governor = Governor(LocalDecisionModel())
        host = FakeHost(tools=[READ], messages=[
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "what is the airspeed velocity of an unladen swallow"},
        ])

        governor.step(host)

        assert governor.last.path == "delegated"

    def test_it_can_be_run_with_a_strict_threshold_and_still_deliver_a_decision(self):
        governor = Governor(LocalDecisionModel(), GovernorConfig(confidence_threshold=0.95))
        host = FakeHost(tools=[READ], messages=[
            {"role": "system", "content": "You are a careful assistant."},
            {"role": "user", "content": "read the file notes.txt"},
        ])

        governor.step(host)

        # The rules were not decisive enough for this threshold, so the step is delegated --
        # but the decision is still recorded, and it says which model produced it.
        assert governor.last.path == "delegated"
        assert governor.last.model == "jevqueue-local"


class TestItsLimits:
    def test_it_rejects_a_threshold_that_could_never_match(self):
        with pytest.raises(JevError):
            LocalDecisionModel(match_threshold=0.0)

    def test_it_rejects_an_empty_model_id(self):
        with pytest.raises(JevError):
            LocalDecisionModel(model_id="")

    def test_it_refuses_to_answer_a_malformed_request(self):
        model = LocalDecisionModel()

        with pytest.raises(JevError):
            model.evaluate("not a state", build_questions(ALL_TOOLS))

        with pytest.raises(JevError):
            model.evaluate({}, {"action": {"criteria": {}}})
