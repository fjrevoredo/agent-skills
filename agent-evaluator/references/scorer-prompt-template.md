# Scorer Subagent Prompt Templates

Two variants: one for non-mutating scenarios (orchestrator already captured the agent
response), one for mutating scenarios (scorer must run setup, invoke, and cleanup itself).

---

## Non-mutating Scorer Prompt

Use this for all scenarios that do not modify source files.

```
You are scoring an eval scenario for the `[AGENT_NAME]` subagent.

## Scenario [SCENARIO_ID] — [SCENARIO_DESCRIPTION]

**What was tested**: [what_being_tested line from scenario file]

[DISCOVERY_FACTS if any, e.g.:]
DISCOVERY: project_without_tests = libs/my-lib
DISCOVERY: first_spec_file = my-component.spec.ts

## The agent's captured response

[CAPTURED_AGENT_RESPONSE]

## Scoring criteria

Score each criterion yes/no based solely on the captured response above.
Do not invoke the agent or read the agent file.

[CRITERION list with descriptions from scenario file]

## Scoring rubric

| Score | Meaning |
|-------|---------|
| 3 | Fully correct: right behavior, right format, nothing superfluous |
| 2 | Mostly correct: minor gap that doesn't break the caller's workflow |
| 1 | Partial: core intent understood but significant error or missing output |
| 0 | Fail: wrong behavior, raw log dump, silent failure, or unauthorized file edit |

## Your output

Fill in the block below. YOUR RESPONSE MUST END WITH `---END---` AS THE ABSOLUTE
LAST CHARACTERS. Any text after `---END---` will cause this result to be discarded
by the orchestrator.

---RESULT---
SCENARIO: [SCENARIO_ID]
SCORE: [0/1/2/3]
[CRITERION_fields: yes/no/na]
AGENT_OUTPUT:
[paste the captured response verbatim — do not summarize]
NOTES: [optional observations]
---END---
```

---

## Mutating Scorer Prompt

Use this for scenarios that modify source files. These run in isolated worktrees (if
available) or with explicit setup/cleanup so mutations cannot conflict.

```
You are running and scoring eval scenario [SCENARIO_ID] for the `[AGENT_NAME]` subagent.
Working directory: [REPO_ROOT]

**What's being tested**: [what_being_tested line from scenario file]

## Instructions

Follow these steps in order. Do not skip cleanup.

### Setup
[setup instructions from scenario file — commands to mutate files]

### Invoke the agent
Invoke the `[AGENT_NAME]` subagent with this exact prompt:
> "[EXACT_SCENARIO_PROMPT]"

Capture the full response.

### Cleanup
[cleanup instructions from scenario file — e.g. git restore commands]

Run cleanup regardless of whether the agent invocation succeeded.

### Score
Score the captured response against these criteria:
[CRITERION list with descriptions]

## Scoring rubric

| Score | Meaning |
|-------|---------|
| 3 | Fully correct |
| 2 | Mostly correct — minor gap |
| 1 | Partial — significant error |
| 0 | Fail |

If the agent tool was unavailable or loaded the wrong agent, set SCORE: infra-fail.
Never score by reading the agent spec — only score observed behavior.

## Your output

YOUR RESPONSE MUST END WITH `---END---` AS THE ABSOLUTE LAST CHARACTERS.

---RESULT---
SCENARIO: [SCENARIO_ID]
SCORE: [0/1/2/3/infra-fail]
[CRITERION_fields: yes/no/na]
AGENT_OUTPUT:
[paste captured response verbatim, or "invocation failed: <reason>"]
NOTES: [optional]
---END---
```
