---
name: process
description: Go through the collected agent-feedback entries with the user, group them, and hand each group off to its fix.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/process.py *)
metadata:
  version: "1.0.0"
---

# Process feedback

Turn the open feedback entries into fixes, together with the user. Every entry ends this run either
still in `inbox/` because the user deferred it, or moved with a one-line outcome. Fixing is a hand-off.
Nothing is edited, sent or moved before the user approves it.

Run the script exactly as written (the path first, no `cd`, no `python3` prefix), so it runs without a
permission prompt. `${CLAUDE_SKILL_DIR}/scripts/process.py --help` lists the commands.

## 1. Load the routing

`${CLAUDE_SKILL_DIR}/scripts/process.py paths` gives the state dir, the briefs dir and the routing
file. The routing file says where each target lives on this machine and which hand-off it takes.
If it doesn't exist, copy `routing_template` there, fill it in with the user, and continue.

## 2. Close what landed

`process.py list --state proposed` shows each entry waiting on its `link`: a brief, an MR, an
applied edit, a relayed message. Check each link: is the MR merged, the edit still in place and
working, the message sent? Has a newer inbox entry hit the same problem since? Propose `done` or
`wontfix` per entry. Leave it in `proposed/` while the work is still pending.

## 3. Triage the inbox

`process.py list` shows every open entry. Group the entries that share a fix (same file, same tool,
same rule). Recurrence is signal: a group of four outranks a lone entry of the same severity. For
each group:

- **Check the present.** Read the file, skill, `--help` or doc the entries name, as it is now.
  Entries go stale: the fix may have landed, or the tool may be gone. Mark the group *fixed*,
  *obsolete* or *open* from what you read, not from the entry text.
- **Read the transcript** only when the entry text leaves the problem unclear:
  `process.py transcript <id> --minutes 15`.
- **Pick the target and hand-off** from the routing file.

Show the user one table, ranked by severity, then recurrence:

| Group | Entries | n | Kind | Severity | State | Target → hand-off |
|---|---|---|---|---|---|---|

The step is done when every inbox entry is in exactly one row, and the user has decided each row:
go, change the target, defer, or wontfix.

## 4. Hand off

Work through the decided rows one group at a time:

- **setup edit**: show the exact diff, apply it once the user approves, then move the entries to
  `proposed/` with the edited file as `--link`. They reach `done` in a later run (step 2), after the
  edit has held up.
- **brief**: write `<briefs>/<slug>.md` (template below), show it, move the entries to `proposed/`
  with the brief as `--link`. Starting the work in that repo is the user's call.
- **relay**: draft the exact text and where it goes, hand it to the channel the routing file names,
  move the entries to `proposed/` with where it went as `--link`.
- **wontfix**, *fixed*, *obsolete*: move straight to `wontfix/` or `done/` with the reason.

```bash
${CLAUDE_SKILL_DIR}/scripts/process.py move <id> <id> --to proposed --outcome 'One line' --link '<path or URL>'
```

Keep single quotes out of the outcome. The script refuses an unknown id or a `proposed` move without a link, and moves nothing.

Brief template:

```markdown
# <repo>: <one-line problem>

Problem: what goes wrong, for whom, how often (n entries).
Evidence: entry ids, with one line each; no transcript excerpts.
Proposed change: files and what changes in them.
Done when: a check anyone can run.
```

## 5. Report

End with the counts (moved to `proposed/`, `done/`, `wontfix/`, left in `inbox/`) and the open links.
Transcript copies hold whole sessions: they stay on this machine, and their content never goes into a brief,
a relay or a report.
