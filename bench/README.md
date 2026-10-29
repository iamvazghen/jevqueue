# The benchmark

Most people publishing numbers about a decision layer publish numbers *about themselves*.
This directory publishes a **harness** instead, so the numbers can be about your traffic.

```bash
python bench/run_bench.py --model local
TYPESAFE_API_KEY=... python bench/run_bench.py --model hosted --json results.json
```

The same corpus, the same tools, the same transcripts — one decision model or the other. That
is the whole point: a measurement only becomes a *comparison* when there is something to
compare against.

## What it measures

| Number | Meaning |
|---|---|
| `routing_accuracy` | How often the decision layer chose the labelled expected route |
| `enforced_rate` | How often the decision was acted on rather than delegated |
| `decision_ms` | p50 / p95 / max wall-clock for one decision |
| `path_distribution` | Which of the nine recorded paths each turn took |
| `mean_input_tokens_per_decision` | What the decision itself cost in tokens |

**Two accuracy numbers, deliberately.** A decision can be *right* and still not be acted on —
that is what `delegated` means: the rules chose a tool but were not decisive enough, so the
turn fell through to the generative model unconstrained. Reporting only `routing_accuracy`
would overstate the result, so the harness reports both.

## What it does not measure

End-to-end agent quality. Total loop latency. Cost. Those need your provider and your
traffic, and a benchmark that pretends otherwise is worse than no benchmark. What this does
give you is a way to put two decision models on identical inputs and see the difference.

The corpus is **fourteen labelled scenarios** and it is small on purpose. It is a workload for
comparing decision models, not a claim about the world, and the numbers below should be read
as "this baseline, on these fourteen cases" rather than "routing accuracy is 100%".

## A published result

`results/local-rules-baseline.json` is a real run of the offline rules baseline on this
corpus, five repetitions, on an ordinary laptop:

```text
decisions            70
routing accuracy     100.0%  (70/70)
enforced rate         71.4%  (50/70)
decision_ms p50/p95   0.395 / 0.496
input tokens/decision 215.1
path distribution     tool_arguments 35, delegated 20, risk_stop 10, final_response 5
```

Two things in that are worth reading twice.

**The rules picked the right tool every time, and only acted on 71% of them.** The gap is
the honest part: the rules are decisive when the request names the tool's own vocabulary
("read the file"), and undecided when it does not ("open the file" shares no word with
"read"). A correct decision that is not enforced is worth much less than a correct decision
that is, and a benchmark that reported only the first number would have hidden that.

**The two `risk_stop` cases are the point of the whole exercise.** `delete_file` and
`deploy_service` were both triaged as high risk and stopped before the provider was called
at all. Nothing was executed, and the user was told why. That is a failure mode the
ungoverned loop does not have.

## Running it on your own traffic

The corpus is a fixture, not the point. The useful run is the one on **your** transcripts:

1. Take a sample of real steps from your agent — the tools available at that step and the
   transcript up to it.
2. Label the route you would have wanted. This is the tedious part and it is the part that
   makes the number mean something.
3. Run both decision models over those steps and compare `routing_accuracy`, `enforced_rate`
   and `decision_ms`.

`Governor.events` already records `path`, `confidence`, `decision_ms` and the resolved model
id for every step of a live agent, so the log you need already exists.
