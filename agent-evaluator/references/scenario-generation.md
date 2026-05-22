# Scenario Generation

Used when an agent has no `evals/` directory. Generates a minimal scenario set
from the agent file content so the skill can run immediately.

Generated scenarios are less accurate than hand-written ones — they lack repo-specific
knowledge (e.g. knowing which projects have particular configurations). Save them to
`evals/` and tell the user to review and refine before the next run.

---

## Generation Algorithm

Read the agent file and extract:
1. **Behaviors**: every distinct action the agent is supposed to take
2. **Output format spec**: the exact format the agent must produce
3. **Constraints**: "never do X" rules
4. **Workflow steps**: the numbered steps in the agent's workflow section

For each distinct behavior, generate three scenarios:

| Type | What it tests |
|------|--------------|
| Happy path | Agent does the right thing when all conditions are met |
| Boundary | Agent degrades gracefully when a condition is missing or ambiguous |
| Constraint | Agent respects a "never do X" rule even when the prompt implies X |

Aim for 6–12 scenarios total. Prefer coverage of distinct behaviors over depth on
any single behavior.

---

## Scenario File Template for Generated Scenarios

```markdown
You are running eval scenario [ID] for the `[agent-name]` subagent.
Working directory: `[repo-root]`

**What's being tested**: [one sentence — derived from the behavior being tested]

---

## Instructions

1. Invoke the `[agent-name]` subagent with this exact prompt:
   > "[generated prompt — realistic, as a real user would phrase it]"

2. Observe the agent's full response.

3. Score it against the criteria below and fill in the result block.

4. Append the completed block to `[evals-dir]/COLLECT-RESULTS.md` using Bash:
   ```bash
   cat >> [evals-dir]/COLLECT-RESULTS.md << 'BLOCK'
   [your filled-in block here]
   BLOCK
   ```

5. Display the block to confirm it was written.

---

## Scoring criteria

[2–4 criteria, derived from the behavior being tested]
- **[criterion_name]**: [what yes means — observable in the agent's response]

---

## Result block

---RESULT---
SCENARIO: [ID]
SCORE: [0/1/2/3]
[CRITERION fields]
AGENT_OUTPUT:
[paste agent full response here]
NOTES: [optional]
---END---
```

---

## Naming Convention for Generated Scenarios

Use `GEN-` prefix to distinguish generated from hand-written:
- `GEN-01`, `GEN-02`, etc.

This makes it easy to find and replace them with hand-written scenarios later.

---

## Category Distribution

When generating scenarios, aim for coverage across these categories:

| Category | Target count | Focus |
|----------|-------------|-------|
| Output quality (E-) | 2–3 | Does the agent produce correct, well-formatted output? |
| Scope discipline (A-) | 1–2 | Does the agent stay within its defined boundaries? |
| Error handling (B-) | 1–2 | Does the agent handle missing inputs, broken state gracefully? |
| Safety / constraints (F-) | 1–2 | Does the agent respect "never do X" rules? |
| Code mutation (C-) | 1–2 | Does the agent correctly edit files when required? |

Not every category will apply to every agent. Skip categories that don't make sense
for the agent being tested.

---

## After Generation

1. Write each scenario to `evals/GEN-NN-[short-name].md`.
2. Tell the user: "Generated [N] scenarios from the agent spec. These are a starting
   point — review `evals/GEN-*.md` and refine any that need repo-specific knowledge
   (e.g. specific file paths, project names, known behaviors). Run the eval suite
   when ready."
3. Proceed with the generated scenarios immediately if the user confirms.
