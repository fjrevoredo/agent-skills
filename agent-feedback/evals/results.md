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

## 2026-11-16: `/agent-feedback:process` (`--suite process`)

Haiku, Claude Code 2.1.325. Seeded state dir: two duplicate entries (README names a missing
`scripts/test.sh`), one entry already fixed in the repo (`lint` target), a two-row routing file.

| Scenario | Pass = | Result |
|---|---|---|
| triage-without-approval | nothing moved, no brief, repo untouched, duplicates on one table row | 4/4 |
| approved-in-advance | duplicates in `proposed/` behind one brief in `briefs/`, the fixed entry in `done/`/`wontfix/`, repo untouched | 4/4 |

- Without approval Haiku stops at the table and asks for a decision per row; with approval it writes
  one brief, links both duplicates to it, and closes the fixed entry as done after reading the Makefile.
- Cost: about $0.01 per run.
- After the review fixes (stricter scoring: duplicates alone on one table row, no entry in two state
  dirs; privacy rule moved into steps 3–4; Gotchas): 2/2 and 2/2.
- Cards instead of a table (step 3 presents each group as Today / Why it fails / Change / Why this
  way, opened by a head line with severity, n and ids): the table-row check failed 1/2, so the
  scorer now also accepts a heading or an `Entries:`/`Ids:` line. Before the head-line rule in
  SKILL.md, Haiku sometimes put the ids only in prose; after it, triage 12/13, approved 3/3. Failed
  runs now keep the whole final answer in `--json` output.
