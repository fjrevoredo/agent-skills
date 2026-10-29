#!/usr/bin/env python3
"""Run the capture-trigger evals: each scenario headless on one model, one at a time, scored by script.

  run_evals.py [--only ID ...] [--runs N] [--model haiku] [--keep] [--json]

Each run gets a fresh git repo built from the scenario's files and a fresh AGENT_FEEDBACK_DIR, loads
the plugin with --plugin-dir, and is scored on the entries it leaves in inbox/: an entry with an
expected source and kind for positive scenarios, no entry for negative ones, and no permission
denial of the capture script. No model is used for scoring. Costs tokens: one session per run.
Exit codes: 0 all passed, 1 some failed, 64 usage.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
EVALS = Path(__file__).resolve().with_name("evals.json")


def score(expect, entries, denials, error=None):
    """Return {"passed", "reasons"} for one run. A run that errored fails whatever it left behind."""
    reasons = [f"run failed: {error}"] if error else []
    for d in denials:
        tool_input = json.dumps(d.get("tool_input", {}))
        if "capture.py" in tool_input or "agent-feedback:capture" in tool_input:
            reasons.append(f"capture denied: {d.get('tool_name')} {tool_input[:200]}")
    if expect["capture"]:
        if not entries:
            reasons.append("no entry written")
        elif not any(e.get("source") in expect["source"] and e.get("kind") in expect["kind"]
                     for e in entries):
            got = ", ".join(f"{e.get('source')}/{e.get('kind') or '-'}" for e in entries)
            reasons.append(f"no entry with source {expect['source']} and kind {expect['kind']}; got {got}")
    elif entries:
        reasons.append(f"{len(entries)} entry/entries written, expected none")
    return {"passed": not reasons, "reasons": reasons}


def read_entries(state):
    entries = []
    for path in sorted((state / "inbox").glob("*.md")):
        head, _, body = path.read_text().partition("\n---\n")
        meta = {}
        for line in head.splitlines()[1:]:
            key, _, value = line.partition(":")
            meta[key] = json.loads(value) if value.strip() else ""
        meta["text"] = body.strip()
        entries.append(meta)
    return entries


def make_repo(root, files):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"],
                ["-c", "user.name=eval", "-c", "user.email=eval@example.com", "commit", "-qm", "init"]):
        subprocess.run(["git", *cmd], cwd=root, check=True, capture_output=True)


def run_one(scenario, model, workdir):
    repo, state = workdir / "repo", workdir / "state"
    repo.mkdir()
    make_repo(repo, scenario["files"])
    cmd = ["claude", "-p", scenario["prompt"], "--model", model, "--plugin-dir", str(PLUGIN),
           "--output-format", "json", "--max-turns", "15"]  # default permission mode, as in real sessions
    if scenario.get("allowed_tools"):
        cmd += ["--allowedTools", *scenario["allowed_tools"]]
    if scenario.get("disallowed_tools"):
        cmd += ["--disallowedTools", *scenario["disallowed_tools"]]
    env = {**os.environ, "AGENT_FEEDBACK_DIR": str(state)}
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "AI_AGENT"):  # don't inherit the caller's session
        env.pop(var, None)
    r = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=600)
    error = None
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out, error = {}, f"stdout is not JSON: {(r.stdout + r.stderr)[-300:]}"
    if not error and (r.returncode != 0 or out.get("is_error")):
        error = f"exit {r.returncode}, {out.get('subtype')}: {(out.get('result') or r.stderr)[-300:]}"
    entries = read_entries(state) if (state / "inbox").is_dir() else []
    result = score(scenario["expect"], entries, out.get("permission_denials") or [], error)
    return {**result, "entries": entries, "final": (out.get("result") or "")[-400:],
            "cost_usd": out.get("total_cost_usd")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", metavar="ID", help="run only these scenario ids")
    ap.add_argument("--runs", type=int, default=1, help="runs per scenario (default 1)")
    ap.add_argument("--model", help="override the model in evals.json")
    ap.add_argument("--keep", action="store_true", help="keep the temp dirs and print their paths")
    ap.add_argument("--json", action="store_true", help="print full results as JSON")
    args = ap.parse_args()

    spec = json.loads(EVALS.read_text())
    model = args.model or spec["model"]
    scenarios = [s for s in spec["scenarios"] if not args.only or s["id"] in args.only]
    if not scenarios:
        print(f"no scenario matches {args.only}", file=sys.stderr)
        return 64

    results = []
    for s in scenarios:
        for n in range(args.runs):
            workdir = Path(tempfile.mkdtemp(prefix=f"agent-feedback-eval-{s['id']}-"))
            res = {"id": s["id"], "run": n + 1, **run_one(s, model, workdir)}
            results.append(res)
            mark = "PASS" if res["passed"] else "FAIL"
            got = ", ".join(f"{e.get('source')}/{e.get('kind') or '-'}" for e in res["entries"]) or "none"
            print(f"{mark} {s['id']} #{n + 1}  entries: {got}  {'; '.join(res['reasons'])}", file=sys.stderr)
            if args.keep:
                print(f"     kept: {workdir}", file=sys.stderr)
            else:
                shutil.rmtree(workdir, ignore_errors=True)

    passed = sum(r["passed"] for r in results)
    cost = sum(r["cost_usd"] or 0 for r in results)
    print(f"{passed}/{len(results)} passed, ${cost:.3f}", file=sys.stderr)
    if args.json:
        print(json.dumps(results, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
