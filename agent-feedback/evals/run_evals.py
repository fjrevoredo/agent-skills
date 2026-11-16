#!/usr/bin/env python3
"""Run the plugin evals: each scenario headless on one model, one at a time, scored by script.

  run_evals.py [--suite capture|process] [--only ID ...] [--runs N] [--model haiku] [--keep] [--json]

Each run gets a fresh git repo built from the scenario's files and a fresh AGENT_FEEDBACK_DIR (seeded
from the scenario's `state` files), and loads the plugin with --plugin-dir. No model is used for scoring.
- capture (evals.json): an entry with an expected source and kind for positive scenarios, no entry
  for negative ones, no permission denial of the capture script.
- process (process.json): seeded entries in the expected states, duplicates in one table row and
  behind one brief, the repo untouched, no permission denial of the process script.
Costs tokens: one session per run.
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
SUITES = {"capture": "evals.json", "process": "process.json"}
ENTRY_STATES = ("inbox", "proposed", "done", "wontfix")


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


def score_process(expect, snap, final, denials, error=None):
    """Return {"passed", "reasons"} for one process run; snap comes from process_snapshot()."""
    reasons = [f"run failed: {error}"] if error else []
    for d in denials:
        tool_input = json.dumps(d.get("tool_input", {}))
        if "process.py" in tool_input or "agent-feedback:process" in tool_input:
            reasons.append(f"process denied: {d.get('tool_name')} {tool_input[:200]}")
    entries = snap["entries"]
    for entry_id, allowed in expect.get("states", {}).items():
        got = entries.get(entry_id, {}).get("state", "missing")
        if got not in allowed:
            reasons.append(f"{entry_id} is in {got}, expected {'/'.join(allowed)}")
    ids = expect.get("same_row")
    if ids and not any(all(i[-4:] in line for i in ids) for line in final.splitlines()):
        reasons.append(f"{', '.join(ids)} not grouped on one line of the final answer")
    ids = expect.get("same_link")
    if ids:
        links = {entries.get(i, {}).get("link", "") for i in ids}
        link = links.pop() if len(links) == 1 else ""
        if not link:
            reasons.append(f"{', '.join(ids)} don't share one link")
        elif Path(link).name not in snap["briefs"]:
            reasons.append(f"shared link {link} is not a brief in briefs/")
    if expect.get("no_briefs") and snap["briefs"]:
        reasons.append(f"briefs written without approval: {', '.join(snap['briefs'])}")
    if expect.get("repo_unchanged") and snap["repo_changed"]:
        reasons.append("repo files changed")
    return {"passed": not reasons, "reasons": reasons}


def read_meta(path):
    head = path.read_text().partition("\n---\n")[0]
    meta = {}
    for line in head.splitlines()[1:]:
        key, _, value = line.partition(":")
        meta[key] = json.loads(value) if value.strip() else ""
    return meta


def process_snapshot(state, repo):
    entries = {p.stem: {"state": s, "link": read_meta(p).get("link", "")}
               for s in ENTRY_STATES for p in sorted((state / s).glob("*.md"))}
    briefs = sorted(p.name for p in (state / "briefs").glob("*")) if (state / "briefs").is_dir() else []
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True)
    return {"entries": entries, "briefs": briefs, "repo_changed": bool(status.stdout.strip())}


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


def seed_state(state, files):
    for d in (*ENTRY_STATES, "transcripts", "briefs"):
        (state / d).mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        (state / rel).write_text(content)


def run_one(suite, scenario, model, workdir):
    repo, state = workdir / "repo", workdir / "state"
    repo.mkdir()
    make_repo(repo, scenario["files"])
    if scenario.get("state"):
        seed_state(state, scenario["state"])
    cmd = ["claude", "-p", scenario["prompt"], "--model", model, "--plugin-dir", str(PLUGIN),
           "--output-format", "json", "--max-turns", str(scenario.get("max_turns", 15))]  # default permission mode, as in real sessions
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
    denials, final = out.get("permission_denials") or [], out.get("result") or ""
    if suite == "process":
        snap = process_snapshot(state, repo)
        result = score_process(scenario["expect"], snap, final, denials, error)
        found = [f"{i[-4:]}:{e['state']}" for i, e in snap["entries"].items()] + snap["briefs"]
    else:
        entries = read_entries(state) if (state / "inbox").is_dir() else []
        result = score(scenario["expect"], entries, denials, error)
        found = [f"{e.get('source')}/{e.get('kind') or '-'}" for e in entries]
    return {**result, "found": found, "final": final[-1500:], "cost_usd": out.get("total_cost_usd")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", choices=SUITES, default="capture")
    ap.add_argument("--only", nargs="+", metavar="ID", help="run only these scenario ids")
    ap.add_argument("--runs", type=int, default=1, help="runs per scenario (default 1)")
    ap.add_argument("--model", help="override the model in evals.json")
    ap.add_argument("--keep", action="store_true", help="keep the temp dirs and print their paths")
    ap.add_argument("--json", action="store_true", help="print full results as JSON")
    args = ap.parse_args()

    spec = json.loads(Path(__file__).resolve().with_name(SUITES[args.suite]).read_text())
    model = args.model or spec["model"]
    scenarios = [s for s in spec["scenarios"] if not args.only or s["id"] in args.only]
    if not scenarios:
        print(f"no scenario matches {args.only}", file=sys.stderr)
        return 64

    results = []
    for s in scenarios:
        for n in range(args.runs):
            workdir = Path(tempfile.mkdtemp(prefix=f"agent-feedback-eval-{s['id']}-"))
            res = {"id": s["id"], "run": n + 1, **run_one(args.suite, s, model, workdir)}
            results.append(res)
            mark = "PASS" if res["passed"] else "FAIL"
            got = ", ".join(res["found"]) or "none"
            print(f"{mark} {s['id']} #{n + 1}  found: {got}  {'; '.join(res['reasons'])}", file=sys.stderr)
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
