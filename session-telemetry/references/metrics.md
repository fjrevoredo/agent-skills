# Metrics

## Definitions

| Metric | Definition |
| --- | --- |
| Attended | Session spans, minus gaps of 60 min or more between prompts |
| Agent-busy | Model steps (capped at 10 min each) plus tool calls (capped at 3 h each), excluding questions to the user |
| Autonomous run | Agent-busy time between two human prompts; median and p90 |
| Resume cost | Minutes and plan KB read before the first code edit or test run, per session |
| Stops | Why the agent handed back: its `Stop:` line if present, else a regex guess |
| Ceremony | Share of busy time spent reading, writing and checking the plan |
| Context intake | KB of tool output per category |
| Per task | Active time attributed to the task most recently set `IN PROGRESS` |
| Outcomes | Reverts in the plan's window, TODO items that mention the plan |

Tool calls longer than 10 minutes that look like plan commands are counted as `long_wait`, not
ceremony (typically a CI wait).

## Findings

| Area | Fires when |
| --- | --- |
| `context` | Median plan read before first productive action > 15 KB |
| `handover` | Context/limit stops plus handover requests reach 30% of sessions |
| `autonomy` | 3+ "continue?" stops, or median autonomous run < 20 min |
| `plan-writes` | Any plan edit made through a shell script |
| `task-size` | One task > 30% of active time, or spans > 3 sessions |
| `stop-line` | A v2.1+ plan with no `Stop:` lines |
| `ceremony` | Ceremony > 30% of busy time |

## Limitations

- The regex stop guess is uncalibrated; its largest class is `other`. Trust `Stop:` lines.
- Parallel tasks share wall time in per-task attribution.
- After changing an adapter or a definition, re-run `report` on an already-closed plan and compare
  with its stored subject file.
