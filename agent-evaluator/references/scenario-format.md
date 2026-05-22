# Scenario Format and Wire Format

## Scenario File Structure

Each scenario file is a self-contained prompt that describes one behavior to test.

```markdown
You are running eval scenario [ID] for the `[agent-name]` subagent.
Working directory: `[repo-root]`

**What's being tested**: [one sentence description]

---

## Instructions

1. [Discovery step if needed — e.g. find a project matching criteria X]
2. Invoke the `[agent-name]` subagent with this exact prompt:
   > "[exact prompt]"
3. Observe the agent's full response.
4. Score it against the criteria below and fill in the result block.
5. Append the completed block to `<evals-dir>/COLLECT-RESULTS.md` using Bash.
6. Display the block to confirm.

---

## Scoring criteria

- **[criterion_name]**: [what yes means]
- **[criterion_name]**: [what yes means]

---

## Result block

---RESULT---
SCENARIO: [ID]
SCORE: [0/1/2/3]
CRITERION_[name]: [yes/no]
...
AGENT_OUTPUT:
[paste agent full response here]
NOTES: [optional]
---END---
```

---

## Wire Format (canonical — do not change without updating scorer + interpreter)

```
---RESULT---
SCENARIO: [ID]
SCORE: [0/1/2/3/na/infra-fail]
CRITERION_[name]: [yes/no/na]
...
AGENT_OUTPUT:
[full agent response — verbatim, not summarized]
NOTES: [optional free text]
---END---
```

**Field rules:**
- Every `CRITERION_*` value must be `yes`, `no`, or `na` — no prose.
- `SCORE` values:
  - `0–3` — normal score (see rubric below)
  - `na` — scenario not applicable to this repo (e.g. no matching projects for the test)
  - `infra-fail` — scorer could not invoke the target agent (excluded from denominator)
- `AGENT_OUTPUT` must be verbatim — the interpreter re-reads it for context.
- `NOTES` is free text; only the interpreter reads it, not parsed programmatically.
- Response must end with `---END---` as the absolute last characters.

---

## Scoring Rubric (canonical)

| Score | Meaning |
|-------|---------|
| 3 | Fully correct: right behavior, right format, nothing superfluous |
| 2 | Mostly correct: minor gap that doesn't break the caller's workflow |
| 1 | Partial: core intent understood but significant error or missing output |
| 0 | Fail: wrong behavior, raw log dump, silent failure, crash, or unauthorized file edit |

**Pass threshold**: score ≥ 2 on all scenarios. Any 0 or 1 triggers an edit.
`na` and `infra-fail` are excluded from the denominator and pass threshold.

---

## Mutating Scenario Markers

Scenarios that modify source files must include explicit setup and cleanup blocks.
Mark them with a `mutates: true` line in the scenario header, or use the naming
convention of prefixing with `C-` (code mutation category).

The orchestrator uses this to determine execution order:
- Non-mutating scenarios run in parallel.
- Mutating scenarios run sequentially with isolation.

---

## Semantically Equivalent Scenario Pairs

When multiple scenarios test the same underlying behavior from different angles,
document the pairing in a comment at the top of each scenario file:

```markdown
<!-- equivalent-pair: A-04 -->
```

The orchestrator uses these to detect scoring inconsistencies — if two scenarios
testing the same behavior diverge by more than 1 point, the lower-scoring one
is flagged as a potential infra-fail rather than a genuine agent failure.
