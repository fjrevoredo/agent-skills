# SKILL_RULES.md

Repo-wide standards for all skills in this repository. Every skill added here must conform to these rules. The skill extractor (`skill-extractor/`) enforces them automatically; manual skill creation should reference this document.

## Table of Contents

1. [Frontmatter Standards](#1-frontmatter-standards)
2. [Description Optimization](#2-description-optimization)
3. [Skill Structure](#3-skill-structure)
4. [Writing Guidelines](#4-writing-guidelines)
5. [Scripts Standards](#5-scripts-standards)
6. [Evaluation Standards](#6-evaluation-standards)
7. [Quality Gates](#7-quality-gates)
8. [Versioning](#8-versioning)

---

## 1. Frontmatter Standards

Every `SKILL.md` must start with YAML frontmatter containing these fields:

```yaml
---
name: skill-name
description: |
  What the skill does and when to trigger it.
  Include trigger keywords.
metadata:
  version: "1.0.0"
---
```

### Required Fields

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | Kebab-case identifier. Must match the directory name. |
| `description` | string | Under 1024 characters. See [Description Optimization](#2-description-optimization). |
| `metadata.version` | string | Semantic version (see [Versioning](#8-versioning)). Starts at `"1.0.0"`. |

### Optional Fields

| Field | Type | Purpose |
|-------|------|---------|
| `compatibility` | string | Runtime requirements (e.g., "Requires Node.js 18+", "Requires Python 3.11+"). |

### Anti-examples

```yaml
# BAD: name uses spaces, no metadata version
---
name: My Skill
description: Does stuff.
---

# BAD: description exceeds 1024 characters (will be truncated)
---
name: data-processor
description: |
  [500+ words of detailed explanation that will get cut off...]
metadata:
  version: "1.0.0"
---
```

### Good Example

```yaml
---
name: todo-manager
description: |
  End-to-end management of TODO items in a Markdown-based backlog. Covers creation with auto-assigned IDs,
  status tracking, archival of completed items, and format validation. Use this skill whenever the user asks to
  add a new TODO, check TODO status, archive completed items, validate the TODO system, or set up a new TODO
  backlog from scratch. Also use when the user mentions a task list, backlog, roadmap, or task tracking in a
  Markdown file — even if they don't explicitly say "TODO".
  Triggers: TODO, todo item, add todo, create todo, todo status, archive todo, validate TODO,
  TODO ID, TODO-0001, check TODO, todos, list todos, todo list, backlog, task tracking, roadmap, task list.
metadata:
  version: "1.0.0"
---
```

*Source: [agentskills.io specification](https://agentskills.io/specification)*

---

## 2. Description Optimization

The `description` field is the primary triggering mechanism. Agents load only `name` + `description` at startup to decide which skills to consult.

### Writing Principles

- **Use imperative phrasing.** Tell the agent when to act: "Use this skill when..." not "This skill does..."
- **Focus on user intent.** Describe what the user is trying to achieve, not the skill's internal mechanics.
- **Be pushy.** Explicitly list contexts where the skill applies, including cases where the user doesn't name the domain directly.
- **Keep it concise.** A few sentences to a short paragraph. Hard limit: 1024 characters.

### Testing Trigger Accuracy

To verify a description works, design ~20 eval queries:

| Type | Count | Purpose |
|------|-------|---------|
| Should-trigger | 8-10 | Varied phrasing, explicitness, detail, complexity |
| Should-not-trigger | 8-10 | Near-misses that share keywords but need different capabilities |

Run each query 3 times and compute trigger rate. A query passes if:
- `should_trigger=true` and rate ≥ 0.5, or
- `should_trigger=false` and rate < 0.5

### Optimization Loop

1. Evaluate current description on train set (~60% of queries).
2. Identify failures: should-trigger that didn't fire, should-not-trigger that false-fired.
3. Revise: generalize from failures (don't add specific keywords — address the underlying concept).
4. Repeat up to 5 iterations.
5. Select the best iteration by validation set (~40%) pass rate.

**Tip:** The `skill-creator` skill automates this loop end-to-end.

### Anti-examples

```yaml
# BAD: too narrow, won't trigger on casual requests
description: Process CSV files with pandas.

# BAD: too broad, will trigger on unrelated requests
description: Handle any data processing, analysis, visualization, or file manipulation task.

# GOOD: specific about what, broad about when
description: >
  Analyze CSV and tabular data files — compute summary statistics,
  add derived columns, generate charts, and clean messy data. Use this
  skill when the user has a CSV, TSV, or Excel file and wants to
  explore, transform, or visualize the data, even if they don't
  explicitly mention "CSV" or "analysis."
```

*Source: [agentskills.io optimizing-descriptions](https://agentskills.io/skill-creation/optimizing-descriptions.md)*

---

## 3. Skill Structure

### Directory Layout

```
skill-name/
├── SKILL.md          (required — core instructions)
├── assets/           (optional — templates, icons, fonts)
├── references/       (optional — detailed docs loaded on demand)
├── scripts/          (optional — executable code)
└── evals/            (optional — test cases)
    └── evals.json
```

### Progressive Disclosure

Skills use three levels of context loading:

1. **Metadata** (name + description) — Always in context (~100 words)
2. **SKILL.md body** — Loaded when skill triggers (<500 lines, <5000 tokens ideal)
3. **Bundled resources** — Loaded on demand when the agent reads `references/`, `assets/`, or runs `scripts/`

**Key rule:** Keep `SKILL.md` under 500 lines. When a skill needs more content, move detailed reference material to `references/` and tell the agent *when* to load each file:

```markdown
Read `references/api-errors.md` if the API returns a non-200 status code.
```

### When to Use Each Directory

| Directory | Use when... | Example |
|-----------|-------------|---------|
| `assets/` | The skill needs templates or files the agent copies into the target repo | TODO.md template, report template |
| `references/` | Detailed docs only needed in specific scenarios | API error codes, schema definitions |
| `scripts/` | The agent repeatedly reinvents the same logic across test cases | Data parser, chart builder, validator |

*Source: [agentskills.io specification](https://agentskills.io/specification), [best-practices](https://agentskills.io/skill-creation/best-practices.md)*

---

## 4. Writing Guidelines

### Start from Real Expertise

Effective skills are grounded in real expertise, not generic LLM knowledge. Extract from:

- **Hands-on tasks:** Steps that worked, corrections you made, input/output formats observed
- **Existing artifacts:** Internal docs, runbooks, API specs, code review comments, real failure cases

### Add What the Agent Lacks, Omit What It Knows

Focus on project-specific conventions, domain-specific procedures, and non-obvious edge cases. Don't explain what a PDF is or how HTTP works.

```markdown
<!-- BAD: explains what the agent already knows -->
## Extract PDF text
PDF files are a common format that contains text and images...

<!-- GOOD: jumps straight to what the agent wouldn't know -->
## Extract PDF text
Use pdfplumber for text extraction. For scanned documents, fall back to
pdf2image with pytesseract.
```

### Calibrate Control

Match instruction specificity to task fragility:

| Task type | Approach | Example |
|-----------|----------|---------|
| Flexible (multiple valid approaches) | Explain *why*, give freedom | "Check all DB queries for SQL injection — use parameterized queries" |
| Fragile (specific sequence required) | Be prescriptive | "Run exactly this command. Do not modify flags." |

### Provide Defaults, Not Menus

Pick a default approach and mention alternatives briefly:

```markdown
<!-- BAD: too many equal options -->
You can use pypdf, pdfplumber, PyMuPDF, or pdf2image...

<!-- GOOD: clear default with escape hatch -->
Use pdfplumber for text extraction. For scanned PDFs requiring OCR, use pdf2image with pytesseract instead.
```

### Gotchas Sections

The highest-value content in many skills. Concrete corrections to mistakes the agent will make without being told:

```markdown
## Gotchas

- The `users` table uses soft deletes. Queries must include
  `WHERE deleted_at IS NULL` or results will include deactivated accounts.
- The user ID is `user_id` in the database, `uid` in the auth service,
  and `accountId` in the billing API. All three refer to the same value.
```

Keep gotchas in `SKILL.md` where the agent reads them before encountering the situation.

### Templates for Output Format

When specific output format is required, provide a template. Agents pattern-match well against concrete structures:

```markdown
## Report structure

Use this template, adapting sections as needed:

# [Analysis Title]
## Executive summary
[One-paragraph overview]
## Key findings
- Finding 1 with data
## Recommendations
1. Specific action
```

Short templates live inline in `SKILL.md`; longer ones go in `assets/` and are referenced from the skill body.

### Validation Loops

Instruct the agent to validate its own work:

```markdown
1. Make your edits
2. Run validation: `python scripts/validate.py output/`
3. If validation fails, fix issues and run again
4. Only proceed when validation passes
```

*Source: [agentskills.io best-practices](https://agentskills.io/skill-creation/best-practices.md)*

---

## 5. Scripts Standards

### One-off Commands

When an existing package does what you need, reference it directly in `SKILL.md`:

```bash
npx eslint@9 --fix .
uvx ruff@0.8.0 check .
```

Pin versions for reproducibility. State prerequisites in the skill body.

### Self-contained Scripts

When reusable logic is needed, bundle scripts in `scripts/` with inline dependency declarations:

**Python (PEP 723):**
```python
# /// script
# dependencies = ["beautifulsoup4>=4.12,<5"]
# requires-python = ">=3.11"
# ///
from bs4 import BeautifulSoup
```
Run with: `uv run scripts/extract.py`

### Agentic Script Design

Scripts that agents run must follow these rules:

| Rule | Why | Example |
|------|-----|---------|
| **No interactive prompts** | Agents run in non-interactive shells | Accept input via CLI flags, env vars, or stdin |
| **Document with `--help`** | Agents learn the interface from help output | Include description, flags, examples |
| **Helpful error messages** | Error messages shape the agent's next attempt | Say what went wrong, what was expected, what to try |
| **Structured output** | Agents and tools parse stdout | Use JSON/CSV over free-form text |
| **Separate data from diagnostics** | Agents need clean parseable output | Structured data to stdout, progress to stderr |
| **Idempotency** | Agents may retry commands | "Create if not exists" over "create and fail" |
| **Meaningful exit codes** | Agents branch on exit status | Distinct codes for different failure types |
| **Predictable output size** | Tool output may be truncated | Default to summary, support `--offset` for pagination |

*Source: [agentskills.io using-scripts](https://agentskills.io/skill-creation/using-scripts.md)*

---

## 6. Evaluation Standards

### Test Case Design

Store test cases in `evals/evals.json`:

```json
{
  "skill_name": "todo-manager",
  "evals": [
    {
      "id": 1,
      "prompt": "Add a new TODO item for implementing dark mode support",
      "expected_output": "A new TODO-XXXX entry added to the High Priority section with auto-assigned ID",
      "files": []
    }
  ]
}
```

**Tips:**
- Start with 2-3 test cases, expand later
- Vary phrasing, detail level, formality
- Cover edge cases (malformed input, ambiguous requests)
- Use realistic context (file paths, specific details)

### Assertions

Add verifiable checks after seeing first-round outputs:

```json
"assertions": [
  "The output file contains a TODO entry with a sequential ID",
  "The new ID is exactly one higher than the previous highest ID",
  "The entry uses em-dash (—) between title and description"
]
```

Good assertions are programmatically verifiable, specific, and countable. Avoid vague assertions like "the output is good."

### Grading

Evaluate each assertion against outputs, recording PASS/FAIL with evidence:

```json
{
  "assertion_results": [
    {
      "text": "The output file contains a TODO entry with a sequential ID",
      "passed": true,
      "evidence": "Found TODO-0038 in docs/todo/TODO.md, previous highest was TODO-0037"
    }
  ]
}
```

### Iteration Loop

1. Give eval signals + current SKILL.md to an LLM, ask for improvements
2. Review and apply changes
3. Rerun all test cases in a new `iteration-N/` directory
4. Grade, aggregate, review with human
5. Repeat until satisfied

*Source: [agentskills.io evaluating-skills](https://agentskills.io/skill-creation/evaluating-skills.md)*

---

## 7. Quality Gates

Before adding a new skill to this repo, verify all items below:

### Pre-commit Checklist

- [ ] `SKILL.md` exists and has valid YAML frontmatter
- [ ] `name` is kebab-case and matches the directory name
- [ ] `metadata.version` is present and starts at `"1.0.0"` (or bumped appropriately for updates)
- [ ] `description` is under 1024 characters
- [ ] `description` uses imperative phrasing and lists trigger contexts
- [ ] `SKILL.md` body is under 500 lines (use `references/` for detail beyond this)
- [ ] No hardcoded repo-specific paths, project names, or domain conventions (unless the skill is intentionally repo-specific)
- [ ] Gotchas section exists for non-obvious pitfalls
- [ ] Each operation/section has validation guidance
- [ ] Bundled scripts (if any) follow [Scripts Standards](#5-scripts-standards)
- [ ] Templates (if any) in `assets/` are usable without modification
- [ ] No interactive prompts in any bundled scripts
- [ ] Existing skills in the repo are unchanged

### Quick Validation Commands

```bash
# Check frontmatter validity (requires yq or similar)
yq eval '.name' SKILL.md
yq eval '.metadata.version' SKILL.md

# Check description length
python -c "
import yaml, sys
with open('SKILL.md') as f:
    fm = yaml.safe_load(f)
    desc = fm.get('description', '')
    print(f'Description: {len(desc)} chars (limit: 1024)')
    sys.exit(0 if len(desc) <= 1024 else 1)
"

# Check SKILL.md line count
wc -l SKILL.md

# Search for repo-specific leaks (adapt patterns to your repo)
grep -ri 'mini-diarium\|diary\|diarium' SKILL.md
```

---

## 8. Versioning

All skills use semantic versioning in the standard frontmatter `metadata.version` field. Keep version inside
`metadata`; the Agent Skills reference validator rejects a non-standard top-level `version` field.

### When to Bump

| Change | Bump | Example |
|--------|------|---------|
| Breaking change to skill interface (renamed operations, removed sections, changed output format) | Major | `1.x.x` → `2.0.0` |
| New capability, new operation, new bundled resource | Minor | `1.0.x` → `1.1.0` |
| Bug fix, typo correction, description optimization, gotcha addition | Patch | `1.0.0` → `1.0.1` |

### Initial Version

New skills start at `1.0.0`. Do not use `0.x.y` — skills in this repo are expected to be production-ready from the start.
