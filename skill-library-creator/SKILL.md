---
name: skill-library-creator
description: |
  Create or maintain a skill library that groups two or more related, low-frequency Agent Skills behind one
  discoverable dispatcher. Use when the user wants to consolidate skills, reduce the active skill catalog,
  group manual runbooks, or keep exceptional workflows available without loading every skill description.
  Also use when deciding which skills should remain standalone versus move into a library.
  Triggers: skill library, skill of skills, meta-skill, consolidate skills, group skills, runbooks library,
  reduce active skills, skill catalog pollution, nested skills, skill dispatcher.
metadata:
  version: "1.0.0"
---

# Skill Library Creator

Create one discoverable dispatcher that loads complete inner skills only when needed.

## Before Creating a Library

Read:

- every candidate skill's `SKILL.md` and directly referenced resources;
- the target repository's skill rules and agent instructions;
- the current [Agent Skills specification](https://agentskills.io/specification) and
  [best practices](https://agentskills.io/skill-creation/best-practices).

Use a library only when:

- at least two skills share a clear user-facing domain;
- they are manual, rare, or exceptional workflows;
- each can run independently after being selected.

Keep common, foundational, or broadly automatic skills standalone. Split unrelated candidates instead of
creating a miscellaneous library.

If the user provides no name, derive the shared scope and use `<scope>-library`.

## Required Layout

```text
<library-name>/
├── SKILL.md
└── skills/
    ├── <entry-one>/
    │   ├── ENTRY.md
    │   └── ... existing resources
    └── <entry-two>/
        ├── ENTRY.md
        └── ... existing resources
```

Move or copy each complete skill directory so its relative `scripts/`, `references/`, and `assets/` paths
continue to work.

## Workflow

1. **Choose the boundary.** Classify candidates as included, standalone, or belonging in another library.
   Summarize the library's shared scope in one sentence.
2. **Verify reachability.** Inspect how the target client discovers and explicitly activates skills.
   - The library must be discoverable.
   - Nested entries must not remain separately registered.
   - Name nested library entrypoints `ENTRY.md`, not `SKILL.md`, to prevent automatic discovery or
     registration by harnesses such as Codex.
   - Check generated mirrors, symlinks, user-level copies, plugins, and skill-sync scripts too.
3. **Validate entries.** Preserve each inner workflow as a complete reusable bundle. Keep the original
   standalone skill valid until cutover and verify that the nested bundle still contains the expected
   instructions, scripts, assets, and references.
4. **Create the dispatcher.** Write the library `SKILL.md` using the template below. Its description should
   describe the shared domain, not enumerate every entry.
5. **Migrate entries.** Place complete skill directories under `skills/`. Keep originals registered until the
   new library passes validation.
6. **Test routing.**
   - Explicitly activate the library using the target client's supported syntax and name one entry.
   - Try a natural request matching one entry.
   - Try an unknown request and confirm the dispatcher does not invent an entry.
   - Run one representative validation from every migrated skill.
7. **Cut over.** Remove or exclude the original standalone registrations and stale mirrors. The nested copy
   becomes canonical.
8. **Confirm the result.** Inspect the client's final available-skills catalog and verify that only the
   dispatcher is registered.

Do not advertise `<library>:<entry>` as standard syntax. Use it only when the target client or project
instructions explicitly support that shorthand.

## Dispatcher Template

```markdown
---
name: <library-name>
description: <Shared domain and when the library should activate. Mention explicit requests for its entries.>
---

# <Library Title>

## Routing

Match the request to **Available Skills**. Read the selected entry's `ENTRY.md` completely before acting and
resolve relative paths from that entry's directory. Load only the entries required for the current request.
If no entry matches, state that the workflow is not in this library.

Explicit use: activate `<library-name>` with the target client's supported skill invocation, then name the
entry.

## Available Skills

| Skill | Use when | Load |
|-------|----------|------|
| `<entry-one>` | <Short routing description> | `skills/<entry-one>/ENTRY.md` |
| `<entry-two>` | <Short routing description> | `skills/<entry-two>/ENTRY.md` |
```

The table is the library catalog and single source of truth. Do not create a duplicate registry unless the
target client requires one.

## Validation

Run the target repository's checks. When available, also run:

```bash
skills-ref validate <path-to-library>
```

Validate the dispatcher, the preserved bundled resources, the routing behavior, and the final client discovery
result before removing originals.

## Maintenance

When adding or removing an entry:

1. validate the entry independently;
2. update the `Available Skills` table;
3. rerun routing and discovery checks;
4. update mirrors or synchronization rules;
5. bump the version if the repository requires version metadata.

Split the library when its shared description becomes vague or routing becomes ambiguous.

## Gotchas

- A hidden entry is unreachable unless the dispatcher activates, so preserve explicit activation and useful
  domain triggers.
- Recursive client discovery can make every nested `SKILL.md` active and defeat the purpose. Use `ENTRY.md`
  for nested library entries so harnesses like Codex do not auto-register them.
- Copying only `SKILL.md` breaks bundled relative resources.
- Keeping standalone and nested registrations creates duplicate triggers and saves no context.
- A skill library is a composition convention, not a primitive defined by the Agent Skills specification;
  discovery and invocation remain client-specific.

## Completion Report

Report the library scope, included and excluded candidates, generated path, reachability strategy, validation
results, discovery result, and whether original registrations were removed.
