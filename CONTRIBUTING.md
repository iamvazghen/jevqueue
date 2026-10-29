# Contributing

Thanks for looking. This is a small, deliberately narrow package; the fastest way to get a
change merged is to show the failure it fixes.

## Setup

```bash
git clone https://github.com/iamvazghen/jevqueue
cd jevqueue
uv venv && uv pip install -e ".[dev]"
```

## The loop

```bash
uv run pytest             # 264 hermetic tests, ~8s, no network and no API key
uv run ruff check src tests
uv run mypy
```

All three must be green. CI runs them on Python 3.10–3.13.

The benchmark has its own entry point, and it is part of the loop when you touch the decision
path:

```bash
uv run python bench/run_bench.py --model local
```

It runs a labelled corpus and prints the routing accuracy, the enforced rate and the latency
spread. If your change moves those numbers, the PR should say so — a guard that improves one
number by degrading another is a trade, and trades should be visible.

## The one rule about tests

**The suite never needs an API key and never touches the network.** A suite that needs a paid
credential does not run in CI, and a suite that does not run in CI is decoration. Use the fakes
in `tests/conftest.py`: a transport that returns canned bodies, and a host that records what it
was asked to do.

Live verification is `scripts/verify_live.py`, run deliberately, never in CI.

## The review bar

**A new guard needs a test that fails without it.** Delete your guard, watch the test go red,
put it back. If nothing goes red, the guard is not doing what you think.

**Comments say *why*, not *what*.** The line below already says what. What a reader cannot
recover is the failure that put it there:

```python
# Good -- names the failure
# isinstance(True, int) is True in Python, so without this a stray boolean reads as certainty.
if isinstance(value, bool):

# Bad -- restates the code
# Check if value is a bool.
if isinstance(value, bool):
```

Most of the comments in this repo describe something that actually went wrong once. That is the
density to aim for: not every line, but every non-obvious decision.

**Tests are named after the property, not the function.**
`test_a_finish_on_a_partial_view_is_refused` over `test_dispatch_truncated`. The test name is
the specification; someone reading the failure output should learn what broke.

**No new runtime dependencies.** `httpx` is the only one, and that is a feature — this installs
into other people's agents. Optional extras are fine when they are genuinely optional, and the
code must refuse clearly when one is absent (see `static.py`).

## Changing the guard order

`Governor._dispatch` is the heart of the package. The order of its checks is load-bearing and
[docs/architecture.md](docs/architecture.md#why-the-guards-are-in-that-order) explains each
position.

If you reorder them, the PR needs to say which failure the new order prevents **and** which one
the old order prevented that the new one still does. The risk-stop-before-confidence ordering in
particular exists so that uncertainty about risk never buys an escalation in capability; that
one is not up for a tidy-up.

## Adding an adapter

Read [docs/adapters.md](docs/adapters.md) first. The requirement is that `generate` can
*genuinely force* a tool choice and `called_tools` can report what happened. An adapter that can
only suggest must say so prominently in its docstring — it reads as a guarantee while providing
none, which is worse than no adapter.

Include the four tests listed in that document. The one people skip is "a provider that ignores
the constraint raises", and it is the one that proves the adapter works.

There is a skill for this in [skills/jev-decision-layer-adapter](skills/jev-decision-layer-adapter/SKILL.md),
if you would rather have the protocol, the four tests and the two reference implementations
laid out for an agent to follow than read them out of the docs. It is the same content, and
it is what this repository publishes to skills.sh and ClawHub.

## Documentation

Docs are part of the change, not a follow-up. If you add a config field, it belongs in the
README table and in the relevant doc. If you add a limitation, it belongs in
[docs/limits.md](docs/limits.md) — that file is an asset, and padding it with honest entries
makes the package more trustworthy, not less.

## Things that will be declined

These are in [docs/roadmap.md](docs/roadmap.md#probably-not) with reasoning, but briefly:
making Jev write tool arguments (it cannot — it generates no tokens), growing this into a full
agent framework, bundling a provider SDK, and treating `risk` as authorization.

## Reporting a bug

Describe the **turn**, not the feature: what the agent was asked, which path it took
(`governor.last.path`), the probabilities, and what you expected instead. Several of the guards
in this package exist because someone described a bad turn precisely enough that the missing
check was obvious.

Security issues go through [SECURITY.md](SECURITY.md), not a public issue.

## Licence

Contributions are accepted under the [MIT Licence](LICENSE). By opening a PR you confirm you
have the right to contribute the code under it.
