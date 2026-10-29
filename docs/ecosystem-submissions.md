# Ecosystem submissions

Three directories index the Jev ecosystem, and `jevqueue` is in none of them. This file
holds the exact entries, in each directory's own format, ready to paste.

Each directory has its own rules about what a row is allowed to claim, and each has a
different bar for "verified". These entries are written to fit those bars rather than to
flatter the project: the honest row is more likely to be accepted, and a row that has to be
walked back later costs the directory more than a missing one.

| Directory | Stars | Mechanism | Section |
|---|---|---|---|
| [`kydlikebtc/awesome-jev`](https://github.com/kydlikebtc/awesome-jev) | 593 | PR | "By decision pattern" → **Tool selection** |
| [`heyjunpenn/awesome-jev`](https://github.com/heyjunpenn/awesome-jev) | — | GitHub issue | **Frameworks & integrations** |
| [`hellogumbo/awesome-jev`](https://github.com/hellogumbo/awesome-jev) | — | PR or issue | **Integrations** |

---

## 1. `kydlikebtc/awesome-jev` — "Jev Decision Atlas"

Format: `- **[Name: description](url)**<br>` then a description line, then a
`<sub>` tag line carrying the kind, the language and the primitives used.

**Section:** under `### Tool selection`. (A second entry under `### Safety gating` is worth
considering once the risk-gate behaviour has been measured on someone else's traffic.)

```markdown
- **[jevqueue: a decision layer that enforces its own routing](https://github.com/iamvazghen/jevqueue)**<br>
  Splits the agent loop in two: a judgment model picks the tool, the provider is then constrained to exactly that tool and the result is checked against it, and a separate `goal_met` question gates whether the agent may stop at all. A provider that ignores the constraint raises before anything executes.<br>
  <sub>`SDK` · `Py` · `choice` · `noul`</sub>
```

The kind is `SDK` because the row points at a client library you install. The primitives are
`choice` and `noul`: the action and risk questions are closed-set choices, and completion is a
number. There is no `⭐` — that marker is reserved for official documentation.

**Before submitting:** the directory's bar is *"could a reader act on this row with what is
here?"* They can `pip install jevqueue` and run `python -m jevqueue` with no
credential, so the row should say so. If that one-liner is not in the README when the PR is
opened, add it to the description line.

---

## 2. `heyjunpenn/awesome-jev`

This one reviews submissions against an explicit field list, and the verification labels
are separate facts rather than a score. The submission is a GitHub issue using the project
submission template.

```markdown
**Project or repository URL**
https://github.com/iamvazghen/jevqueue

**Your relationship to the project**
Author and maintainer. Not affiliated with TypeSafe AI; the project is independent community
work that calls the hosted Jev API and is not endorsed by TypeSafe.

**What Jev decides**
Three things, in one request per step:
1. `action` — which tool or control option the agent should take next, as a choice over the
   tools actually available in that step plus `finish` / `clarify` / `delegate`.
2. `goal_met` — whether the substantive work is already done, as a probability, asked
   separately from `action` so it cannot see the answer it is judging.
3. `risk` — low / medium / high triage for the selected step, which gates a stop-and-ask
   before the provider is called at all.

**Jev call-site URL, when public**
https://github.com/iamvazghen/jevqueue/blob/main/src/jevqueue/client.py
(`POST https://api.typesafe.ai/v1/systemone`)

**Primitive or primitives used**
Choice (action, risk) · Noul (goal_met)

**Runbook or demo URL**
- Runbook: https://github.com/iamvazghen/jevqueue#install
- Runnable demo, no credential required: `claude plugin install jevqueue --marketplace iamvazghen/jevqueue`, then `python -m jevqueue`
- Examples: https://github.com/iamvazghen/jevqueue/tree/main/examples

**Metric sources and measurement method**
A benchmark harness is published in the repository:
https://github.com/iamvazghen/jevqueue/tree/main/bench

It runs a labelled 14-scenario corpus (tools, transcripts and the expected route written by
hand) and reports routing accuracy, the enforced rate, decision latency percentiles and the
path distribution. A published run of the offline rules baseline is committed at
`bench/results/local-rules-baseline.json`: 70 decisions, 100% routing accuracy, 71.4% enforced
rate, p50 0.395 ms. The corpus is small and the numbers are the author's own; the harness is
published so a reviewer can reproduce or extend it.

**Optional localized summaries**
Not provided.
```

The verification label that fits is **Public source** with **Author-reported metric** for the
numbers, and **Call site verified** is not claimed — the call site is public and inspectable,
but this project is not asking the directory to assert that it has been independently
reproduced. Say which labels you are claiming rather than letting a reviewer guess.

**Section:** "Frameworks & integrations" is the closest fit — it covers a framework or
platform route to the model, and this is a layer that routes into the agent frameworks. If
the maintainer prefers "Agent tooling", the entry works unchanged there.

---

## 3. `hellogumbo/awesome-jev`

Format: `- [Name](url) - Description.` under a section heading. Simple, and the directory
notes it is **not affiliated with TypeSafe AI**, which is worth matching in tone.

**Section:** `## Integrations`.

```markdown
- [jevqueue](https://github.com/iamvazghen/jevqueue) - A decision layer for existing LLM agents: a judgment model picks the tool, the provider is constrained to it and checked, and an independent `goal_met` question gates whether the agent may stop. Adapters for LangChain, Hermes, Pydantic AI and any OpenAI-compatible loop. Not affiliated with TypeSafe AI.
```

The directory's entry format has an optional `([site](url))` after the URL. Once the docs
site is live, add it: `([site](https://iamvazghen.github.io/jevqueue/))`.

---

## Order of work

Submit in this order, because each one makes the next one easier:

1. **hellogumbo** first — the entry is one line, and "not affiliated with TypeSafe AI" in
   the description matches the directory's own framing.
2. **heyjunpenn** second — it needs the benchmark numbers, which now exist.
3. **kydlikebtc** last — it has the strictest bar, and by then the README will have been
   improved by whatever the first two produce.

Do all three from the same account and in one week. A directory that indexes the Jev
ecosystem is checking whether a project is *real and maintained*; three submissions in a week
from one author is evidence of that, and one submission is noise.
