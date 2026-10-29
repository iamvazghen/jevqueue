"""A deterministic, offline decision model: the hand-written-rules baseline, packaged.

**This is not a judgment model, and it does not pretend to be one.** It is the alternative
described in ``docs/comparison.md`` -- "hand-written rules or a classifier you train" -- built
into the package so that three things are possible without an account, a key, or a network:

1. The package is installable and runnable end to end the moment it lands from PyPI. A visitor
   can execute a governed loop, see the constraint applied, and see the provider-ignored case
   raise, before deciding whether this is worth a credential.
2. The enforcement machinery -- the part of this package that is actually unusual -- can be
   demonstrated and tested without a hosted service standing behind it. The constraint, the
   verification, the refusal to execute an unselected tool: none of that needs a model.
3. There is a baseline to measure the hosted model against. ``docs/limits.md`` says the honest
   thing to do is measure on your own traffic, and a baseline is what makes a measurement a
   comparison rather than a number.

What it does *not* do, stated plainly:

* **Its confidence is not calibrated.** It reports *rule-match strength*: how decisively the
  lexical rules picked one option over the others. That is a different quantity from the
  probability that the choice is correct, and this package says so wherever the two are
  confused. A confident wrong answer is entirely possible here, exactly as it is with the
  hosted model -- only here it is more likely, because a keyword matcher is a cruder instrument.
* **It cannot judge the world.** It does not know whether the work is done, whether the user
  meant something else, or whether a step is really safe. Where it has no evidence it says so,
  in the way the question set itself instructs: delegate rather than guess.
* **It will never ask a clarifying question.** Deciding that only the user can supply the
  missing piece is a judgment about what the user knows, and this model has no standing to make
  it.

The routing rule itself is deliberately boring: tokenise the user's current request, tokenise
each tool's name and description, and route to the tool whose text overlaps the request most --
but only when the match is decisive on two counts (clearly over the threshold, and clearly ahead
of the runner-up). A tie, or a thin match, produces ``delegate``. That is the correct default
for the governor, because delegation is cheap and a wrong tool is not.

The risk rule is a keyword heuristic over the selected tool's name and description. It is the
crudest part of this module and it is the part most likely to be wrong in both directions: it
will call a tool described as "run the deployment" high risk, and it will call a tool named
``remove_from_cache`` high risk when the operation is routine. It exists so the risk gate can be
exercised, not because keyword matching is a risk model. Replace it: pass your own patterns, or
use the hosted model, which was built for this question.

One consequence worth stating: with this model, ``clarify`` and ``risk_stop`` are reachable but
``final_response`` requires the structural signal that the agent has already written its answer,
and ``completion_held`` fires when a tool call is still outstanding. The paths that require
genuine knowledge of the world -- is the work done, is this really safe -- stay with the hosted
model, which is where they belong.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .errors import JevError
from .state import text_of

#: The model id recorded on every decision this module produces. It is deliberately not a
#: version of anything: this is not a model, and a resolved model id in the event log is how an
#: operator tells a real judgment from a fallback.
LOCAL_MODEL_ID = "jevqueue-local"

#: Words that carry no routing signal. A small list on purpose: an aggressive stopword list
#: removes words that genuinely appear in tool descriptions ("all", "no", "use").
_STOPWORDS = frozenset(
    {
        "a", "about", "all", "also", "am", "an", "and", "any", "are", "as", "at", "be", "been",
        "but", "by", "can", "do", "does", "doing", "done", "for", "from", "had", "has", "have",
        "how", "i", "if", "in", "into", "is", "it", "its", "me", "my", "of", "on", "one", "only",
        "or", "other", "our", "out", "over", "so", "some", "such", "than", "that", "the",
        "their", "them", "then", "there", "these", "they", "this", "to", "too", "us", "use",
        "used", "using", "very", "was", "we", "were", "what", "when", "where", "which", "who",
        "why", "will", "with", "would", "you", "your",
    }
)

#: Words that make a step look risky. Matched against the tool's name and description.
_HIGH_RISK = re.compile(
    r"\b(delete|deleted|deleting|remove|removed|drop|dropped|truncate|truncated|destroy|"
    r"destroyed|wipe|wiped|erase|erased|purge|purged|revoke|revoked|terminate|terminated|"
    r"kill|killed|shutdown|force[-_ ]?push|deploy|deployment|publish|production|prod|"
    r"migrate|migration|format|formatted|sudo|chmod|overwrite|reset|factory[-_ ]?reset)\b",
    re.IGNORECASE,
)

#: Words that make a step look like it has an outward effect.
_MEDIUM_RISK = re.compile(
    r"\b(write|writes|written|create|creates|created|update|updates|updated|post|posts|posted|"
    r"send|sends|sent|upload|uploads|uploaded|install|installs|patch|patches|edit|edits|"
    r"rename|renames|move|moves|copy|copies|merge|merges|commit|commits|push|pushes|"
    r"schedule|schedules|email|emails|comment|comments|ticket|tickets|run|runs|execute|"
    r"executes|configure|configures|set|sets)\b",
    re.IGNORECASE,
)

#: How confident a *rule* can be about a risk level it matched by keyword. Rule strength, not
#: probability: see the module docstring.
_RISK_CONFIDENCE = {"high": 0.90, "medium": 0.85, "low": 0.90}

#: Confidence reported for a decision the rules reached unambiguously. Above the governor's
#: default threshold of 0.80, so a decisive rule match actually takes the fast path.
_DECISIVE = 0.90

#: Confidence reported when the rules could not separate the options. Below the governor's
#: default threshold, so an undecided rule match delegates instead of guessing.
_UNDECIDED = 0.50


def _words(text: str) -> list[str]:
    """Lower-case word list for a piece of text.

    Underscores and punctuation separate words, and camelCase is split, so ``read_file`` and
    ``readFile`` both yield ``["read", "file"]``.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def _content_words(text: str) -> set[str]:
    """The words in ``text`` that carry routing signal."""
    return {word for word in _words(text) if word not in _STOPWORDS and len(word) > 1}


def _distribution(options: set[str], selected: str, mass_selected: float) -> dict[str, float]:
    """Spread ``mass_selected`` over ``selected`` and share the rest evenly.

    Even shares are the honest shape here: the rules have an opinion about the winner and no
    opinion at all about the rest, so inventing a preference for the runners-up would be a
    claim the rules cannot support.
    """
    others = sorted(options - {selected})
    if not others:
        return {selected: 1.0}
    share = (1.0 - mass_selected) / len(others)
    distribution = {option: share for option in others}
    distribution[selected] = mass_selected
    return distribution


def _choice_answer(options: set[str], selected: str, confidence: float) -> dict:
    """Build a well-formed ``choice`` answer over exactly ``options``."""
    distribution = _distribution(options, selected, confidence)
    return {
        "type": "choice",
        "choice": selected,
        "probabilities": distribution,
        "confidence": distribution[selected],
    }


class LocalDecisionModel:
    """An offline decision model: deterministic rules, no network, no credential.

    Implements :class:`~jevqueue.client.DecisionModel`, so it drops into a
    :class:`~jevqueue.governor.Governor` wherever :class:`~jevqueue.client.JevClient`
    does::

        from jevqueue import Governor, LocalDecisionModel

        governor = Governor(LocalDecisionModel())

    Parameters
    ----------
    match_threshold:
        Minimum lexical score a tool must reach before the rules will route to it. Below it,
        the rules delegate. Raise it to be more conservative, lower it to route more often.
    high_risk_pattern, medium_risk_pattern:
        Patterns matched against the selected tool's name and description. The defaults are
        keyword heuristics and are the crudest thing in this module; replace them with your
        own if your tools have names that mislead.
    model_id:
        The id recorded on every decision this model produces.
    """

    def __init__(
        self,
        *,
        match_threshold: float = 0.20,
        high_risk_pattern: re.Pattern[str] | None = None,
        medium_risk_pattern: re.Pattern[str] | None = None,
        model_id: str = LOCAL_MODEL_ID,
    ) -> None:
        if not 0.0 < match_threshold <= 1.0:
            raise JevError("match_threshold must be greater than zero and at most one")
        if not isinstance(model_id, str) or not model_id:
            raise JevError("model_id must be a non-empty string")
        self.match_threshold = match_threshold
        self.high_risk_pattern = high_risk_pattern or _HIGH_RISK
        self.medium_risk_pattern = medium_risk_pattern or _MEDIUM_RISK
        self.model_id = model_id

    # -- the DecisionModel contract ---------------------------------------------------------

    def evaluate(self, state: Any, questions: dict) -> dict:
        """Answer the three typed questions from ``state`` and ``questions``.

        Returns a response body in the same shape as the hosted service, so the same parser
        and the same guards apply to it. That is deliberate: if the local model were parsed
        more leniently, it would not be exercising the machinery it exists to exercise.
        """
        if not isinstance(state, dict):
            raise JevError("The state passed to a decision model must be an object")
        if not isinstance(questions, dict):
            raise JevError("The questions passed to a decision model must be an object")

        action_question = questions.get("action")
        if not isinstance(action_question, dict):
            raise JevError("The action question is missing")
        criteria = action_question.get("criteria")
        if not isinstance(criteria, dict) or not criteria:
            raise JevError("The action question has no criteria")
        options = set(criteria)

        history = state.get("recent_history")
        rows = history if isinstance(history, list) else []

        action, action_confidence = self._action(state, rows, criteria, options)
        goal = self._goal_met(rows)
        risk, risk_confidence = self._risk(action, criteria)

        return {
            "model": self.model_id,
            "usage": {
                "input_tokens": len(json.dumps(state, ensure_ascii=False)),
                "output_tokens": 0,
            },
            "answers": {
                "action": _choice_answer(options, action, action_confidence),
                "goal_met": {"type": "noul", "noul": goal},
                "risk": _choice_answer(
                    {"low", "medium", "high"}, risk, risk_confidence
                ),
            },
        }

    def close(self) -> None:
        """Present for symmetry with :class:`~jevqueue.client.JevClient`. Does nothing."""

    # -- the rules --------------------------------------------------------------------------

    def _action(
        self,
        state: dict,
        rows: list[dict],
        criteria: dict[str, str],
        options: set[str],
    ) -> tuple[str, float]:
        """Choose the next step, and say how decisively the rules chose it."""
        if self._already_answered(rows):
            # The agent has written its answer and called nothing further, so the loop is
            # finished. This is a structural fact about the transcript, not a judgment about
            # whether the answer was any good.
            return "finish", _DECISIVE

        goal = state.get("goal")
        goal_text = goal if isinstance(goal, str) else ""
        goal_words = _content_words(goal_text)

        best_option: str | None = None
        best_score = 0.0
        runner_up = 0.0

        for option, description in criteria.items():
            if not option.startswith("tool:"):
                continue
            name = option.removeprefix("tool:")
            score = self._score(goal_text, goal_words, name, description)
            if score > best_score:
                runner_up = best_score
                best_score = score
                best_option = option
            elif score > runner_up:
                runner_up = score

        if best_option is None or best_score < self.match_threshold:
            # Nothing matched. The rules are decisive about that much: no tool is a confident
            # no, and delegation is the designed-for answer to thin evidence.
            return "delegate", _DECISIVE

        # Two ways to be undecided: the match barely clears the bar, or a second tool is close
        # behind. Either way the rules have not separated the options, so the confidence says
        # so and the governor delegates.
        headroom = (best_score - self.match_threshold) / max(1e-9, 1.0 - self.match_threshold)
        separation = self._separation(best_score, runner_up)
        margin = min(1.0, max(0.0, min(headroom, separation)))
        confidence = _UNDECIDED + (_DECISIVE - _UNDECIDED) * margin
        return best_option, round(confidence, 4)

    @staticmethod
    def _separation(best: float, runner_up: float) -> float:
        """How decisively the winner beat the runner-up, from 0 (a tie) to 1 (clear).

        The rule is about *relative* closeness, not absolute difference. A tool that shares a
        common noun with the winner -- ``write_file`` against a request to "read the file" --
        is a worse match but not a rival, and it should not cost the routing its confidence.
        What costs it is a runner-up within striking distance of the winner, which is the
        situation where the rules genuinely cannot tell them apart.
        """
        if best <= 0.0:
            return 0.0
        ratio = runner_up / best
        if ratio >= 1.0:
            return 0.0
        # A runner-up at or below 60% of the winner is a clear loser; the gap closes linearly
        # from there to a dead heat.
        return max(0.0, min(1.0, (1.0 - ratio) / 0.4))

    def _score(
        self, goal_text: str, goal_words: set[str], name: str, description: str
    ) -> float:
        """Lexical overlap between the request and one tool, normalised by request length.

        A word in the tool's *name* counts double: names are chosen to be distinctive, while
        descriptions are prose, and a shared adjective in a description is much weaker
        evidence than a shared verb in a name.
        """
        if not goal_words:
            return 0.0
        name_words = set(_words(name))
        description_words = set(_words(description))
        overlap = 2 * len(goal_words & name_words) + len(goal_words & description_words)
        # An explicit mention of the tool is a much stronger signal than a shared adjective.
        spoken = name.replace("_", " ").replace("-", " ").lower()
        if spoken and spoken in goal_text.lower():
            overlap += 3
        return overlap / len(goal_words)

    def _already_answered(self, rows: list[dict]) -> bool:
        """True when the last turn is a completed assistant answer with no tool call."""
        if not rows:
            return False
        last = rows[-1]
        if not isinstance(last, dict) or last.get("role") != "assistant":
            return False
        if last.get("tool_calls"):
            return False
        return bool(text_of(last.get("content")))

    def _goal_met(self, rows: list[dict]) -> float:
        """Judge completion from the *structure* of the history, not its content.

        The three cases are deliberately different, because they are different kinds of
        evidence:

        * A tool call with no result yet means the work is still in flight. Not done.
        * A tool result with nothing after it means the rules cannot tell whether more work is
          needed, so they say so. A ``noul`` near 0.5 means "about as likely as not" -- which
          is exactly why the completion gate exists, and exactly what it is there to refuse.
        * A completed assistant answer with no outstanding call means the turn is over.
        """
        pending = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("tool_calls"):
                pending = True
            elif row.get("role") == "tool":
                pending = False

        if pending:
            return 0.05
        if self._already_answered(rows):
            return 0.99
        if rows and isinstance(rows[-1], dict) and rows[-1].get("role") == "tool":
            return 0.50
        return 0.05

    def _risk(self, action: str, criteria: dict[str, str]) -> tuple[str, float]:
        """Triage the selected step. Keyword heuristics; see the module docstring."""
        if not action.startswith("tool:"):
            # Nothing is executed on a finish or a delegate, so there is nothing to triage.
            return "low", _RISK_CONFIDENCE["low"]

        name = action.removeprefix("tool:")
        description = criteria.get(action, "")
        subject = f"{name} {description}"

        if self.high_risk_pattern.search(subject):
            return "high", _RISK_CONFIDENCE["high"]
        if self.medium_risk_pattern.search(subject):
            return "medium", _RISK_CONFIDENCE["medium"]
        return "low", _RISK_CONFIDENCE["low"]
