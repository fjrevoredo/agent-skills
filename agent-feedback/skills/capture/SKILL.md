---
name: capture
description: |
  Use unprompted, the moment you hit friction with the agent setup or a repo's dev tooling: an
  instruction, memory or doc is wrong or stale; a concept is missing, unclear or defined two ways; the
  user corrects you; you work around something; access or a permission is missing; a tool, skill, MCP,
  hook, test, build, CI or script misbehaves. Records one feedback entry in one call, then you carry on
  with the task. Also when the user asks to note something as feedback, and for retro findings the
  user accepts. Bugs and design of the product code or the task itself stay in the task.
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/capture.py *)
metadata:
  version: "1.0.0"
---

# Capture feedback

One call per distinct problem, then straight back to the task. Fixing the problem is someone else's
job, later.

## Record

```bash
${CLAUDE_SKILL_DIR}/scripts/capture.py add --source agent --kind docs --severity medium --suggestion 'One-line fix idea' <<'EOF'
What happened, where, what it cost, what was expected.
EOF
```

The text goes on stdin through the quoted `<<'EOF'` heredoc, so backticks and `$` in it stay literal;
keep the suggestion free of single quotes. Prints `{"id", "path"}`. The script fills in time, session, agent, model, repo, branch and path.

- `--source`: `agent` (you noticed it), `user` (the user asked), `retro` (an accepted retro finding).
- `--kind` (optional, a guess is fine):
  `instruction` (CLAUDE.md, AGENTS.md or memory rule wrong, stale, missing),
  `skill` (misfired, didn't trigger, wrong step),
  `tooling` (script, CLI, MCP, hook, a repo's test or build tooling),
  `access` (permission, credential, VPN, connector),
  `infra` (CI, cluster, environment),
  `docs` (README, runbook, path reference: *how to work with a thing*),
  `knowledge` (domain concept missing, unclear or conflicting: *what a thing is*),
  `other`.
- `--severity` (optional): `high` blocked the work or gave a wrong result; `medium` a workaround that
  cost noticeable time or tokens; `low` an annoyance. Leave it out when unclear.
- `--suggestion` (optional): one line.

## The text

It must make sense to a reader who never sees this session. Name the exact file (repo-relative
path), command, skill or term; say what you expected, what happened, and what it cost. For `--source user`, quote the user's
words verbatim, then add one line of context.

Keep secrets, customer data and transcript excerpts out of it.

## Then

Continue the task. At the end of your turn, add one line: `Noted feedback: <short summary>`.

## Gotchas

- Exit 64 means a bad flag or empty text: the message names the valid values; fix and rerun once.
- Run the command exactly as written above (the path first, no `cd`, no `python3` prefix), or a
  permission prompt interrupts the user.
- If the script cannot run, put the feedback in your end-of-turn line instead.
