---
name: skill-extractor
description: |
  Port a repo-specific skill into a generic, reusable skill for the agent-skills library. Use this skill
  whenever the user asks to extract a skill from a project, generalize a skill, port a skill to another repo,
  convert a project-specific skill into a reusable one, or remove repo-specific context from a skill. Also use
  when the user mentions skill extraction, skill generalization, or creating a library skill from a project skill —
  even if they don't explicitly say "extract" or "generalize." If a skill exists in a project's `.agents/skills/`
  directory and the user wants to make it reusable across repositories, this skill should be used.
  Triggers: extract skill, generalize skill, port skill, convert skill, remove repo-specific, make skill reusable,
  skill extraction, skill generalization, library skill, repo-agnostic skill, skill from project.
metadata:
  version: "1.0.0"
---

# Skill Extractor

Transform a repo-specific skill into a generic, reusable skill for the agent-skills library.

This skill has two distinct phases. Complete Phase 1 fully before starting Phase 2 — they serve different purposes and must not be mixed.

## Phase 1: Extraction Workflow

Read `SKILL_RULES.md` at the repo root first. All output must conform to its standards.

### Step 1: Analyze Source Skill

Read the source `SKILL.md` and identify every repo-specific element:

| Element type | What to look for |
|--------------|-----------------|
| Hardcoded paths | `docs/todo/TODO.md`, `src/backend/`, `website/` |
| Project names | "MyProject", "the app", "our codebase" |
| Domain conventions | Specific file formats, database schemas, auth flows |
| Toolchain assumptions | `cmd.exe /c`, `bun run`, `cargo test` |
| Skill references | Mentions of other project-specific skills |
| File references | Absolute paths or project-relative paths in operations |

Write down every finding. This is your extraction inventory.

### Step 2: Classify Elements

Categorize each finding from Step 1:

| Category | Action | Example |
|----------|--------|---------|
| **Keep** | Universal guidance that applies to any repo | Format rules, ID sequencing, em-dash convention |
| **Generalize** | Valuable but tied to specific paths/names | Replace `docs/todo/TODO.md` with a frontmatter-configurable default |
| **Remove** | Repo-specific noise with no general value | "Run from this Codex shell with the Windows toolchain" |
| **Extract to template** | Files the agent should create in the target repo | `TODO.md` boilerplate, `TODO_ARCHIVE.md` skeleton |

### Step 3: Generalize

Apply these transformations to the skill body:

1. **Paths:** Replace hardcoded paths with references to frontmatter-configurable defaults. Add a "Configurable Paths" table near the top of the skill:

   ```markdown
   ## Configurable Paths

   | Field | Default | Role |
   |-------|---------|------|
   | `todo_path` | `docs/todo/TODO.md` | Active backlog |
   ```

2. **Project names:** Replace with generic terms ("the target repo", "the consuming project").

3. **Domain conventions:** Make them configurable options or remove them if they don't generalize.

4. **Toolchain commands:** Replace shell-specific commands with shell-agnostic descriptions (e.g., "search for the pattern" instead of `rg -o 'TODO-\d{4}'`).

5. **Skill references:** Remove references to project-specific skills. If a complementary skill exists in the agent-skills library, reference it by name.

### Step 4: Create Templates

For each element classified as "Extract to template" in Step 2, create a template file in `assets/`:

- Templates should be usable without modification — the agent copies them to the target location
- Include placeholder content that demonstrates the format (e.g., `TODO-0000` as the starting ID)
- Keep templates minimal — only the structure, not example content

### Step 5: Write Generic SKILL.md

Compose the new skill following `SKILL_RULES.md` standards:

1. **Frontmatter:** `name` (kebab-case, matches directory), `description` (under 1024 chars, imperative, pushy, with trigger keywords), and `metadata.version: "1.0.0"`
2. **Structure:** Under 500 lines. Use `references/` for detail beyond this limit.
3. **Operations:** Each operation has step-by-step instructions and validation guidance.
4. **Gotchas:** Include non-obvious pitfalls specific to this skill's domain.
5. **Templates:** Reference `assets/` templates where the agent should use them.
6. **Key Files Reference:** A table mapping configurable paths to their roles.

### Step 6: Provide Optional Dirs Checklist

After writing the SKILL.md, evaluate whether these directories are warranted:

| Directory | Create when... | Skip when... |
|-----------|---------------|--------------|
| `assets/` | The skill needs templates the agent copies into the target repo | No templates needed (skill only operates on existing files) |
| `references/` | Detailed docs are needed but only in specific scenarios | All guidance fits in SKILL.md under 500 lines |
| `scripts/` | The agent would repeatedly reinvent the same logic | One-off commands or simple operations suffice |

Create only the directories that pass the "Create when" test. Don't create directories preemptively.

---

## Phase 2: Description Optimization

**Only start Phase 2 after Phase 1 is complete and the new SKILL.md is written.**

The description is the primary triggering mechanism. A well-optimized description ensures the skill activates when it should and stays silent when it shouldn't.

### Step 1: Design Trigger Eval Queries

Create ~20 eval queries — a mix of should-trigger and should-not-trigger:

**Should-trigger (8-10):**
- Varied phrasing (formal, casual, with typos)
- Varied explicitness (names the skill's domain vs. describes the need)
- Varied detail (terse vs. context-heavy with file paths and backstory)
- Edge cases where the connection isn't obvious

**Should-not-trigger (8-10):**
- Near-misses that share keywords but need different capabilities
- Adjacent domains where another skill is more appropriate
- Avoid obviously irrelevant queries — they test nothing

Save queries as JSON:
```json
[
  { "query": "the user prompt", "should_trigger": true },
  { "query": "another prompt", "should_trigger": false }
]
```

### Step 2: Run the Optimization Loop

If the `skill-creator` skill is available in your environment, use its description optimization loop — it automates eval query generation, train/val splitting, iterative refinement, and HTML report generation.

If not available, perform the optimization manually:

1. **Split** queries into train (~60%) and validation (~40%) sets, keeping proportional should-trigger/should-not-trigger mix.
2. **Evaluate** the current description on the train set. Run each query 3 times and compute trigger rate.
3. **Identify failures:** should-trigger queries below 0.5 rate, should-not-trigger queries above 0.5 rate.
4. **Revise** the description:
   - If should-trigger queries fail: description is too narrow. Broaden scope, add context about when the skill is useful.
   - If should-not-trigger queries false-fire: description is too broad. Add specificity about what the skill does *not* do.
   - Avoid adding specific keywords from failed queries — generalize to the underlying concept.
5. **Repeat** up to 5 iterations.
6. **Select** the best iteration by validation set pass rate (not train set — that avoids overfitting).

### Step 3: Apply the Result

Update the `description` field in the new SKILL.md frontmatter with the optimized description. Verify it stays under 1024 characters.

---

## Gotchas

1. **Over-generalizing:** Removing domain-specific guidance that actually applies broadly. If a convention (like sequential IDs or em-dash formatting) is used across multiple projects, keep it — it's universal, not project-specific.
2. **Under-generalizing:** Leaving hardcoded paths, project names, or toolchain commands in the body. Run a final grep for the source project's name and known paths before declaring done.
3. **Description creep:** Descriptions tend to grow during optimization. Check the character count after every revision — the 1024 limit is hard.
4. **Template bloat:** Creating templates for files the target repo likely already has. Only template files that serve as bootstraps for repos that don't yet have the system.
5. **Mixing phases:** Optimizing the description before the skill body is finalized. Phase 1 produces the skill; Phase 2 optimizes its description. Never run Phase 2 on a draft skill body — you'll waste iterations refining a description for a skill that will change.
6. **Losing the "why":** When generalizing, don't strip out explanations of *why* a rule exists. Agents follow instructions more reliably when they understand the purpose. "Use em-dash because it's the delimiter that separates title from description in the format contract" is better than "ALWAYS use em-dash."

---

## Validation Checklist

Run this checklist before declaring the extraction complete. All items must pass.

- [ ] `SKILL.md` exists at `skill-name/SKILL.md` in the agent-skills repo
- [ ] Frontmatter has `name` (kebab-case), `description` (under 1024 chars), and `metadata.version: "1.0.0"`
- [ ] `name` matches the directory name
- [ ] No references to the source project's name, paths, or conventions remain in the skill body
- [ ] Hardcoded paths are replaced with frontmatter-configurable defaults (if the skill uses paths)
- [ ] Toolchain-specific commands are replaced with shell-agnostic descriptions
- [ ] SKILL.md body is under 500 lines
- [ ] Each operation has validation guidance
- [ ] Gotchas section exists with non-obvious pitfalls
- [ ] Templates in `assets/` (if any) are usable without modification
- [ ] The original source skill is unchanged
- [ ] Phase 2 (description optimization) was run after Phase 1 completed
