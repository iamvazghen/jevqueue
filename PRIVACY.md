# What this plugin runs, sends and fetches

Short version: it runs two Python scripts on your machine, reads your session transcript, and
sends one bounded summary of it to a decision model **only if you have configured an API
key**. It fetches nothing. It writes one small cached file.

Everything below is the detail.

## What it runs

Two scripts, both standard-library Python, both shipped in this repository:

| Script | When | What it does |
|---|---|---|
| `hooks/jevqueue_prompt.py` | when you submit a prompt | writes your current request to a cache file under the plugin's data directory |
| `hooks/jevqueue_gate.py` | before every tool call | reads that cache and the session transcript, asks the decision model, and either allows the call or refuses it |

The decision model is the `jev-governor` package, installed into the plugin's own environment
by `/jevqueue:setup`. Without it, the plugin falls back to a small built-in policy that knows
about a short list of catastrophic operations and nothing else.

The plugin never modifies your shell, your Python, your project files, or your `PATH`.

## What it reads

- **Your session transcript**, from the path the agent runtime provides. Read-only, and only
  the messages needed to build the decision.
- **Your current request**, from a small cache file the prompt hook writes.
- **Your tool input**, which is the thing being judged.

It does not read your files, your shell history, your environment, or your credentials — with
one exception, below, which is deliberate and optional.

## What it sends, and when

**If you have configured a TypeSafe API key**, the plugin sends the decision model:

- a bounded projection of the conversation — the latest user request, the system
  instructions, and the most recent turns that fit in a size limit;
- the tool that is about to be called and its input;
- the three questions the decision layer asks.

That request goes to `https://api.typesafe.ai/v1/systemone`. This is the **only** network
request the plugin ever makes. The transcript is sent in full within the bound — it is not
summarised locally first.

**If you have not configured a key**, the plugin makes **no network request at all**. The
offline rules baseline decides locally.

**The key itself** is read from one place only: the `typesafe_api_key` setting in the
plugin's own configuration (`/config` in Claude Code). The plugin deliberately does **not**
read a credential from your environment — not `TYPESAFE_API_KEY`, not anything else. A plugin
that quietly picks up a secret already sitting in your shell and ships it somewhere is doing
something you did not agree to, and it makes the data handling impossible to reason about.

## What it fetches

Nothing. There is no download step, no asset fetch, no update check, no telemetry, no
analytics and no phone-home. The plugin is a directory of scripts; installing it copies files
and runs two of them.

## What it writes

- **A cached copy of your current request**, under the plugin's data directory
  (`${CLAUDE_PLUGIN_DATA}/state/`). It expires after six hours and is overwritten by the next
  prompt.
- **The plugin's own environment**, under `${CLAUDE_PLUGIN_DATA}/venv`, when you run
  `/jevqueue:setup`.

Both live inside the plugin's data directory and are removed when the plugin is uninstalled.
Nothing is written into your project.

## What it never puts in a message

A refusal reason says what was refused and why. It never contains your transcript, your tool
input, your API key or a response body. That is a property the test suite pins, not a promise.

## Reporting a problem

If you find something that contradicts this document, that is a bug worth reporting as a
security issue: <https://github.com/iamvazghen/jevqueue/security/advisories/new>

MIT licensed — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
