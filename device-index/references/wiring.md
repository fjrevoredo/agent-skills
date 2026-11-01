# Wiring

How each agent loads the index, the exact change to propose, and the checks. One row per agent
(the adapter table). Show each change as a diff or a full new file, and apply it only after the
user approves it. To support a new agent, add one row here; the workflow does not change.

## Adapter table

| | Claude Code | OpenCode | pi |
|---|---|---|---|
| Detect | `claude` on PATH or `~/.claude/` | `opencode` on PATH or `~/.config/opencode/` | `pi` on PATH or `~/.pi/agent/` |
| File this skill writes | `~/.claude/rules/device-index.md` (whole file, owned by this skill) | `instructions` entry in `~/.config/opencode/opencode.json(c)`; topic and rule lines in `~/.config/opencode/AGENTS.md` | `~/.pi/agent/AGENTS.md`, or the local overlay a generator names (for example `AGENTS.local.md`) |
| Pointer form | `@~/.device/INDEX.md` on its own line (an import) | `"~/.device/INDEX.md"` in `instructions` | `- Read \`~/.device/INDEX.md\` at the start of each session.` |
| Load check | `/memory` in an interactive session lists the rules file and the imported index | `opencode debug config` shows the entry in `instructions` | — |
| Headless check | `claude -p "<q>"` | `opencode run "<q>"` | `pi -p "<q>"` |
| Skill dir | `~/.claude/skills/` | `~/.config/opencode/skills/`, `~/.claude/skills/`, `~/.agents/skills/` | `~/.agents/skills/` (auto), `~/.pi/agent/skills/` |
| Agent shell on Windows | Bash tool: Git Bash (when Git for Windows is installed); PowerShell tool may also exist | Windows PowerShell 5.1 (observed on v2) | — |

Check versions before you rely on a row: `claude --version`, `opencode --version`, `pi --version`.
The rows were verified on Claude Code 2.1 and OpenCode v2.2 (Windows 11).

Later rows, not verified: **Codex** (`~/.codex/AGENTS.md`, or `$CODEX_HOME/AGENTS.md`), **Zed**
(`~/.config/zed/AGENTS.md`). There is no standard global AGENTS.md path; each agent has its own.
Verify a new row with its headless check before you rely on it.

## The block

The same parts for every agent; only the pointer differs. Replace `<index>` with the real path
(default `~/.device`).

```markdown
# This machine: device index

<pointer, see the adapter table>
- Read `<index>/toolchains.md` before you build, test, run or install anything.
- <one "read <topic>.md when …" line per further topic file>
- The device index holds facts. The rules for how to act are in the instruction files.

<proposed rules from the interview>
```

## Claude Code

Write `~/.claude/rules/device-index.md` with the block above, pointer `@<index>/INDEX.md`.

- **A real file, not a symlink.** A link in `.claude/rules/` that points outside the working
  directory counts as an external import and needs approval in each project.
- **No `paths` frontmatter**, so the file loads in every project. Files in the user-level
  `~/.claude/rules/` load in every session, and their imports load without an approval dialog.
- `@~/...` imports work in a rules file, also on Windows. Imports nest at most four hops. A path
  with spaces needs a backslash before each space; a quoted path is not imported.
- An older install put the block into `~/.claude/CLAUDE.md`. Move it to the rules file and remove
  it from `CLAUDE.md`, so it loads once. Keep every other line of `CLAUDE.md`.

## OpenCode

Add the index to `instructions` and keep every other key (`$schema`, `plugin`, `mcp`, …):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["…existing…"],
  "instructions": ["~/.device/INDEX.md"]
}
```

- `~/` works in `instructions` (verified on v2.2.5, also on Windows). An absolute path works too;
  on Windows use forward slashes (`C:/Users/<user>/.device/INDEX.md`). Prefer `~/`: the same line
  works on every machine.
- `instructions` entries are **combined** with AGENTS.md. Global AGENTS.md files are
  **first-match**: when `OPENCODE_CONFIG_DIR` points to a profile (for example an OCX profile) with
  its own AGENTS.md, OpenCode reads that file and skips `~/.config/opencode/AGENTS.md` without a
  warning. So put the pointer in `instructions`, and check `profiles/*/AGENTS.md`.
- The global `~/.config/opencode/AGENTS.md` loads on v2 when no profile hides it. When present,
  OpenCode does not fall back to `~/.claude/CLAUDE.md` (documented for v1). Either way it ignores `@file` imports.
- `opencode.jsonc` with comments: edit by hand and keep the comments. `jq` drops them.
- Put the topic-file lines and rules in `~/.config/opencode/AGENTS.md`, or in an own file that
  you also list in `instructions` (one file per tool is easier to remove later).

Test `instructions` without touching the user's config. `OPENCODE_CONFIG` is **ignored** by v2;
use a project config in a temp folder instead (OpenCode reads `opencode.json` from the cwd):

```bash
dir="$(mktemp -d)"; printf 'The codeword is PELICAN-42.\n' > "$dir/probe.md"
printf '{"instructions":["%s"]}\n' "$dir/probe.md" > "$dir/opencode.json"
(cd "$dir" && opencode run "What is the codeword? Answer with it only.")
```

On Windows, write the path in the JSON with forward slashes (`cygpath -m` in Git Bash).

Without a working model or API key: `opencode debug config` prints the resolved config (look for
`instructions`). It proves the config resolves, not that the model sees the file; report it as
such. v2.2.5 has no debug command that lists skills; to check skills, ask a headless question from
a temp folder: `opencode run "List only the names of the skills you can load."`

## pi

pi follows no imports. Add the block with the "read" pointer line. When `~/.pi/agent/AGENTS.md`
says it is generated ("edit AGENTS.base.md and AGENTS.local.md, then rerun the bootstrap"), write
the block into the overlay it names and ask the user to rerun the generator; a direct edit is lost
on the next run.

## Merge rules

- Prefer a whole file this skill owns (Claude Code rules file, an `instructions` file). Then
  install, check and uninstall are file operations, and the user's own file is not touched.
- Otherwise read the whole target file first; propose an insertion, not a rewrite.
- An existing device-index block → replace that block only. The index must load **once** per
  agent: never both a rules file and a block in `CLAUDE.md`.
- A rule that already exists in the file → keep the user's wording; add nothing.
- Back up before writing: `cp <file> <file>.bak-YYYYMMDD`.
- A file that is a link (dotfiles, synced folder) → write through the link. Exception: the
  Claude Code rules file (see above).

## Skill install (optional)

When the user wants this skill on several agents: put it (or a link to it) in
`~/.agents/skills/device-index`, and add `~/.claude/skills/device-index` → that folder (on Windows,
a junction: `New-Item -ItemType Junction`). pi and OpenCode find `~/.agents/skills`; one more pi
`settings.json` skill path to the same skill makes pi warn about a name collision.

## Headless check

Ask each wired agent a question only the index answers, from a neutral folder so no project
instructions interfere. Pick a fact the agent can't guess: a non-default install path, the repo
root for new work, the binary agents must call.

```bash
cd "$(mktemp -d)"
q='Answer from your loaded instructions only, without running tools: where is <fact>?'
claude -p "$q"
opencode run "$q"
pi -p "$q"
```

PowerShell: `Set-Location (New-Item -ItemType Directory (Join-Path $env:TEMP "di-$(Get-Random)"))`,
then the same commands.

A correct answer means the index loads. A wrong or "I don't know" answer → check the pointer, the
file path, and the agent version, then report the output to the user.
