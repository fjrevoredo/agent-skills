---
name: device-index
description: |
  Build or refresh a device index: a short, always-loaded file of facts about this machine (paths,
  toolchains, shells, containers, clusters, services, apps, agents) plus topic files read on demand,
  and wire Claude Code, pi and OpenCode to load it. Explores the machine read-only, interviews the
  user for what only they know, and writes only after approval. Use it when the user wants their
  coding agents to know this machine, sets up a new laptop for agents, asks to create, update or
  check a device index or ~/.device, wants agents to know where repos and toolchains live or which
  cluster contexts are prod, or when agents keep failing on machine facts (wrong JDK, JAVA_HOME
  empty in agent shells, Docker socket not found). Machine-wide and user-level; a single repo's
  AGENTS.md or CLAUDE.md belongs to that repo.
  Triggers: device index, machine index, ~/.device, tell agents about my machine, new laptop for
  agents, stale device index, agent shell env, wire index into CLAUDE.md, AGENTS.md or
  opencode.json.
compatibility: |
  Claude Code, pi, OpenCode. probe.sh needs bash 3.2+ on macOS or Linux; jq optional.
metadata:
  version: "1.0.0"
---

# Device index

A **device index** is a set of Markdown files that tell every coding agent on a machine what is
where: paths, toolchains, shells, containers, clusters, services, apps and agents. One short
`INDEX.md` is loaded into every session; topic files (`toolchains.md`, `paths.md`, …) sit behind a
"read when" pointer in it. Default home: `~/.device/`.

Two ideas decide every line you write:

- **Facts, not rules.** The index says what is true ("`prod` contexts: A, B"). How an agent must
  act ("never `kubectl apply` on prod") belongs in each agent's own instruction file. When the user
  states a rule, put it on the *proposed rules* list for step 5.
- **Cache only the expensive lookup.** The machine is the source of truth; the index is a cache.
  Point to the lookup (`brew leaves`, `kubectl config get-contexts`) instead of copying its output.
  Record what no command shows: the non-default location, the agent-shell gap, the trap someone
  already fell into, which of two installed tools is the canonical one, and why.

## Workflow

Paths below are relative to this skill's folder.

### 0. Pick the mode

Look for `~/.device/` and for index pointers in the global instruction files
(`~/.claude/CLAUDE.md`, `~/.pi/agent/AGENTS.md`, `~/.config/opencode/AGENTS.md`,
`~/.config/opencode/opencode.json` → `instructions`). `scripts/probe.sh --section index` shows all
of them. An index lives elsewhere when a pointer names another path; use that path.

- **Create mode:** no index. Run every step.
- **Update mode:** an index exists. Read all its files first. Run `scripts/probe.sh` and
  `scripts/probe.sh --check-index <file>` for each index file. In step 2, interview only on
  differences between probe and index, stale lines, and sections the index lacks. In step 3,
  draft edits to the existing files rather than new files.

Done when the mode is stated to the user, with the index path in update mode.

### 1. Explore (read-only)

Run `bash scripts/probe.sh` (about 20–30 s; `--help` lists flags). It prints `## <section>`
blocks of `key: value` lines. Then read `references/exploration.md` and run the follow-up probes
for what the output shows.

Keep two lists as you go:

- **Draft facts**, each tagged with its section and evidence (command or file).
- **Open questions**: what a probe can't settle (which context is prod, which shell the terminal
  starts, which of two version managers is canonical).

Done when every probe section has at least one draft fact, an open question, or "nothing found".

### 2. Pair with the user

Read `references/interview.md` and walk it section by section. Each round: show what you found,
ask the user to confirm or correct it, then ask what only they know. At most 4 questions per round,
recommended answer first. Use the agent's question tool when it has one (Claude Code:
`AskUserQuestion`; OpenCode: `question`); otherwise ask numbered questions in chat.

Rules the user states ("agents must never…", "always use…") go on the proposed rules list, not
into the index.

Done when every section of the templates in `assets/` is filled from evidence or confirmed by the
user, or the user marked it N/A.

### 3. Draft

Copy the templates into a scratch folder (the agent's scratchpad, else `$TMPDIR/device-index/`)
and fill them:

- `assets/INDEX-template.md` → `INDEX.md`, always. About one screen; every topic file is named in
  its header with a "read when" condition.
- `assets/toolchains-template.md` → `toolchains.md`, when any stack needs activation steps or has
  gotchas (almost always).
- `assets/paths-template.md` → `paths.md`, only when the user has many repos with a grouping that
  folder names don't show.
- A further topic file only for a large topic the user names (for example a cluster map).

Show the drafts in full. Iterate until the user approves them.

Before showing, check each draft line: a fact, not a rule; not a copy of a cheap lookup; no secret
value; every backticked path exists (`scripts/probe.sh --check-index <draft>`; a path the text
says is absent on purpose is fine).

Done when the user explicitly approves the drafts.

### 4. Write

Ask where the source of truth lives:

- `~/.device/` as a plain folder (default), or
- a synced or versioned folder (cloud drive, dotfiles repo) with `~/.device` symlinked to it, so
  the index survives a machine swap and is editable from elsewhere.

Back up any file you replace (`<file>.bak-YYYYMMDD`), then write. When `~/.device` is a symlink,
write through it; the target is what changes.

Done when `scripts/probe.sh --check-index` on each written file reports no `missing:` line except
paths the text names as absent on purpose, and the user has seen the written paths.

### 5. Wire

Read `references/wiring.md`. For each installed agent (probe section `agents`), show the exact
change to its global instruction file or config:

1. the index pointer (import, "read" line or `instructions` entry),
2. the trigger line "read `~/.device/toolchains.md` before you build, test, run or install
   anything" (one per topic file, each with its own "read when"),
3. the proposed rules from step 2, worded as rules.

Merge into existing files: keep every existing line and config key. Apply each agent's change only
after the user approves that change.

Done when every installed agent is wired or the user declined it.

### 6. Verify

For each wired agent, run the headless check from `references/wiring.md`: ask a question only the
index answers (for example "where is the JDK manager installed?") from a neutral folder, and
compare the answer with the index. Show the answers to the user.

Done when each wired agent answers correctly, or the failure is reported with its output.

At the end, list what the user still has to do (an agent you could not verify, an open question
they deferred) and offer to note it wherever they track to-dos.

## What goes where

| Content | Home |
|---|---|
| Facts every session may need: machine, roots for new work, shells, one line per stack, apps, services, agents | `INDEX.md` |
| Activation commands, agent-shell gaps, per-stack traps | `toolchains.md` |
| Repo groupings, root → group map | `paths.md` |
| How agents must act (approvals, prod limits, which CLI to use) | agent instruction files (step 5) |
| Secret values, tokens, passwords | nowhere; record only where secrets live |
| Full package or app lists | nowhere; record the command that lists them |

## Gotchas

- **Agent shells skip the interactive rc files.** Agents run commands in non-interactive,
  non-login shells, so exports and functions from `.zshrc` / `.bashrc` / `.zprofile` (`JAVA_HOME`,
  `NVM_DIR`, `DOCKER_HOST`, `sdk`, `nvm`) are missing there. The `envgap` probe lists the names.
  For each one a tool needs, record the activation command in `toolchains.md`.
- **Secrets stay where they are.** Record "SSH keys: 1Password agent", never a key, token or
  password; also no values from `.env`, `auth.json`, keychains, or rc files.
- **Name prod contexts explicitly.** List every production cluster context and cloud project by
  name, including ones whose name lacks `prod`, and say which context is safe for local throwaway
  work. Record that the current context is shared global state.
- **Ambient versions differ from project pins.** The `java` / `node` / `python3` on PATH is often
  not what repos pin (`.sdkmanrc`, `.nvmrc`, `.python-version`, `.tool-versions`). Record both and
  where pins live.
- **Non-default install locations are the expensive facts.** A version manager installed through
  a package manager (SDKMAN via Homebrew, nvm via a formula) lives outside its documented default,
  and init scripts silently fall back to the default path. Record the real path and the trap.
- **`INDEX.md` stays short.** It is loaded every turn in every session. Detail goes to a topic file
  behind a "read when" pointer in the index header.
- **Edit through the symlink.** When `~/.device` or a file in it links into a synced folder, read
  and write the link path; replacing the link with a plain file breaks the sync.
- **OpenCode ignores `@file` imports**, and an existing `~/.config/opencode/AGENTS.md` turns off its
  fallback to `~/.claude/CLAUDE.md` (documented for v1). Wire OpenCode on its own; never assume it
  inherits the Claude Code wiring.
- **`probe.sh --check-index` reports every missing backticked path**, including ones the index
  names as absent on purpose ("not `~/.sdkman`"). Judge each `missing:` line before calling it stale.
- **Windows is out of scope.** On WSL, run the probe inside the Linux side and ask the user about
  the Windows host.
