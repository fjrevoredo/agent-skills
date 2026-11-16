# agent-feedback

A Claude Code plugin that lets agents record friction with their setup the moment it happens:
wrong or stale instructions, skills that misfire, broken tooling, missing access, unclear domain
knowledge, a repo's test or build tooling. Entries pile up locally and are processed later, on demand,
with `/agent-feedback:process`.

## Install

```bash
claude plugin marketplace add https://github.com/fjrevoredo/agent-skills.git
claude plugin install agent-feedback@fjrevoredo-agent-skills
```

Uninstall with `claude plugin uninstall agent-feedback@fjrevoredo-agent-skills`.

## What it contains

| Part | Purpose |
|---|---|
| `skills/capture` | `/agent-feedback:capture`: when and how to record; its `allowed-tools` grants the script, so recording never prompts |
| `skills/capture/scripts/capture.py` | Standard-library Python; writes the entry, keeps a gzip copy of the session transcript |
| `skills/process` | `/agent-feedback:process` (typed by you, never triggered by the model): groups the open entries, checks them against the current setup, and hands each group off (setup edit, brief, relay, wontfix) after your approval |
| `skills/process/scripts/process.py` | `list`, `move` (records outcome, link, time; drops a session's transcript copy once its entries are closed), `transcript` (the minutes before an entry), `paths` |
| `skills/process/routing.template.md` | Where targets live and how fixes reach them; copied to the routing file on the first run and filled in there |
| `hooks/hooks.json` | SessionStart: one reminder line (the skill description alone did not trigger in the evals). SessionEnd: refreshes the transcript copy of sessions that have open entries |

## Storage

`$AGENT_FEEDBACK_DIR`, else `${XDG_STATE_HOME:-~/.local/state}/agent-feedback`:

```
inbox/  proposed/  done/  wontfix/   one <id>.md per entry; the folder is its state
transcripts/<session>.jsonl.gz       copy of the session transcript (Claude Code deletes its own after 30 days)
briefs/                              hand-off briefs written during processing
routing.md                           where targets live on this machine ($AGENT_FEEDBACK_ROUTING overrides the path)
```

`inbox/` → `proposed/` (waiting on its `link`: a brief, an applied edit, a relayed message) → `done/` or
`wontfix/`, each move with a one-line `outcome`.

Transcript copies hold the whole session. They stay on this machine.

## Development

```bash
python3 -m unittest discover agent-feedback/tests     # script tests
claude plugin validate agent-feedback
python3 agent-feedback/evals/run_evals.py             # headless Haiku capture-trigger evals (costs tokens)
python3 agent-feedback/evals/run_evals.py --suite process   # headless Haiku processing evals
```
