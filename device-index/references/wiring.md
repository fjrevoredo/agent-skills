# Wiring

How each agent loads the index, the exact change to propose, and the headless check. Show each
change as a diff or a full new block, and apply it only after the user approves it.

## Per agent

| | Claude Code | pi | OpenCode |
|---|---|---|---|
| Global instructions | `~/.claude/CLAUDE.md` | `~/.pi/agent/AGENTS.md` (or `CLAUDE.md` there) | `instructions` in `~/.config/opencode/opencode.json(c)`, plus `~/.config/opencode/AGENTS.md` |
| Loads the index by | `@~/.device/INDEX.md` import (followed, loaded at start) | a "read at session start" line (no imports) | an `instructions` entry (files, globs, URLs); `@file` refs are not followed |
| Skill discovery | `~/.claude/skills/` | `~/.agents/skills/` (auto), `~/.pi/agent/skills/`, settings paths | `~/.config/opencode/skills/`, `~/.claude/skills/`, `~/.agents/skills/` |
| Headless check | `claude -p "<q>"` | `pi -p "<q>"` | `opencode run "<q>"` |

Check versions before you rely on a row: `claude --version`, `pi --version`, `opencode --version`.

## The block to add

The same three parts for every agent; only the pointer line differs. Put the block under its own
heading near the top of the file. Replace `<index>` with the real path (default `~/.device`).

```markdown
## This machine: device index

<pointer line, see below>
- Read `<index>/toolchains.md` before you build, test, run or install anything.
- <one "read <topic>.md when …" line per further topic file>
- The device index holds facts. The rules for how to act are in this file.

<proposed rules from the interview, each under the heading it belongs to>
```

Pointer line per agent:

- **Claude Code:** `@<index>/INDEX.md` on a line of its own (an import; `~` works).
- **pi:** `- Read \`<index>/INDEX.md\` at the start of each session.`
- **OpenCode:** the index goes into `instructions` (next section); the AGENTS.md block keeps the
  topic-file lines and the rules.

## OpenCode details

Add the absolute path to `instructions` and keep every other key (`plugin`, `mcp`, `$schema`, …):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["…existing…"],
  "instructions": ["/home/<user>/.device/INDEX.md"]
}
```

- Use an absolute path; `~` expansion in `instructions` is not documented.
- `opencode.jsonc` with comments: edit by hand, keep the comments. `jq` drops them.
- `~/.config/opencode/AGENTS.md` present → OpenCode does not read `~/.claude/CLAUDE.md` as a
  fallback (documented for v1). Absent → it may read the Claude file, whose `@` import it ignores.
  Either way, wire OpenCode explicitly.
- **v2 is unverified:** the v2 docs name `instructions` but not the global AGENTS.md path. On v2,
  check the loading with the headless check and report what you saw.

Test `instructions` without touching the user's config: OpenCode reads a config file from
`OPENCODE_CONFIG`.

```bash
dir="$(mktemp -d)"; printf 'The codeword is PELICAN-42.\n' > "$dir/probe.md"
printf '{"instructions":["%s"]}\n' "$dir/probe.md" > "$dir/opencode.json"
(cd "$dir" && OPENCODE_CONFIG="$dir/opencode.json" opencode run "What is the codeword? Answer with it only.")
```

Without a working model or API key: `opencode debug config` prints the resolved config (look for
`instructions`), and `opencode debug skill` lists the skills OpenCode found. Both prove the config
resolves, not that the model sees the file; report them as such.

## Merge rules

- Read the whole target file first; propose an insertion, not a rewrite.
- An existing device-index block → replace that block only.
- A rule that already exists in the file → keep the user's wording; add nothing.
- Back up before writing: `cp <file> <file>.bak-YYYYMMDD`.
- A file that is a symlink (dotfiles, synced folder) → write through the link.

## Skill install (optional)

When the user wants this skill on all three agents: put it (or a symlink to it) in
`~/.agents/skills/device-index`, and add `~/.claude/skills/device-index` → that folder. pi and
OpenCode find `~/.agents/skills`; one more pi `settings.json` skill path to the same skill makes pi
warn about a name collision.

## Headless check

Ask each wired agent a question only the index answers, from a neutral folder so no project
instructions interfere. Pick a fact the agent can't guess: a non-default install path, the repo
root for new work, the prod context names.

```bash
cd "$(mktemp -d)"
q='Answer from your loaded instructions only, without running tools: where is <fact>?'
claude -p "$q"
pi -p "$q"
opencode run "$q"
```

A correct answer means the index loads. A wrong or "I don't know" answer → check the pointer line,
the file path, and the agent version, then report the output to the user.
