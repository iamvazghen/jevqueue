# The decision layer

**A calibrated decision layer for agents you already have.**


Two failures in ordinary agent loops have the same root cause: the loop asks one generative
model to do two unrelated jobs on every step — **decide what to do next**, and **write the
thing**. The decision and the writing share one pass, so two things go unchecked.

**The wrong tool runs.** The model selects a tool in the same breath as it writes prose, and
nothing verifies that selection against anything. A constraint written in a prompt is a
suggestion; a constraint in the provider's `tool_choice` is a fact — but only if something
checks that the provider obeyed it.

**The agent reports success on work that never happened.** Stopping is decided in the same
breath as the final answer, so the model is its own witness that it finished.

The first of those two jobs is a classification over a fixed set of options. Autoregressive
generation is a strange and expensive way to pick one of eight strings — you pay for reasoning
tokens, you re-send every tool description so the model can choose between them, and you wait
seconds for an answer that was never prose.

`jevqueue` splits the loop. A decision model decides — Jev, TypeSafe's System One model, or
the offline rules baseline in [`LocalDecisionModel`](#try-it-in-ten-seconds-with-no-key) — and the
generative model is then **constrained to that decision and checked against it**. It installs into
agents you already run — LangChain, Hermes, Pydantic AI, OpenClaw, or any OpenAI-compatible loop
— without changing their tools, memory, sandboxes, or prompts.

```text
             ┌──────────────────────────── one decision, ~70–300 ms ──┐
             │                                                        │
  state ──►  │  action   : choice over YOUR tools + finish/clarify/delegate
             │  goal_met : noul  — is the substantive work already done?
             │  risk     : choice over low/medium/high  (triage, not permission)
             │                                                        │
             └───────────────────────────────┬────────────────────────┘
                                             │
   ┌─────────────────────────────────────────┼─────────────────────────────────────┐
   ▼                     ▼                   ▼                 ▼                   ▼
 static_tool        tool_arguments     final_response      risk_stop           delegated
 pre-approved       model writes ONLY  model writes ONLY   ask a human       unconstrained
 payload, zero      the arguments      the prose           first             generative step
 generative cost    (forced tool)      (tools forbidden)   (no model call)   (as before)
```

---

## What it does

Concretely, on every step of an agent loop, this package does six things.

### 1. It projects the transcript into a bounded, read-only state

The decision layer cannot read the whole transcript — it would be unbounded, and it would be
reading someone else's data. So `state.py` builds a **fresh projection on every step** and
throws it away:

```json
{
  "goal": "the latest user message",
  "instructions": "system messages, concatenated once, in order",
  "recent_history": ["newest turns that fit, oldest-first"],
  "truncated": true
}
```

Two properties matter more than the shape. **The canonical transcript is never touched** — not
truncated, not reordered, not rewritten; a decision layer that edits the transcript to make its
own job cheaper has corrupted the record. And **the bound is enforced on the serialized length**,
not the sum of field lengths, because JSON escaping can multiply a string several times over and
a naive character count silently stops holding.

`truncated` is reported rather than hidden, because the second guard depends on it.

### 2. It asks three typed questions about that state

One request, three answers, each a closed type rather than prose:

| Question | Type | Answers |
|---|---|---|
| `action` | `choice` | which tool to call, or `finish` / `clarify` / `delegate` — over exactly the tools available in this step |
| `goal_met` | `noul` | is the substantive work already done? A probability, asked **separately** from `action` |
| `risk` | `choice` | `low` / `medium` / `high` for the selected step — triage, never permission |

The separation of `action` and `goal_met` is the load-bearing part. They are asked in the same
request but they cannot see each other's answers, so a model that has just chosen `finish`
cannot be its own witness that finishing is justified.

### 3. It runs seven guards, in an order that is load-bearing

`Governor._dispatch` checks, in this order:

1. **Interrupted?** A decision takes a few hundred milliseconds, which is long enough for
   someone to hit Ctrl-C. Checking after the decision and before the effect is the last honest
   moment to notice.
2. **Truncated view and a `finish`?** Delegate. The one judgment that must never be made from a
   partial transcript is *"the work is already done"* — the part that got dropped is exactly
   where unfinished work would be. A tool route from partial evidence is fine; a *stop* from
   partial evidence is how an agent confidently reports success on work it never did.
3. **Confidently high risk?** Stop and ask a human. This sits **before the confidence gate on
   purpose**: otherwise an action judged risky *but with low confidence* would fall through to
   the generative model — i.e. the response to "this might be dangerous and I am not sure" would
   be to hand it to the component with fewer brakes.
4. **Unconfident, or explicitly `delegate`?** Hand it over, unconstrained. **This is the designed
   path, not the failure path.** It is supposed to be common.
5. **`clarify`?** Ask the user. No generative call — spending one to phrase a question is the
   cost this package exists to avoid.
6. **`finish`?** Only if `goal_met` clears its own, higher threshold.
7. **A tool?** Either a pre-approved static payload (schema-validated, and only on a `low` risk
   verdict), or the generative model writes the arguments under a hard constraint.

### 4. It constrains the provider, then verifies what came back

This is the part that makes it a decision *layer* rather than a suggestion:

```python
response = host.generate(force_tool="read_file", directive=...)
called = host.called_tools(response)
if called != ["read_file"]:
    raise JevError("The provider ignored the selected tool; execution blocked")
```

The host sets `tool_choice={"type": "function", "function": {"name": ...}}` with
`parallel_tool_calls=False`, and then the result is **checked**. Providers ignore `tool_choice`
— under load, on older models, through proxies and compatibility shims. Without the check, a
provider that disregarded the constraint would have its own choice executed, and the decision
layer would have been decorative in exactly the cases where it mattered.

The same check runs inverted for `finish`: a tool call after a no-tool decision also raises.

### 5. It distrusts the answer

A typed response is schema-valid, not coherent. Four properties are enforced, and each has a
failure behind it:

| Check | What it catches |
|---|---|
| Not a `bool` | `isinstance(True, int)` is true in Python, so a stray boolean reads as certainty |
| Distribution covers exactly the offered options, sums to 1 | The question and the answer have drifted apart |
| The choice is its own argmax | An internally inconsistent answer where neither half can be believed |
| `confidence = min(stated, mass[winner])` | Confidence summarising concentration more optimistically than the mass supports |

None of this makes a judgment *correct*. It makes an incoherent one **loud**, which is the only
guarantee a client library can honestly offer.

### 6. It records one event per step

Nine paths, and each one is recorded with the probabilities, the resolved model id, the latency
and the token usage behind it:

| Path | What happened |
|---|---|
| `static_tool` | A pre-approved payload ran, with no generative call at all |
| `tool_arguments` | The provider wrote the arguments for the one selected tool, under a hard constraint |
| `final_response` | The decision was that the work is done, so the model wrote prose and was forbidden from calling any tool |
| `clarification` | The user was asked for what was missing — no generative call |
| `risk_stop` | The step looked destructive, so a human was asked first — no model call |
| `delegated` | The decision was handed to the generative model unconstrained: the designed path, not a failure |
| `completion_held` | A `finish` was refused because completion was not certain enough |
| `truncated_hold` | A `finish` was refused because the view of the transcript was partial |
| `error` | The decision model failed, and `on_error` decided what happened next |

---

## The benefits

**Fourteen of them**, and each is a property you can point at in the code or observe in a run.
They are not all equally important — the first three are the reason the package exists, and the
rest are why it is worth the dependency.

### Control

1. **The wrong tool cannot run.** The provider is constrained to the selected function and the
   result is checked against it. A provider that ignores the constraint **raises before
   anything executes**, so the failure is a retryable error rather than a wrong side effect.
2. **Completion gets an independent witness.** `goal_met` is a separate question from `action`,
   so the two cannot see each other's answers. When they disagree, the stricter completion
   judgment wins and the turn keeps working. This is the most common real failure of agent
   loops — confidently reporting success on work that never happened.
3. **A partial view can never produce a "done."** A `finish` decided on a truncated transcript
   is refused, because the dropped history is exactly where unfinished work would be.
4. **Risk is triaged ahead of confidence.** Uncertainty about risk never buys an escalation in
   capability: "this might be dangerous and I am not sure" cannot fall through to the
   generative model.
5. **The escape hatch is designed, not accidental.** `delegated` is a first-class path, and
   `on_error="delegate"` degrades to the old behaviour when the decision service is
   unreachable. The fast path can afford to be strict precisely because falling off it is cheap
   and safe.

### Assurance

6. **The decision is a value you can gate on, not a sentence you have to trust.** It arrives as
   a typed choice over exactly the offered options, with a distribution and a number. You can
   threshold on it, compare it, and branch on it.
7. **Incoherent answers are loud instead of silent.** Four checks, each with a failure behind it.
   A `JevError` has exactly one meaning — *no decision was executed* — so it is always safe to
   retry and is never raised after an effect.
8. **Every step leaves a number behind.** One event with the path, the probabilities, the
   resolved model id and the latency. "Why did it do that" becomes a query instead of a
   transcript re-read, and a behaviour change is attributable to a model version after the fact.
9. **Your transcript and your record stay intact.** The canonical transcript is never edited, and
   exception messages never carry response bodies, transcript content or credentials.

### Cost and reach

10. **The routing decision generates zero tokens.** The decision is a classification over a
    closed set, so it is not something a generative model should be paying reasoning tokens for.
11. **Some steps cost nothing at all.** `static_tools` runs a pre-approved payload with no
    generative call — validated against the tool's live JSON schema, remote `$ref` refused, and
    only on a `low` risk verdict. `clarification` and `risk_stop` also skip the model. This is
    the single biggest win available, and it removes generative calls from the *dangerous* steps
    specifically.
12. **Routing commands cannot be smuggled in through tool output.** Fetched pages and tool
    results are declared to the model as **evidence, never instructions**, because a decision
    layer that reads routing commands out of a scraped page subverts the one component whose
    job is to be unsubvertible.

### Fit

13. **It fits the framework you already run.** The `Host` protocol is seven methods, and any
    framework that can be described that way can be governed. The decision layer and the
    framework version move independently — the Hermes integration is a six-line seam rather than
    a fork.
14. **The decision model is yours to choose.** `Governor` takes a `DecisionModel` protocol, so
    the hosted judgment model, the offline rules baseline, and anything you plug in yourself all
    work the same way — and everything that happens after the answer is identical either way.

---

## Install

```bash
# The package is not on PyPI, so every install names the repository.
pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"                # core: no dependencies
pip install "jevqueue[pydantic-ai] @ git+https://github.com/iamvazghen/jevqueue.git" # the model-wrapper adapter
pip install "jevqueue[langchain] @ git+https://github.com/iamvazghen/jevqueue.git"   # the chat-model wrapper
pip install "jevqueue[static] @ git+https://github.com/iamvazghen/jevqueue.git"      # validated zero-cost static tool payloads
```

You need a TypeSafe API key in `TYPESAFE_API_KEY` to use the hosted decision model. Get one at
[typesafe.ai](https://typesafe.ai). **The package itself does not need one** — see below. The
test suite does not need it either — see [Verification](#verification).

### Try it in ten seconds, with no key

The hosted decision model needs a credential. The package does not have to.

```python
from jevqueue import Governor, LocalDecisionModel

governor = Governor(LocalDecisionModel())
```

`LocalDecisionModel` answers the same three questions with offline rules, so the whole
machinery — the constraint, the verification, the gates — runs with no key and no network. It
is the hand-written-rules baseline rather than a judgment model, and
[docs/local-decision-model.md](docs/local-decision-model.md) is explicit about where it stops
being useful. With a key, the swap is one name:

```python
from jevqueue import Governor, JevClient

governor = Governor(JevClient(key))
```

A runnable version of the whole thing — including a provider that ignores its constraint and
is refused before it executes — is in [`examples/local_first.py`](examples/local_first.py).

Or run it with no code at all:

```bash
pip install "jevqueue @ git+https://github.com/iamvazghen/jevqueue.git"
python -m jevqueue
```

### Works with

| Framework | Integration | Install | Verified against |
|---|---|---|---|
| **Any OpenAI-compatible loop** | `OpenAIChatHost` | core | logic tested; a live provider is yours to run |
| **LangChain** | `GovernedChatModel`, a chat-model wrapper | `jevqueue[langchain]` | tested against a real `BaseChatModel`; not run against a live provider |
| **Hermes Agent** | a six-line seam in `agent/turn_api_call.py` | core | logic tested; not run against a live checkout |
| **Pydantic AI** | `GovernedModel`, a `WrapperModel` | `jevqueue[pydantic-ai]` | logic tested; not run against a live provider |
| **OpenClaw** | `OpenClawRouter` — fleet routing, *not* governed | core | transport properties tested; not run against a live gateway |
| **Your own** | seven methods — see [docs/adapters.md](docs/adapters.md) | core | — |

The last column is the honest one, and it is the row to read before you adopt: the decision
parsing, guards, projection, config and transport are pinned by a hermetic suite, but the
adapters have not been round-tripped against live frameworks in CI. That is exactly the part
a contributor can close, and [CONTRIBUTING.md](CONTRIBUTING.md) says how.

### LangChain — wrap the chat model, change nothing else

```python
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from jevqueue.adapters.langchain import GovernedChatModel

model = GovernedChatModel(init_chat_model("openai:gpt-4o"))
agent = create_agent(model, tools=[check_port, read_log])
```

Your tools, your chain, your `create_agent` call are untouched. LangChain has a real
`tool_choice`, and a **named** one is a provider-level constraint rather than a prompt
instruction — so the forced tool is not advice. To finish, the request is re-issued with no
tools bound at all, leaving prose as the only legal move.

Two honest limits: a provider that cannot constrain is governed less tightly rather than
unsafely (the check catches it), and **streaming is not governed** — this wrapper implements
the non-streaming path.

### Pydantic AI — wrap the model, change nothing else

```python
from pydantic_ai import Agent
from jevqueue.adapters.pydantic_ai import GovernedModel

agent = Agent(GovernedModel("openai:gpt-4o"), tools=[check_port, read_log])
print(agent.run_sync("Is port 8080 listening? If not, check uptime.").output)
```

Your tools, prompts, and run calls are untouched. Pydantic AI has no `tool_choice`, so the
constraint is applied by re-issuing the request with `function_tools` filtered to the chosen
tool and `allow_text_output=False` — one legal move, using only documented fields.

### Hermes Agent — one seam, six lines

Hermes funnels every provider call through `agent/turn_api_call.py`, so the install is a seam
rather than a rewrite. Full copy-paste in **[docs/install-hermes.md](docs/install-hermes.md)**;
the shape is:

```python
# agent/turn_api_call.py
def _perform_api_call(next_api_kwargs):
    governor = getattr(agent, "_jevqueue", None)
    if governor is not None:
        return governor.call(agent, next_api_kwargs, _generate_api_call)
    return _generate_api_call(next_api_kwargs)
```

Enable per profile, so switching it off is one line and not an uninstall:

```yaml
jev:
  enabled: true
  confidence_threshold: 0.8
  on_error: delegate
```

Tools, sandboxes, session persistence, memory, skills, and compression stay upstream code.

### OpenClaw — route the fleet

OpenClaw runs its own loop in Node, so there is no Python seam inside it. **This adapter does
not claim one.** What it governs is the decision OpenClaw genuinely leaves open — *which agent
gets this, and should a human see it first*:

```python
from jevqueue import JevClient
from jevqueue.adapters.openclaw import AgentSpec, OpenClawRouter

router = OpenClawRouter(JevClient(key), [
    AgentSpec("finance",  "Invoices, bookkeeping, tax deadlines, portfolio questions."),
    AgentSpec("personal", "Household bills, appointments, personal errands and admin."),
    AgentSpec("security", "Breach alerts, credential hygiene, suspicious access."),
])

route = router.route(inbound_message)
print(router.dispatch(route, inbound_message) if route.routable else f"Hold: {route.reason}")
```

Four transport properties, each a deliberate refusal: commands are built as **`argv`, never a
shell string**; the message crosses in a **file** so nothing re-parses `&` or a quote;
**`--deliver` is never passed**, so a turn produces a reply and *sends nothing*; and the child
environment is an **allowlist built from nothing**.

### Anything OpenAI-compatible

```python
from jevqueue import Governor, JevClient
from jevqueue.adapters.openai_chat import OpenAIChatHost

governor = Governor(JevClient(key))
response = governor.step(OpenAIChatHost(request, lambda r: client.chat.completions.create(**r)))
```

---

## Measured, not claimed

The package tells you to measure on your own traffic rather than trusting anyone's marketing —
including this README's. So the benchmark is a **harness you can run**, not a number you have
to believe, and a published run is committed:

```bash
uv run python bench/run_bench.py --model local
TYPESAFE_API_KEY=... uv run python bench/run_bench.py --model hosted --json results.json
```

A published run of the offline rules baseline over the labelled corpus in `bench/`:

```text
decisions             70
routing accuracy      100.0%  (70/70)
enforced rate          71.4%  (50/70)
decision_ms p50/p95    0.395 / 0.496
input tokens/decision 215.1
path distribution     tool_arguments 35, delegated 20, risk_stop 10, final_response 5
```

Two things in that are worth reading twice. **The rules picked the right tool every time and
acted on only 71% of them** — the gap is the honest part, because a correct decision that is
not enforced is worth much less than a correct decision that is. **The two `risk_stop` cases
are the point of the whole exercise**: `delete_file` and `deploy_service` were both triaged as
high risk and stopped before the provider was called at all.

The corpus is fourteen labelled scenarios, so read it as *"this baseline, on these cases"* and
not as a claim about the world. The harness is the durable artifact; run it on your own
transcripts and compare two decision models on identical inputs.

---

## When not to use it

Stated here rather than left in `docs/limits.md`, because the failure mode of a decision layer
is to be adopted by someone who does not need one.

- **You have one tool.** There is nothing to choose between.
- **Your agent already runs a cheap local model.** The routing decision is nearly free
  already, and this adds a network hop to save less than it costs.
- **You want the model to plan.** This decides *one step at a time*. It does not decompose a
  goal and it does not sequence steps.
- **You cannot tolerate a network dependency in the control flow.** Use
  [`LocalDecisionModel`](#try-it-in-ten-seconds-with-no-key).
- **Your step count is very high and your decision is easy.** Per-call cost is a line item
  then, not a rounding error.

What it does need: a provider that can be constrained to a named tool, and somewhere to record
what happened. Both are ordinary.

---

## What it costs, and what it saves

Honest accounting, because the interesting number is not the one in the benchmark table.

| | Standard loop | With `jevqueue` |
|---|---|---|
| Routing decision | Full generative pass; tokens spent to emit an enum | One decision call, no tokens generated |
| Tool descriptions | Re-sent every step so the model can choose | Not sent for the decision; the criteria are scored instead |
| Deciding to stop | Same pass that chose to stop | Separate, independently gated judgment |
| Risk triage | Prompt instructions, if any | A typed answer with a calibrated probability |
| Provider ignoring tool choice | Executes whatever it called | Raises; nothing executes |
| Routine fixed calls | Always a generative call | `static_tools`: schema-validated, zero generative cost |
| Why did it do that | Read the transcript | One event: path, probabilities, resolved model |

One caveat on the second row, because that row is the one that gets quoted. Deferring tool
schemas until they are needed is no longer a differentiator on its own: Anthropic's Tool Search
Tool is generally available and on by default in Claude Code, and Spring AI ports the pattern
to other providers. Saving the tool descriptions is table stakes now. What is left in the rows
below it is not: the decision is *verified* rather than suggested, and completion is judged by
a separate question that cannot see the answer it is judging. Neither is available from a
schema filter.

**Jev costs real money per call, and the governor adds one call per step.** It pays for itself
when the generative model you are routing with is expensive and the routing decision is easy —
which is the common case, and is why `delegated` is a *designed* path rather than a failure.
It does not pay for itself if your agent is already running a cheap local model, and
`docs/limits.md` says so plainly.

Numbers from the vendor (~70–300 ms, `$0.042`/M input tokens) are **not reproduced here as
findings.** Measure on your own traffic: `Governor.events` records `decision_ms`, the resolved
model id, and token usage for exactly this purpose.

---

## Configuration

```python
from jevqueue import Governor, GovernorConfig, JevClient

governor = Governor(JevClient(key), GovernorConfig(
    confidence_threshold=0.80,   # below this, delegate instead of routing
    completion_threshold=0.95,   # below this, refuse to stop
    state_chars=24_000,          # bound on the per-step state projection
    timeout=5.0,
    on_error="delegate",         # or "stop"
    goal_hint="You operate a home lab and a small business.",
    static_tools={"docker_ps": {}},   # zero-cost pre-approved payloads
))
```

The two thresholds are deliberately not one knob. The failure modes are not symmetric: a
needless delegation costs a few cents, while a turn that stops early hands the user a confident
answer about work that never happened. Unknown config keys are an **error**, not a warning — a
typo in `confidence_threshold` that is silently ignored leaves the gate at its default while you
believe it was tightened.

---

## Verification

```bash
uv run pytest                    # hermetic: no network, no API key, no provider
uv run python scripts/verify_live.py   # opt-in, needs TYPESAFE_API_KEY, costs a few cents
```

The suite is offline by design. A test suite that needs a paid credential does not run in CI,
and one that does not run in CI is decoration. Live verification is a separate script you run
deliberately.

The offline rules baseline is what makes that possible without giving anything up:
`LocalDecisionModel` is a real decision model as far as the governor is concerned, so the
constraint, the verification and every gate are exercised against it with no service behind
them.

---

## Documentation

| | |
|---|---|
| [docs/architecture.md](docs/architecture.md) | The two-tier split, the guard order, and why each guard sits where it does |
| [docs/adapters.md](docs/adapters.md) | Writing a `Host` for a framework not listed here |
| [docs/install-hermes.md](docs/install-hermes.md) | Copy-paste Hermes integration and how to keep merging upstream |
| [docs/limits.md](docs/limits.md) | What this cannot do, and when not to use it |
| [docs/comparison.md](docs/comparison.md) | Against a standard loop, and against other routing approaches |
| [docs/local-decision-model.md](docs/local-decision-model.md) | The offline rules baseline: what it is, what it is not, and how to use it |
| [docs/roadmap.md](docs/roadmap.md) | Possible improvements, with the reasoning for each |

Three runnable examples: [`examples/local_first.py`](examples/local_first.py) governs a step
with **no key and no network**; [`examples/openai_loop.py`](examples/openai_loop.py) is a
complete governed agent loop in about fifty lines; and
[`examples/fleet_router.py`](examples/fleet_router.py) routes across a real 18-agent roster
covering 83 utilities — adjacent remits included, which is where a router either earns its keep
or quietly guesses.

There is also a **docs site**: <https://iamvazghen.github.io/jevqueue/>.

---

## Security

Credentials are read from the environment or the host framework's own secret scope, never from
this package's configuration — a credential should have exactly one home. Exception messages
carry status codes but never response bodies, transcript content, or keys. Tool output and
fetched pages are declared to the model as **evidence, never instructions**, because a decision
layer that reads routing commands out of a scraped page subverts the one component whose job is
to be unsubvertible.

Report vulnerabilities per [SECURITY.md](SECURITY.md). Please do not open a public issue for
one.

---

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the dev loop and the review bar. The short version:
a new guard needs a test that fails without it, and docstrings explain **why** a check exists,
not what the line below does.

If you are adding an adapter for a framework that is not listed above, there is a skill that
lays out the protocol, the four mandatory tests and the two reference implementations:
[`skills/jev-decision-layer-adapter`](skills/jev-decision-layer-adapter/SKILL.md).

## License

[MIT](LICENSE). See [NOTICE](NOTICE) for attribution.

`jevqueue` is an independent community project. It is not affiliated with, endorsed by, or
supported by TypeSafe AI or Nous Research. **Jev** and **TypeSafe** are names of a separately
hosted service; this repository distributes no model weights, API keys, or usage credits, and
use of the service is subject to [TypeSafe's terms](https://docs.typesafe.ai/legal).
