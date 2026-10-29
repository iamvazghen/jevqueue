"""What an agent needs to know about jevqueue, in the fewest possible tokens.

This text is injected into a session at start-up, so it is written for an agent that has never
heard of this project and will not read the README. Every word has to earn its place, and the
rule that shaped it is simple: **the agent only needs to know three things** -- that the
queue exists, when to ask it, and what to do when it says no.

The long version, for a human deciding whether to install any of this, is in
``docs/benefits.md``.
"""

from __future__ import annotations

__all__ = ["AWARENESS", "SHORT_AWARENESS"]

SHORT_AWARENESS = """\
## jevqueue

A decision layer sits in front of your tools. Before a risky or irreversible step, it is
asked whether the step should run, and the call is refused when the answer is no.

**Ask it before a destructive step.** Call `jevqueue_decide` with the tool and its input:

    jevqueue_decide(tool="Bash", input={"command": "rm -rf build/"})

It returns the verdict, the action, the confidence, the risk and the completion probability.
The decision is non-autoregressive, so it costs no generated tokens -- the routing decision
is not paid for in reasoning.

**When it refuses, it is a decision, not an error.** Read the reason and act on it:

- "high risk" -- do not run it anyway. Say what you wanted and why, and let a human decide.
- "the work is already done" -- stop calling tools and write the answer. Continuing to hunt
  for more work is the loop this exists to close.
- "information is missing" -- ask the user. That question is part of the work.

**Do not retry a refused call.** A refusal means the step was wrong, not unlucky.

An allowed call is not a guarantee: the gate fails open, so "nothing objected" is what it
means, not "this was safe".
"""

AWARENESS = """\
# jevqueue

A decision layer sits in front of your tools. Before a risky or irreversible step, it is
asked whether the step should run, and the call is refused when the answer is no.

An ordinary agent loop asks one model to do two jobs at once: decide what to do next, and
write the thing. Sharing one pass means two things go unchecked -- the wrong tool runs,
because nothing verifies the choice, and the agent reports success on work that never
happened, because the model that decides to stop is the model claiming it finished.

## Ask it before a destructive step

Call `jevqueue_decide` with the tool and its input:

    jevqueue_decide(tool="Bash", input={"command": "rm -rf build/"})

It returns the verdict, the action, the confidence, the risk triage and the completion
probability. The decision is non-autoregressive: it costs **no generated tokens**, because
routing is a classification, not prose. The state it reads is bounded, so the cost of asking
does not grow with the length of the conversation.

## When it refuses, it is a decision, not an error

Read the reason and act on it:

- **"high risk"** -- do not run it anyway. Say what you wanted to do and why, and let a human
  decide. The refusal exists because the step is irreversible, not because the request was
  unusual.
- **"the work is already done"** -- stop calling tools and write the answer. Continuing to
  look for more work is exactly the loop the completion gate exists to close.
- **"information is missing"** -- ask the user. That question is part of the work, not a
  detour from it.

**Do not retry a refused call.** A refusal means the step was wrong, not unlucky.

## What an allowed call means

Less than it sounds like. The gate fails open: if the decision layer cannot be reached, the
tool runs normally. An allowed call means nothing objected -- not that the step was safe.

## The skills

Two skills ship with the plugin:

- `jevqueue` -- this document. What the queue is and when to ask it.
- `jevqueue-adapter` -- how to govern a framework this plugin does not cover yet: the
  seven-method host protocol, the four mandatory tests, and the two reference
  implementations.

Full documentation: https://github.com/iamvazghen/jevqueue
"""
