---
name: session-telemetry
description: |
  Measure what a plan cost from the local Claude Code and OpenCode session transcripts: attended
  time, agent-busy time, human prompts, why the agent stopped, what filled its context, and which
  tasks dominated. Use it to tell whether a plan was slow because the work was hard or because of
  the process, to close a finished plan into the baseline ledger, or to compare plans. Read-only;
  reports aggregates, never transcript text.
  Triggers: how long did this plan take, why was this slow, session telemetry, plan performance,
  time spent, agent busy time, stop reasons, context intake, baseline, compare plans.
metadata:
  version: "1.0.0"
---

# Session Telemetry

Reports what a plan cost, from the session transcripts that mention it.

## Script

Standard library Python 3 only.

```bash
python3 scripts/telemetry.py report <plan-file> [--repo DIR] [--key K ...] [--exclude SID ...]
                                                [--no-derive] [--json] [--sessions]
python3 scripts/telemetry.py close <plan-file> [--repo DIR]   # at COMPLETED: store + ledger row
python3 scripts/telemetry.py baseline [--format 2.1] [--json] # medians per Plan Format
python3 scripts/telemetry.py sources [--repo DIR]             # which transcript stores exist
```

Exit codes: 0 ok, 1 no sessions matched (or empty ledger), 64 usage, 66 plan unreadable.

Sessions are selected by repository, then by keys taken from the plan: its name, its decision-ID
prefix, and dated documents linked from its Context section. Add keys with `--key`.

**Check the selection every time** with `--sessions`, and drop false positives with `--exclude`.

Results are stored outside the repository: `--home`, else `$SESSION_TELEMETRY_HOME`, else
`~/.local/share/session-telemetry`.

## Reading a report

- **coverage** — read first. Missing stores or unrecognised records mean the numbers are partial.
- **time** — attended (the person's time) vs agent-busy.
- **autonomous run** — agent-busy minutes between human prompts.
- **stops** — why the human was needed. `Stop:` lines are exact; the rest is a regex guess.
- **per task** — which tasks took the time.
- **findings** — what to change.

Mostly busy time, long runs and one dominant task: the work was hard. Short runs, many stops and
large plan reads at session start: the process was the cost.

## Statistics

- Use medians, not means.
- Do not draw conclusions from fewer than 3 plans; `baseline` says so.
- Compare only plans of similar size and kind.

## Gotchas

- **Transcripts contain secrets.** Never quote transcript text in a report.
- **`rg` skips files listed in `.git/info/exclude`**, which is where untracked plans often live. Use
  `grep -r` to find plans.
- **OpenCode v2 has no per-tool timing**; tool time there is estimated.
- **Subagent sessions are not counted.**
- **A live session keeps changing the numbers.** Run `close` after the last session ends.

## References

- `references/metrics.md` — read when a number or finding needs explaining.
- `references/adapters.md` — read when coverage reports a missing store or unrecognised records.
