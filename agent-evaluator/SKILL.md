---
name: agent-evaluator
description: |
  Evaluate a subagent by running its scenario suite as parallel subagents, scoring results against
  observable criteria, and producing exact FIND/REPLACE edits for any failing behaviors. Use this
  skill whenever the user wants to evaluate, test, score, or quality-check a subagent — even if they
  don't use those exact words. Triggers on: "evaluate the agent", "run evals on [agent]", "assess
  agent performance", "score the agent", "check if the agent works", "run the eval suite", "test the
  agent", "quality-check [agent]", "is the agent working correctly", or after applying fixes "did
  that improve things?". Also triggers proactively after an agent file is edited and the user asks
  "does it work now?" or similar.
  Triggers: evaluate agent, run evals, assess agent, score agent, test agent, quality-check, eval
  suite, agent performance, agent working, improve agent, rerun evals, benchmark agent.
metadata:
  version: "1.0.0"
---

# Agent Evaluator

Evaluate subagents by running their scenario suites, scoring each scenario against observable
criteria, and producing exact edits for anything that fails. The user should be able to say
"evaluate my-agent" and get a scored report plus actionable fixes — no manual steps.

## Configurable Paths

These paths are defaults. Override them if the consuming repo uses a different layout.

| Field | Default | Role |
|-------|---------|------|
| `agents_dir` | `.claude/agents/` | Directory containing agent `.md` files |
| `evals_dir` | `<agents_dir>/evals/` | Directory containing scenario files and results |

---

## Step 0 — Parse Input and Locate Agent

Accept: an agent name (e.g. `my-agent`) or a path to an agent `.md` file.

Resolve the agent file:

1. If given a name, look in the configured `agents_dir`:
   ```
   <agents_dir>/<name>.md
   ```
2. If given a path, use it directly.

**If the file does not exist, stop immediately:**

> "Agent not found: `<resolved-path>` does not exist. Check the agent name
> and make sure it is registered before running an eval."

Locate the evals directory — it lives next to the agent file:
```
<agents_dir>/<name>.md          ← agent file
<agents_dir>/evals/             ← scenario files, results
```

If no `evals/` directory exists → generate scenarios (see `references/scenario-generation.md`).

### Quick Mode

Check for `--quick` flag in the user's prompt. Quick mode runs a representative subset of
scenarios (roughly 5) that covers the most important behavior categories. Select the subset
by scanning scenario filenames for coverage across categories — prioritize scenarios that
test output quality, scope discipline, error handling, and safety.

Use quick mode when the user mentions "quick check" or "just the critical ones" after a
small prompt edit.

---

## Step 1 — Smoke Test

Before running the full suite, confirm the agent can be invoked correctly:

Invoke the target agent with a simple identity prompt:
> "What is your purpose? Reply in one sentence."

If the response is coherent and from the right agent → proceed.
If it fails, loads the wrong agent, or returns an error → **abort immediately**:

> "Smoke test failed — the agent could not be invoked. Check that `<agent-name>` is
> registered and try again. Full eval aborted."

Do not attempt to run scenarios against a broken invocation path.

---

## Step 2 — Load Scenarios

Read every scenario file in the `evals/` directory. For each, extract:
- Scenario ID (from filename or content header)
- Whether it mutates files (look for setup/cleanup blocks or a `mutates: true` marker)
- Full file content

Apply quick mode filter if active.

### Scenario Categories

Scenarios should be organized with a category prefix in their filename:

| Prefix | Category | Example |
|--------|----------|---------|
| `E-` | Output quality / correctness | `E-01-correct-output-format.md` |
| `C-` | Code mutation / edit scenarios | `C-01-fix-broken-test.md` |
| `A-` | Scope and boundary decisions | `A-01-stays-in-scope.md` |
| `B-` | Build/test integration | `B-01-clean-test-output.md` |
| `D-` | Dependency/impact analysis | `D-01-affected-scope.md` |
| `F-` | Safety and constraint respect | `F-01-no-unauthorized-edits.md` |
| `GEN-` | Auto-generated (see scenario generation) | `GEN-01-happy-path.md` |

This convention is recommended but not required — the evaluator works with any filenames matching `*.md` in the evals directory.

---

## Step 3 — Pre-compute Discovery Data

Several scenarios may need repo-specific facts before they can run. Compute these once and
inject them into the relevant scenario prompts. This prevents each scorer from re-running
the same shell commands (wastes tokens) or doing it incorrectly.

**How to identify what to discover:**

1. Scan scenario files for `DISCOVERY:` placeholders or instructions that say "find a project with X".
2. Run the necessary shell commands to resolve those placeholders.
3. Inject results as `DISCOVERY:` lines at the top of the relevant scenario prompts before spawning scorers.

Example format:
```
DISCOVERY: project_without_tests = libs/my-lib
DISCOVERY: first_spec_file = my-component.spec.ts
```

If a discovery returns nothing (e.g. no matching projects), inject:
```
DISCOVERY: test_framework_project = none — mark relevant scenario as SCORE: na
```

The discovery commands are repo-specific — read the scenario files to determine what facts are needed. Common patterns include: finding projects with specific configurations, locating test files, identifying build targets.

---

## Step 4a — Non-mutating Scenarios

**The orchestrator — not the scorer — invokes the target agent.** This prevents scorer
subagents from loading the wrong skill, which can produce false scores.

For each non-mutating scenario:

1. Extract the exact prompt from the scenario file (typically the line after `> "`).
2. Inject discovery data if applicable.
3. Invoke the target agent directly with the exact scenario prompt.
4. Capture the full response.
5. Pass it to a scorer subagent with the non-mutating template from `references/scorer-prompt-template.md`.

Spawn **all scorer subagents in a single message** so they run in parallel.

---

## Step 4b — Mutating Scenarios

These temporarily edit source files. Run **one at a time** using isolated worktrees (if
available) or careful setup/cleanup so mutations cannot conflict.

For each mutating scenario, spawn a scorer that handles setup → invoke → score → cleanup.
Use the mutating variant from `references/scorer-prompt-template.md`.

Run mutating scenarios sequentially. Wait for each to complete before starting the next.

---

## Step 5 — Validate and Collect Result Blocks

As each subagent returns, **immediately validate** that the response ends with `---END---`.
Collect the result blocks in memory as they arrive — do not write to disk yet.

If a block is missing or malformed, synthesize a fallback immediately:

```
---RESULT---
SCENARIO: [ID]
SCORE: infra-fail
CRITERION_runner_completed: no
AGENT_OUTPUT: scorer did not return a result block
NOTES: re-run this scenario manually
---END---
```

`infra-fail` is excluded from the score denominator (same as `na`). It signals an
infrastructure problem, not an agent behavior problem — do not let it inflate failure counts.

---

## Step 6 — Consistency Check

Before writing results, scan for semantically equivalent scenario pairs. These are scenarios
that test the same underlying behavior from different angles.

Look for pairs in scenario metadata or identify them by comparing `what_being_tested` fields.
If two equivalent scenarios differ by more than 1 point, flag them:

```
⚠️ CONSISTENCY: [ID-A] scored 0, [ID-B] scored 3 — same behavior, high divergence.
   This likely indicates an invocation problem on [ID-A], not an agent regression.
   Treat [ID-A] as infra-fail and re-run manually to confirm.
```

---

## Step 7 — Write COLLECT-RESULTS.md

Once all result blocks are collected (from scorers or synthesized as fallbacks),
overwrite `<evals-dir>/COLLECT-RESULTS.md` in a single write:

```markdown
# Eval Results — <agent-name>
_Collected by agent-evaluator skill — <date>_

[all result blocks, one per scenario, separated by blank lines]
```

---

## Step 8 — Interpret Results

Read `references/interpreter-prompt.md`. Substitute:
- `<AGENT_FILE_CONTENT>` → full content of the agent file
- `<RESULTS>` → full content of COLLECT-RESULTS.md
- `<EVALS_DIR>` → path to the evals directory
- `<AGENT_NAME>` → the agent's name

Spawn an interpreter subagent with the substituted prompt.

The interpreter writes its output to `<evals-dir>/LAST-INTERPRET-OUTPUT.md`.

If the interpreter subagent fails, write a minimal fallback to that file:
```markdown
# Interpreter failed
Run the interpretation manually with the collected results below.

[paste COLLECT-RESULTS.md content]
```

---

## Step 9 — Present Results and Offer Edits

Display to the user:
1. The score summary table (copied from LAST-INTERPRET-OUTPUT.md).
2. Count of scenarios scoring 0 or 1 (excluding `na` and `infra-fail`).
3. Count of proposed edits.

Then ask:
> "Found [N] scenarios scoring 0–1. [M] edits proposed. Apply them now?"

**If yes:**
- Apply each `FIND / REPLACE WITH` block to the agent file using the Edit tool.
- Re-run only the failing scenarios (repeat steps 3–8 scoped to those IDs).
- Report the delta: "X improved, Y still failing."

**If no:**
- Confirm: "Fixes are in `<evals-dir>/LAST-INTERPRET-OUTPUT.md`."
- Done.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/scorer-prompt-template.md` | When building scorer subagent prompts (steps 4a, 4b) |
| `references/interpreter-prompt.md` | When building the interpreter subagent prompt (step 8) |
| `references/scenario-format.md` | Wire format, scoring rubric, result block spec — reference when validating or synthesizing blocks |
| `references/scenario-generation.md` | When no evals/ dir exists and scenarios must be generated |

---

## Gotchas

1. **Scorer invokes the wrong agent.** If the scorer subagent uses a Skill tool instead of the Agent tool, it may load a skill instead of the target agent. That's why the orchestrator (you) must invoke the target agent for non-mutating scenarios and pass the captured response to the scorer. The scorer only scores — it never invokes.

2. **Missing `---END---` delimiter.** If a scorer's response doesn't end with `---END---`, the result block is considered malformed. Synthesize a fallback `infra-fail` block rather than trying to parse a partial result.

3. **Mutating scenarios conflict.** Never run multiple mutating scenarios in parallel — they edit source files and can corrupt each other's state. Always run them sequentially, and always verify cleanup completed before starting the next one.

4. **Discovery data stales.** Pre-computed discovery data reflects the repo at eval time. If someone pushes changes mid-eval, discovery may be stale. For long-running evals, re-run discovery before each mutating scenario.

5. **infra-fail vs. genuine failure.** When a scenario fails to invoke the agent at all (wrong name, tool unavailable), mark it `infra-fail`, not `0`. `infra-fail` is excluded from the score denominator so it doesn't unfairly drag down the agent's score. Reserve `0` for cases where the agent ran but produced wrong behavior.

6. **Quick mode selection.** When using quick mode, don't just pick the first 5 scenarios. Select for coverage across behavior categories (output quality, scope discipline, error handling, safety) to get a meaningful signal from fewer runs.
