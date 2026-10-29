# Eval results

Haiku (`claude-haiku-5-5`), headless, Claude Code 2.1.312, `python3 evals/run_evals.py`. Pass = an entry
with an expected source and kind (positives), no entry (negative), and no denial of the skill or script.

## 2026-10-29: description only vs. SessionStart reminder (decision 25)

| Scenario | Description v1 | Description v2 ("use unprompted") | v2 + SessionStart reminder | Final (heredoc, matcher) |
|---|---|---|---|---|
| stale-instruction | 0/1 | 0/1 | 4/4 | 3/3 |
| user-correction | 0/1 | 0/1 | 4/4 | 3/3 |
| missing-access | 0/1 | 0/1 | 3/4 | 1/3, then 1/3 with "a denied tool call" in the reminder |
| explicit-user | 1/1 | – | 3/3 | 3/3 |
| negative-product-bug | 1/1 | – | 3/3 | 3/3 |

- Without the reminder, Haiku noticed the friction (for example "the CLAUDE.md instruction looks stale")
  but did not record it. The description alone does not trigger, so the reminder ships (decision 25).
- `missing-access` is unstable (4 of 10 runs with the reminder): after a denied tool call, Haiku often reports
  the denial to the user and ends the turn. Judged on real sessions in the two-week review.
- The first runner used `--permission-mode acceptEdits`. In that mode the Skill call for a skill with
  `allowed-tools` is itself denied. The runner now uses the default mode.
- Cost: about $0.008 per run.
