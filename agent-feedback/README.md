# agent-feedback

A Claude Code plugin that lets agents record friction with their setup the moment it happens:
wrong or stale instructions, skills that misfire, broken tooling, missing access, unclear domain
knowledge, a repo's test or build tooling. Entries pile up locally and are processed later, on demand.

## Install

```bash
claude plugin marketplace add https://github.com/fjrevoredo/agent-skills.git
claude plugin install agent-feedback@agent-skills
```

Uninstall with `claude plugin uninstall agent-feedback@agent-skills`.

## What it contains

| Part | Purpose |
|---|---|
| `skills/capture` | `/agent-feedback:capture`: when and how to record; its `allowed-tools` grants the script, so recording never prompts |
| `skills/capture/scripts/capture.py` | Standard-library Python; writes the entry, keeps a gzip copy of the session transcript |
| `hooks/hooks.json` | SessionStart: one reminder line (the skill description alone did not trigger in the evals). SessionEnd: refreshes the transcript copy of sessions that have open entries |

## Storage

`$AGENT_FEEDBACK_DIR`, else `${XDG_STATE_HOME:-~/.local/state}/agent-feedback`:

```
inbox/  proposed/  done/  wontfix/   one <id>.md per entry; the folder is its state
transcripts/<session>.jsonl.gz       copy of the session transcript (Claude Code deletes its own after 30 days)
briefs/                              hand-off briefs written during processing
```

Transcript copies hold the whole session. They stay on this machine.

## Development

```bash
python3 -m unittest discover agent-feedback/tests     # script tests
claude plugin validate agent-feedback
python3 agent-feedback/evals/run_evals.py             # headless Haiku trigger evals (costs tokens)
```
