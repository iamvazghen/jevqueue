#!/usr/bin/env node
// jevqueue -- the MCP server, launched.
//
// The decision layer is Python. The agents that speak MCP are Node programs. A plugin
// manifest names exactly one command, and that command has to exist on macOS, Linux and
// Windows alike -- where "python" and "python3" are not the same interpreter, and where
// neither may be on PATH at all. Node is the one interpreter these agents already
// require, so this launcher uses it to find a Python and then hands the process over.
//
// The server speaks JSON-RPC over stdio, so stdio is inherited rather than piped: any
// buffering on the way through would corrupt the protocol.

import { spawn, spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const SERVER = join(ROOT, "mcp", "jevqueue_mcp.py");

// The minimum the package supports.
const MINIMUM = [3, 10];

// The candidates, in the order they are tried. `python3` comes first because on macOS
// and Linux `python` is often a different, older interpreter -- or no interpreter at all.
const CANDIDATES = [
  { command: "python3", args: [] },
  { command: "python", args: [] },
  { command: "py", args: ["-3"] },
];

function versionOf(candidate) {
  // Ask the interpreter itself, rather than parsing `--version`: the Windows Store alias
  // for Python prints a version and still is not an interpreter.
  const probe = spawnSync(
    candidate.command,
    [...candidate.args, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
    { stdio: ["ignore", "pipe", "ignore"], encoding: "utf8" },
  );
  if (probe.error || probe.status !== 0 || !probe.stdout) return null;
  const parts = probe.stdout.trim().split(".").map(Number);
  if (parts.length !== 2 || parts.some((part) => Number.isNaN(part))) return null;
  return parts;
}

function findPython() {
  const configured = process.env.JEVQUEUE_PYTHON;
  if (configured) return { command: configured, args: [] };
  for (const candidate of CANDIDATES) {
    const version = versionOf(candidate);
    if (!version) continue;
    if (version[0] > MINIMUM[0] || (version[0] === MINIMUM[0] && version[1] >= MINIMUM[1])) {
      return candidate;
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  process.stderr.write(
    "jevqueue: no Python 3.10 or later was found on PATH. Install Python, or set " +
      "JEVQUEUE_PYTHON to the interpreter to use.\n",
  );
  process.exit(1);
}

const child = spawn(python.command, [...python.args, SERVER], { stdio: "inherit" });

child.on("error", (error) => {
  process.stderr.write(`jevqueue: could not start the MCP server: ${error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 0);
  }
});
