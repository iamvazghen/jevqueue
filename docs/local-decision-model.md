# The offline decision model

`jevqueue` normally asks System One what to do next. It can also answer that question
itself, with rules, offline, with no credential and no network:

```python
from jevqueue import Governor, LocalDecisionModel

governor = Governor(LocalDecisionModel())
```

That is not a demo of the hosted service. It is a different thing, and it is worth being
precise about what that thing is, because the distinction decides what it is good for.

## What it is

The hand-written-rules option described in [comparison.md](comparison.md): tokenise the user's
current request, tokenise each tool's name and description, and route to the tool whose text
overlaps the request most — but only when the match is decisive on two counts.

| Question | How the rules answer it |
|---|---|
| `action` | Lexical overlap between the request and each tool. A match that clears the threshold *and* leaves the runner-up behind gets routed; a tie or a thin match gets delegated. |
| `goal_met` | The structure of the transcript, not its content: an outstanding tool call means the work is not done; a completed assistant answer with nothing outstanding means the turn is over; a tool result with nothing after it means the rules cannot tell, and they say so. |
| `risk` | Keyword patterns over the selected tool's name and description. |

It implements the same [DecisionModel](https://github.com/iamvazghen/jevqueue/blob/main/src/jevqueue/client.py)
contract as `JevClient`, so it drops into a `Governor` wherever the hosted client does. The
parser, the guards, the gates, the event log — all of it is identical either way. **That is the
point of it.** The part of this package that is actually unusual is not the model; it is that a
decision is *constrained and then verified*. None of that needs a model to exist.

## What it is not

**It is not a judgment model, and its confidence is not calibrated.** The `confidence` it
reports is *rule-match strength*: how decisively the lexical rules separated one option from
the others. That is a different quantity from the probability that the choice is correct, and
the package says so wherever the two are easy to confuse. A confident wrong answer is entirely
possible here — only more likely than with the hosted model, because a keyword matcher is a
cruder instrument than a calibrated one.

**It cannot judge the world.** It does not know whether the work is done, whether the user
meant something else, or whether a step is really safe. Where it has no evidence it says so,
the way the question set itself instructs: delegate rather than guess.

**It will never ask a clarifying question.** Deciding that only the user can supply the missing
piece is a judgment about what the user knows, and this model has no standing to make it.

**Its risk triage is a keyword heuristic**, and it is the crudest part of the module. It will
call a tool described as "run the deployment" high risk, and it will call `remove_from_cache`
high risk when the operation is routine. It exists so the risk gate can be exercised, not
because keyword matching is a risk model. Replace it:

```python
import re
from jevqueue import LocalDecisionModel

model = LocalDecisionModel(
    high_risk_pattern=re.compile(r"\b(migrate|rollback|drop_table)\b", re.I),
)
```

## Why it exists

Three reasons, in order of how often they matter.

**1. The package is runnable before anyone has an account.** To use the hosted service you
need a TypeSafe API key. Without one, a visitor could read the README and imagine what it
does. With `LocalDecisionModel`, they can execute a governed loop, watch the provider get
constrained to one tool, and watch the provider-ignore case raise — before deciding whether
this is worth a credential.

**2. The enforcement machinery can be tested without a service behind it.** The constraint, the
verification, the refusal to execute an unselected tool: none of that is the model's job. A
test suite that exercises it against a hosted service is a test suite that needs a credential,
and a test suite that needs a credential is a test suite that does not run for contributors.

**3. There is a baseline to measure the hosted model against.** [limits.md](limits.md) says the
honest thing to do is measure on your own traffic. A measurement is only a *comparison* if
there is something to compare against, and the rules baseline is the cheapest possible thing
to compare against. `Governor.events` records `decision_ms`, the resolved model id, and token
usage for every step, so the two can be run side by side on the same traffic.

## What it is not for

Do not ship it as the decision model behind a production agent. The hosted model exists because
the routing question — *which of these eight tools, with what confidence, is the work actually
done, and how risky is the next step* — is a judgment question, and a keyword matcher does not
answer judgment questions. The offline model answers the routing question well enough to be
useful and badly enough to be a liability if you trust it.

Use it for: evaluating the package, writing and testing adapters, demonstrating the gates,
and establishing a baseline to measure against.

## The paths it can reach

| Path | Reachable offline? | Why |
|---|---|---|
| `tool_arguments` | Yes | The rules route to a tool and the provider is constrained to it. |
| `risk_stop` | Yes | The risk triage is keyword-based, so a destructive tool name trips the gate. |
| `delegated` | Yes | An undecided or unmatched request delegates, which is the designed-for default. |
| `completion_held` | Yes | A `finish` with a tool call still outstanding is refused. |
| `final_response` | Yes | When the agent has already written its answer and nothing is outstanding. |
| `static_tool` | Yes | A pre-approved payload is executed without a generative call. |
| `clarification` | No | Deciding that only the user can supply the missing piece needs judgment. |

`clarification` is the one path the offline model cannot reach, and it is unreachable on
purpose.
