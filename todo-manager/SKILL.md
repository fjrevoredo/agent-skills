---
name: todo-manager
version: 1.0.0
description: |
  End-to-end management of TODO items in a Markdown-based backlog. Covers creation with auto-assigned IDs,
  status tracking, archival of completed items, and format validation. Use this skill whenever the user asks to
  add a new TODO, check TODO status, archive completed items, validate the TODO system, or set up a new TODO
  backlog from scratch. Also use when the user mentions a task list, backlog, roadmap, or task tracking in a
  Markdown file — even if they don't explicitly say "TODO". If the repo has a `TODO.md` file or similar
  Markdown-based task tracking, this skill should be used to interact with it.
  Triggers: TODO, todo item, add todo, create todo, todo status, archive todo, validate TODO,
  TODO ID, TODO-0001, check TODO, todos, list todos, todo list, backlog, task tracking, roadmap, task list.
---

# TODO Manager Skill

Manages the full lifecycle of TODO items in a Markdown-based backlog system.

## Configurable Paths

These paths are defaults and can be overridden by the consuming repo or agent context:

| Field | Default | Role |
|-------|---------|------|
| `todo_path` | `docs/todo/TODO.md` | Active backlog — the working TODO file |
| `archive_path` | `docs/todo/TODO_ARCHIVE.md` | Completed items archive |
| `extra_path` | `docs/todo/TODO_EXTRA.md` | Implementation detail linked to parent TODOs |

## Bundled Templates

When a repo does not yet have a TODO system, use the templates in `assets/` to bootstrap it:

| Template | Purpose |
|----------|---------|
| `assets/TODO.md` | Active backlog with priority sections, format rules, and ID tracker |
| `assets/TODO_ARCHIVE.md` | Empty archive with `## Completed` heading ready for prepended items |
| `assets/TODO_EXTRA.md` | Implementation notes file with example section showing the `TODO-XXXX-YY` format |

Copy the templates to the paths defined in **Configurable Paths** (or the repo's chosen locations) before performing any operations.

## Quick Reference

| Operation | Purpose |
|-----------|---------|
| **Create** | Add a new TODO item with auto-assigned `TODO-XXXX` ID |
| **Track** | Report status: open/closed counts, stale items, ID health |
| **Archive** | Move completed items to the archive file |
| **Validate** | Check ID uniqueness, sequential order, format correctness |

## Format Rules

These rules keep the TODO file machine-parsable and human-readable. The sequential ID system lets any agent find the next ID without a central registry, and the strict format ensures regex-based tools can reliably extract, count, and validate entries.

- Top-level items: `- [ ] **TODO-XXXX: Title** — description`
- Indented sub-items: `  - [ ] **Title** — description` (free-form, **no ID**)
- IDs are 4-digit zero-padded sequential: `TODO-0001`, `TODO-0002`, ...
- Extra detail file items: `## TODO-XXXX-YY: Title` linking back to parent `TODO-XXXX`
- Completed items in the active file: `- [x] **TODO-XXXX: Title** — description`
- When archived: `- [x] **TODO-XXXX: Title** (YYYY-MM-DD) — description`
- IDs are **never reused** — always scan for the highest existing ID and increment

---

## Operation 1: Create a New TODO

Add a brand-new TODO item to the correct priority section with an auto-assigned ID.

### Pre-condition Check

If the active TODO file does not exist, bootstrap it first: copy `assets/TODO.md` to the configured `todo_path` and set `Latest TODO ID: TODO-0000` so the first item becomes `TODO-0001`.

### Step-by-Step

1. **Read** the active TODO file.
2. **Scan** for the highest existing `TODO-XXXX` ID — the new ID is that number + 1, zero-padded to 4 digits.
3. **Format** the new item: `- [ ] **TODO-XXXX: Title** — description` (use em-dash `—` between title and description).
4. **Insert** into the appropriate priority section, maintaining logical order within the section.
5. **Do NOT** add IDs to new indented sub-items — they stay as `- [ ] **Title** — description`.
6. **Update** any plan milestone or status marker if this TODO references a plan file.

### Example

```
- [ ] **TODO-0020: New feature** — brief description of what must be true
```

### Validation

- Search the active file for `TODO-\d{4}` — the new ID should appear exactly once.
- No duplicate IDs exist.
- The item is in the correct priority section.

---

## Operation 2: Track TODO Status

Report on the state of the TODO backlog.

### Step-by-Step

1. Read the active TODO file.
2. Count items by section and status (`[ ]` vs `[x]`).
3. Identify stale items — completed `[x]` items that have been sitting without archival (more than a few days) should be flagged for archival.
4. Check that the extra detail file's parent IDs all reference valid `TODO-XXXX` entries in the active file.
5. Report any `TODO-XXXX-YY` IDs in the extra detail file whose parent `TODO-XXXX` doesn't exist.

### Validation

Report format:

```
High: 0 open, 1 completed
Medium: 7 open, 2 completed
Website: 1 open
Low: 8 open
---
Total: 16 open, 3 completed
Orphaned extra items: (none / list)
```

---

## Operation 3: Archive Completed Items

Move completed `[x]` items from the active TODO file to the archive file. Keeping the active file focused on open work makes the backlog easier to scan and prevents completed items from burying current priorities.

### Pre-condition Check

If the archive file does not exist, create it from `assets/TODO_ARCHIVE.md` at the configured `archive_path`.

### Step-by-Step

1. Read the active TODO file.
2. Find all top-level `- [x]` items and their indented sub-items.
3. For each completed top-level item:
   - Insert today's date (ISO format `YYYY-MM-DD`) between the closing `**` and the ` — `: `- [x] **TODO-XXXX: Title** (2026-05-07) — description`.
   - Keep indented sub-items verbatim below their parent.
4. **Prepend** the transformed block to the archive file after the `## Completed` heading.
5. **Remove** the completed lines from the active TODO file. Collapse consecutive blank lines to at most one.
6. If no completed items exist, note this and stop.

### Compatibility Note

This operation may complement a release workflow skill that also archives completed items during release preparation. This skill can be used standalone between releases for single-item archival.

### Validation

- Completed items are no longer in the active TODO file.
- They appear at the top of the archive file under `## Completed`.
- Dates are inserted in the correct position (between `**...**` and ` — `).

---

## Operation 4: Validate the TODO System

Run a full consistency check on the TODO files. These checks catch format drift that accumulates over time — duplicate IDs break the "next ID" logic, gaps suggest deleted items, and orphaned extra-file sections reference work that no longer exists.

### Step-by-Step

1. **ID uniqueness**: Extract all `TODO-\d{4}` patterns from the active file and verify each appears exactly once.
2. **ID sequence**: IDs should be sequential from the first ID to the highest, with no gaps.
3. **No IDs on sub-items**: Indented `- [` lines must NOT contain a `TODO-` pattern.
4. **Extra file parent validity**: Every `TODO-XXXX-YY` in the extra detail file must have a parent `TODO-XXXX` that exists in the active file.
5. **No stale `[x]` without archive date**: Items marked `[x]` in the active file that haven't been archived are valid but should be flagged.
6. **Format consistency**: All top-level items follow `- [ ] **TODO-XXXX: Title** — description` or `- [x] **TODO-XXXX: Title** — description`.

### Validation Commands (adapt to local toolchain)

- Count TODO items: search for `\*\*TODO-\d{4}:` in the active file.
- Check uniqueness: extract all `TODO-\d{4}` patterns, sort, and verify count matches unique count.
- Check for IDs on sub-items: search for indented `- [` lines containing `TODO-` — should return zero matches.
- Check extra file parent IDs: extract parent IDs from the extra file and verify each exists in the active file.

---

## Key Files Reference

| File | Role |
|------|------|
| Active TODO file (see `todo_path`) | Active backlog — the working TODO file |
| Archive file (see `archive_path`) | Completed items archive |
| Extra detail file (see `extra_path`) | Implementation detail linked to parent TODOs |
| This skill file | Skill definition |

## Common Pitfalls

1. **ID reuse** — Never reassign a previously used ID. Reusing an ID creates ambiguity when reading archive history or cross-referencing the extra detail file. Always scan for the highest existing `TODO-XXXX` and add 1.
2. **Sub-items getting IDs** — Indented items under a parent TODO are free-form implementation notes, not independently trackable tasks. Giving them IDs breaks the sequential numbering and confuses the "next ID" logic.
3. **Wrong priority section** — Insert new items under the correct priority heading so the backlog stays scannable. If no priority sections exist, add them (High, Medium, Low) before inserting.
4. **Missing em-dash** — Use ` — ` (em-dash with surrounding spaces) between title and description, not ` - ` (hyphen). The em-dash is the delimiter that separates the title from the description in the format contract.
5. **Archive date position** — Date goes between `**...**` and ` — `: `**TODO-0001: Title** (2026-05-07) — description`. Putting it elsewhere breaks regex-based date extraction.
6. **Forgetting to remove from active file after archive** — Archiving is a *move*, not a copy. Leaving completed items in the active file inflates the backlog and makes tracking "open vs closed" counts inaccurate.
7. **Extra file parent drift** — When a TODO ID changes (should be rare), update all `TODO-XXXX-YY` references in the extra detail file. Orphaned sections become dead documentation that no agent can trace back to its parent task.
