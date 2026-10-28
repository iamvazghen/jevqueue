---
name: jevqueue
description: >-
  Work under a decision queue: check a step before taking it. Use when you are about to run a
  destructive or irreversible command, when you are about to keep going on work that may
  already be finished, when a step touches production, credentials or the filesystem
  destructively, or when the user asks whether a step is safe. Covers the two gates --
  the risk gate and the completion gate -- and how to ask the decision layer instead of
  guessing. Do not use when the task is purely writing, or when the answer is obviously
  yes and obviously harmless.
---

# Working under a decision queue

A decision layer is only worth having if it is consulted *before* the effect, not after. The
queue asks one question about a pending step:

> **Should this step run at all?**

It is not asking which tool to use -- you have already chosen that. It is asking whether this
particular step is the right one to take right now.

## The two gates

**The risk gate.** Some steps are irreversible, unbounded, or outside clear authorization:
deleting things, rewriting production, pushing force, dropping tables, piping a download into
a shell. The decision layer triages each step as `low`, `medium` or `high` with a probability,
and a confidently `high` verdict stops the step and asks a human instead.

**The completion gate.** The most common real failure of an agent loop is an agent reporting
success on work that never happened. It happens because the same model that decides to stop
is the one claiming it finished, and a model is a poor witness to its own reliability. The
decision layer asks the completion question *separately*, so the two judgments cannot see each
other's answers. When they disagree, the stricter one wins and the work continues.

Risk is checked **before** completion. That order is the point: "this might be destructive
and I am not sure" must never be answered with "but the work seems finished anyway".

## What to do when a step is refused

The refusal arrives with a reason. Treat it as information, not as an obstacle:

- **High risk.** Do not retry the same command. Say what you wanted to do and why, and let a
  human decide. If the risk genuinely came from a misread of the request, fix the request
  rather than the command.
- **The work looks done.** Stop. Write the answer. Do not call another tool to look for more
  work — that is exactly the loop the gate is closing.
- **Information is missing.** Ask the user. The question is part of the work, not a detour
  from it.

## Asking the queue directly

The queue is also usable by hand, which is how you check a plan before you commit to it:

```bash
jevqueue decide --tool Bash --input '{"command": "rm -rf build/"}'
```

It prints the verdict, the engine that produced it, the model, the action, the risk and the
completion probability. `--transcript <path>` adds the session's own history to the question,
which is what the hook does.

## What the queue is not

- **It is not a planner.** It decides one step at a time. It does not decompose a goal.
- **It is not an authorization layer.** A `low` risk verdict is not permission to loosen your
  own tool permissions. Your existing authorization must stay correct on its own.
- **It is not always right.** A confident wrong verdict is possible. That is why the gates
  are narrow: they refuse a small number of steps rather than steering every step.
- **It fails open.** If the decision layer is unreachable, the step is allowed. A governance
  layer that bricks the agent on a bad day is worse than no governance layer — but it does
  mean an outage is a loss of checking, not a loss of work.

## Reading the numbers

- `confidence` is distribution concentration, not the probability the step is right.
- `risk` is triage, not permission.
- A completion probability near 0.5 means *about as likely as not*, not *half done*.

Read them as evidence about how sure the decision layer is, and not as permission.
