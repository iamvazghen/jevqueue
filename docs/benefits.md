# What this buys the owner of the agent

This page is for the person who owns the agent: the one paying the tokens, answering the
alerts, and signing off on what the thing is allowed to do.

## The problem you actually have

An ordinary agent loop asks one model to do two unrelated jobs on every step: **decide what to
do next**, and **write the thing**. They share a pass, so two things go unchecked.

**The wrong tool runs.** The model selects a tool in the same breath as it writes prose, and
nothing checks the selection. A constraint written in the prompt is a suggestion; a constraint
the provider enforces is a fact — but only if something verifies the provider obeyed it.

**The agent reports success on work that never happened.** Stopping is decided in the same
breath as the final answer, so the model is its own witness that it finished. This is the
most common real failure of agent loops, and it is the one that costs the most: not a crash,
but a confident wrong answer.

Neither is a model problem. Both are control-flow problems, and they are the same problem:
**an agent's control flow is a sentence in a transcript, and you cannot gate on a sentence.**

## What changes

### The decision becomes a value

Three typed questions, one request: *action* (a choice over your tools plus
finish / clarify / delegate), *goal_met* (a probability that the substantive work is
already done), and *risk* (low / medium / high). A typed answer can be thresholded,
compared and refused. A sentence cannot.

### The constraint is verified, not trusted

The provider is constrained to a named tool with `tool_choice`, parallel calls disabled,
and the result is checked against what was asked for. A provider that ignores the constraint
**raises before anything executes**. Without the check, the decision layer would be decorative
in exactly the cases where it mattered — providers do ignore `tool_choice` under load, on
older models, and through proxies.

### Completion stops being self-certified

`goal_met` is asked separately from `action`, so the two judgments cannot see each other's
answers, and the stricter one wins when they disagree. The completion threshold is
deliberately higher than the confidence threshold, because the failure modes are not
symmetric: a needless delegation costs a few cents, while a turn that stops early hands your
users a confident answer about work that never happened.

### Risk is triaged before confidence

The order is load-bearing. If risk were checked after confidence, an action judged risky
*but with low confidence* would fall through to the generative model — which is to say, "this
might be dangerous and I am not sure" would be answered with "here, you decide". Risk first
means uncertainty never buys an escalation in capability.

### Every step leaves a number

One event per step: the path taken, the probabilities, the resolved model id, the latency,
the token usage. "Why did it do that" stops being a transcript re-read and becomes a query.
A behaviour change is attributable to a model version after the fact.

### Your transcript stays intact

The state projection is built fresh per step and thrown away. The canonical transcript is
never truncated, reordered or rewritten. A decision layer that edits the transcript to make
its own job cheaper has corrupted the record your agent and your users depend on.

## What it costs

| | Ordinary loop | With the decision layer |
|---|---|---|
| Routing decision | A full generative pass: schemas sent, reasoning tokens spent, seconds waited | One non-autoregressive call: **0 generated tokens** |
| Tool descriptions | Re-sent every step so the model can choose | Scored as criteria; not sent for the decision |
| Deciding to stop | Same pass that chose to stop | A separate, independently gated judgment |
| Routine fixed calls | Always a generative call | `static_tools`: schema-validated, **0 generative tokens** |
| Risk triage | Prompt instructions, if any | A typed answer with a probability |
| A provider ignoring the constraint | Executes whatever it called | Raises; nothing executes |
| Why did it do that | Read the transcript | One event: path, probabilities, resolved model |

Two honest costs, because they are real:

- **A network hop per step** if you use the hosted model. The offline baseline has none.
- **The decision itself costs input tokens.** Measured on the benchmark corpus: **215 input
  tokens, 0 output tokens** per decision, over a bounded state.

## What it saves on tokens

The saving is on the *routing* half of a turn, not the writing half. Nothing here makes your
model write better prose more cheaply.

Measured on the benchmark's eight-tool corpus:

| | Input tokens | Output tokens |
|---|---|---|
| A generative router, choosing a tool | ~674 (schemas + state) | the reasoning tokens to emit a tool name |
| **The decision layer** | **215** (state only) | **0** |
| A step served from `static_tools` | — | **0** — no model is called at all |

The 460-token difference is the tool schemas: a generative router has to *receive* every tool
definition to choose between them; the decision layer scores criteria against them instead, so
they never enter the context. That gap **scales with the size of your toolset** — at eight
tools it is 460 tokens, at twenty it is over a thousand, and it is paid on every step. The
generated-token difference is larger still: the decision is a classification, so it produces a
label rather than a paragraph of reasoning.

The second saving is bigger and less discussed. A generative router is not only paying for
its own reasoning — it is paying for the *model's* reasoning, which is the expensive part of
the turn, spent on a decision that does not need prose. The decision layer answers the same
question for the price of a single non-autoregressive pass.

Token counts are a four-characters-per-token estimate over the benchmark corpus; the
`output: 0` figure is exact, because it is what the model reports.

## What it does not do

- **It is not a planner.** It decides one step at a time. It does not decompose a goal.
- **It is not an authorization layer.** A `low` risk verdict is not permission to loosen your
  own tool permissions. Your existing authorization must stay correct on its own.
- **It is not always right.** A confident wrong verdict is possible. That is why the gates are
  narrow — a gate that refuses on doubt is a wall — and why it fails open.
- **It does not replace your model.** The model still writes the arguments and the prose.
- **In plugin form it cannot constrain the provider's tool choice.** A hook runs after the
  agent has already chosen. The plugin gives you the *guardrail* guarantee: a step that
  should not run does not run. The *enforcement* guarantee — provider constrained to a named
  tool, result checked — comes from the library, installed in the agent you are building.
  Both are worth having; they are not the same thing, and the README says which one you are
  getting.

## Where to start

If you run an agent unattended, or with tools that can delete things, the completion gate and
the risk gate are the two that pay for themselves. Install the plugin, leave it in `enforce`
mode, and watch what it refuses for a week.

If you are building the agent, install the library instead. The constraint is enforced at the
provider, and the result is checked — which is a stronger guarantee than any hook can give.
