---
name: device-index
description: |
  Build or refresh a device index: a short, always-loaded file of machine facts (paths,
  toolchains, shells, containers, clusters, services, apps, agents) plus topic files read on demand,
  and wire the coding agents the user picks (Claude Code, OpenCode, pi) to load it. Works on macOS,
  Linux and Windows. Explores read-only, interviews the user, and writes only after approval.
  Use it when the user wants coding agents to know this machine, sets up a new
  laptop or PC for agents, asks to create, update or check a device index or ~/.device, or when
  agents keep failing on machine facts (wrong JDK, empty JAVA_HOME in agent shells, wrong ssh
  binary, stale PATH). Not for a single repo's AGENTS.md or CLAUDE.md.
  Triggers: device index, machine index, ~/.device, tell agents about my machine, new laptop for
  agents, stale device index, agent shell env, wire index into Claude Code, OpenCode or pi.
compatibility: |
  Claude Code, OpenCode, pi. probe.sh needs bash 3.2+ on macOS or Linux (jq optional).
  probe.ps1 needs PowerShell 7+ (pwsh) on Windows; Windows PowerShell 5.1 is not supported.
metadata:
  version: "1.1.1"
---

# Device index

A **device index** is a set of Markdown files that tell every coding agent on a machine what is
where: paths, toolchains, shells, containers, clusters, services, apps and agents. One short
`INDEX.md` is loaded into every session; topic files (`toolchains.md`, `paths.md`, …) sit behind a
"read when" pointer in it. Default home: `~/.device/`.

Two ideas decide every line you write:

- **Facts, not rules.** The index says what is true ("`prod` contexts: A, B"). How an agent must
  act ("never `kubectl apply` on prod") belongs in each agent's own instruction file. When the user
  states a rule, put it on the *proposed rules* list for step 5. A rule that must always hold
  (a forbidden command, a wrong binary) can also become a hook (for example a Claude Code
  `PreToolUse` hook): instruction text is context, not enforcement. Name such candidates to the
  user; build a hook only when they ask.
- **Cache only the expensive lookup.** The machine is the source of truth; the index is a cache.
  Point to the lookup (`brew leaves`, `winget list`, `kubectl config get-contexts`) instead of
  copying its output. Record what no command shows: the non-default location, the agent-shell
  gap, the trap someone already fell into, which of two installed tools is the canonical one.

## Prerequisites

- **macOS, Linux, WSL:** `bash scripts/probe.sh`.
- **Windows:** check `pwsh` first (`pwsh -v`, or `Get-Command pwsh`). Missing → stop and ask the
  user to run `winget install Microsoft.PowerShell` and then restart the agent harness (a running
  harness keeps its old PATH). Run the probe as `pwsh -NoProfile -File scripts/probe.ps1`, also
  when the agent's own shell is Git Bash or Windows PowerShell 5.1.

`<probe>` below means the probe for this OS. Flags: `probe.sh --section X --check-index F`;
`probe.ps1 -Section X -CheckIndex F`. Both print the same `## <section>` / `key: value` format.

## Workflow

Paths below are relative to this skill's folder.

### 0. Companion profile and mode

**Companion profile.** A companion knowledge store (a personal or team knowledge base) can own the
durable facts about machines and give this skill a profile. Read the profile before step 1 when:

- the caller (another skill or the user) names a profile file, or
- a global instruction file or rules file names a "device-index companion profile" path.

The profile's rules **add to** "What goes where" and to the interview: read the store's page for
this machine first, skip questions it answers, and **link its fact IDs instead of copying their
claims**. Collect the durable candidates it asks for and show them at the end. No profile → skip
this paragraph.

**Mode.** Look for `~/.device/` and for index pointers in the global instruction files
(`<probe> --section index` lists them: `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md`,
`~/.config/opencode/AGENTS.md`, `instructions` in `~/.config/opencode/opencode.json(c)`,
`~/.pi/agent/AGENTS.md`). An index lives elsewhere when a pointer names another path; use it.

- **Create mode:** no index. Run every step.
- **Update mode:** an index exists. Read all its files first. Run `<probe>` and
  `<probe> --check-index <file>` for each index file. Compare the `INDEX.md` header with the probe:
  `Verified` older than 90 days, or `Host` / `OS` different from `os` → treat every section as
  suspect. In step 2, interview only on differences, stale lines, and missing sections. In step 3,
  draft edits to the existing files rather than new files.

Done when the mode (and the profile, if any) is stated to the user, with the index path in update
mode.

### 1. Explore (read-only)

Run `<probe>` (10–30 s; `--help` / `-Help` lists flags). Then read `references/exploration.md`
and run the follow-up probes for what the output shows.

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

Copy the templates into a scratch folder (the agent's scratchpad, else a temp folder) and fill
them:

- `assets/INDEX-template.md` → `INDEX.md`, always. Header lines `Verified`, `Host`, `OS` (from the
  `os` probe section), every topic file named with a "read when" condition.
- `assets/toolchains-template.md` → `toolchains.md`, when any stack needs activation steps or has
  gotchas (almost always).
- `assets/paths-template.md` → `paths.md`, only when the user has many repos with a grouping that
  folder names don't show (for example the origin host group of each repo).
- A further topic file only for a large topic the user names (a cluster map, peripherals).

Apply the content rules below to every line, then show the drafts in full. Iterate until the
user approves them.

Done when the user explicitly approves the drafts.

### 4. Write

Ask where the source of truth lives:

- `~/.device/` as a plain folder (default), or
- a synced or versioned folder (cloud drive, dotfiles repo) with `~/.device` linked to it, so
  the index survives a machine swap and is editable from elsewhere.

Back up any file you replace (`<file>.bak-YYYYMMDD`), then write. When `~/.device` is a link,
write through it; the target is what changes.

Done when `<probe> --check-index` on each written file reports no `missing:` line, and the user
has seen the written paths.

### 5. Wire

Read `references/wiring.md`. Detect the installed agents (probe section `agents`, and the
"Detect" row of the adapter table). Ask the user **which of them to wire** (multi-select:
`AskUserQuestion` with `multiSelect`, OpenCode `question`, else a numbered list). Wire only the
selected ones. For each, show the exact change:

1. the index pointer (rules file import, "read" line or `instructions` entry),
2. the trigger line "read `~/.device/toolchains.md` before you build, test, run or install
   anything" (one per topic file, each with its own "read when"),
3. the proposed rules from step 2, worded as rules (and the hook candidates, named only).

Where the agent supports it, the pointer is a **whole file this skill owns** (Claude Code:
`~/.claude/rules/device-index.md`), not a block inside the user's file. Otherwise merge into the
existing file: keep every existing line and config key. Apply each change only after the user
approves it.

Done when every selected agent is wired, and each unselected agent is named as "not wired".

### 6. Verify

For each wired agent, run the load check and the headless check from `references/wiring.md`: ask
a question only the index answers (for example "where is the JDK manager installed?") from a
neutral folder, and compare the answer with the index. Show the answers to the user.

Done when each wired agent answers correctly, or the failure is reported with its output.

At the end, list what the user still has to do (an agent you could not verify, an open question
they deferred, the companion profile's durable candidates) and offer to note it wherever they
track to-dos.

## Content rules

Agents follow context files closely; a long or stale file makes their results worse. Apply these
to every draft line:

- **Per-line test.** "Can the agent get this with one cheap command?" Yes → delete the line, or
  keep only the command. Keep facts the agent cannot infer: traps, activation steps, non-standard
  paths, local helpers, which tool is canonical.
- **Line budget.** `INDEX.md` about 60 lines; up to about 75 on a machine with many stacks.
  Detail goes to a topic file. Topic files are never imported into an instruction file; they stay
  behind "read when" lines.
- **Leave out:** tools pinned by a version manager in each repo, tools that are the latest version
  everywhere, facts already in a repo's own files, session data (PID, uptime, load), counts that
  change often, full package or app lists.
- **Machine line:** one short line (model or role, OS, arch). **Applications:** keep only lines that
  change what an agent does ("Agents use the `git` CLI"), not the user's app inventory.
- **Staleness header.** `INDEX.md` starts with `Verified: YYYY-MM-DD`, `Host: <hostname>` and
  `OS: <name version/build>`. Update all three on every refresh.
- **Companion links.** With a companion profile: a fact the store owns appears as a link to its
  fact or page ID, never as a copy of the claim.
- **No secrets, no rules** (see the two ideas above); every backticked path exists
  (`<probe> --check-index <draft>`). Write an example path, or a path that is absent on purpose,
  as plain text without backticks, so the check stays clean.
- **User approval of every draft.** The first draft is machine-written; the user's review is the
  quality gate, not a formality.

## What goes where

| Content | Home |
|---|---|
| Facts every session may need: machine, roots for new work, shells, one line per stack, agents | `INDEX.md` |
| Activation commands, agent-shell gaps, per-stack traps | `toolchains.md` |
| Repo groupings, root → group map | `paths.md` |
| How agents must act (approvals, prod limits, which CLI to use) | agent instruction files (step 5) |
| A rule that must always hold | the agent's hook config, as well as the rule text (user decides) |
| Durable facts a companion store owns (with a profile) | the store; the index links the ID |
| Secret values, tokens, passwords | nowhere; record only where secrets live |
| Full package or app lists | nowhere; record the command that lists them |

## Gotchas

- **Agent shells skip the interactive setup.** On macOS and Linux, agents run commands in
  non-interactive, non-login shells, so exports and functions from `.zshrc` / `.bashrc` /
  `.zprofile` (`JAVA_HOME`, `NVM_DIR`, `sdk`, `nvm`) are missing there. On Windows, agent
  PowerShell tools often run with `-NoProfile`, so the pwsh profile does not run. The `envgap`
  probe lists the names; record the activation command for each in `toolchains.md`.
- **Windows PATH is read at process start.** A `winget` install changes the registry PATH, but a
  running harness and its shells keep the old PATH until the harness restarts
  ([winget-cli #2815](https://github.com/microsoft/winget-cli/issues/2815)). `envgap` reports
  registry entries missing from the current process.
- **Windows agent shells differ per harness.** Claude Code's Bash tool is Git Bash when Git for
  Windows is installed, else PowerShell; `CLAUDE_CODE_GIT_BASH_PATH` sets the bash path (user
  report, [claude-code #21365](https://github.com/anthropics/claude-code/issues/21365)). OpenCode
  ran commands in Windows PowerShell 5.1 when observed (v2). In Git Bash, plain `ssh` is Git's
  `/usr/bin/ssh`, not Windows OpenSSH (`C:\Windows\System32\OpenSSH\ssh.exe`), so it cannot reach
  an SSH agent on the Windows named pipe (1Password, ssh-agent service). A process started from
  Git Bash inherits that PATH order, even in PowerShell. Record the binary agents must call.
- **Secrets stay where they are.** Record "SSH keys: 1Password agent", never a key, token or
  password; also no values from `.env`, `auth.json`, keychains, rc files, or agent config files
  (some hold plain-text passwords). Both probes print file names and key names only.
- **Name prod contexts explicitly.** List every production cluster context and cloud project by
  name, including ones whose name lacks `prod`, and say which context is safe for local throwaway
  work. Record that the current context is shared global state.
- **Ambient versions differ from project pins.** The `java` / `node` / `python` on PATH is often
  not what repos pin (`.sdkmanrc`, `.nvmrc`, `.python-version`, `.tool-versions`). Record both and
  where pins live. On Windows, `python` can be the Microsoft Store stub; `probe.ps1` reports the
  PATH order.
- **Non-default install locations are the expensive facts.** A version manager installed through
  a package manager lives outside its documented default, and init scripts fall back to the
  default path. Record the real path and the trap.
- **`INDEX.md` stays short.** It is loaded every turn in every session (see Content rules).
- **Edit through the link.** When `~/.device` or a file in it links into a synced folder, read and
  write the link path; replacing the link with a plain file breaks the sync. Exception: the
  Claude Code rules file must be a real file (a link pointing outside the project needs approval).
- **OpenCode ignores `@file` imports** and reads only the first global AGENTS.md it finds; an
  `OPENCODE_CONFIG_DIR` profile with its own AGENTS.md hides `~/.config/opencode/AGENTS.md`.
  `instructions` entries are combined with AGENTS.md, so wire OpenCode through `instructions`.
- **Generated instruction files.** When a file says it is generated ("edit X, then rerun the
  bootstrap"), write to the local overlay the generator names, never to the output file.
- **`--check-index` reports every missing backticked path**, and so does a companion store's
  check. Write a path that is absent on purpose as plain text ("not ~/.sdkman"); then each
  `missing:` line is a real stale path.
- **Git Bash eats backslashes.** In Git Bash, an unquoted heredoc or a double-quoted `python -c`
  string turns `\\` into `\`, so a Windows path in inline Python fails with
  `SyntaxError: (unicode error)`. Write the script to a file with the file-write tool, then run it.
- **WSL:** run `probe.sh` inside the Linux side for agents that run there, and `probe.ps1` on the
  Windows side for agents that run there. They are two indexes for two shells.
