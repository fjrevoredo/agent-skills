# Exploration

How to read the probe output (`probe.sh` on macOS/Linux, `probe.ps1` on Windows), which
follow-up probes to run per finding, what to leave unread, and what to leave out of the index.
Everything here is read-only: no installs, no logins, no `start`, no context switches.

## Never read or print

- Secret files: `~/.ssh/*` (keys, `config`, `known_hosts`), `.env*`, `auth.json`, `*credentials*`,
  `~/.netrc`, `~/.npmrc` / `~/.pypirc` tokens, `~/.docker/config.json` auths, `~/.kube/config`
  users section, keychains, password manager stores, browser profiles.
- Environment variable values. Names are fine (`env | cut -d= -f1`); PATH entries are fine.
- Command output that may carry tokens: `gh auth token`, `gcloud auth print-access-token`,
  `kubectl config view --raw`, `docker context inspect` (TLS material).
- Agent and app config files in full (`~/.config/opencode/*.json*`, `~/.claude.json`, MCP
  configs): some hold API keys or plain-text passwords. Read one key in memory (`instructions`,
  MCP server names) and print only that.
- Windows: Credential Manager (`cmdkey /list` prints target names; that is the limit),
  `%APPDATA%\gh\hosts.yml`, the registry under `HKCU:\Software\<vendor>` for tokens.
- rc files and PowerShell profiles in full. They often export tokens. Read their structure with
  values cut off:

  ```bash
  grep -n -E '^[[:space:]]*(export|alias|source|\.|eval|path|PATH|fpath|\$env)' ~/.zshrc | sed -E 's/=.*/=…/'
  ```

  ```powershell
  Select-String -Path $PROFILE -Pattern '^\s*(\$env:|Set-Alias|function|Import-Module|\. )' |
    ForEach-Object { "$($_.LineNumber): $($_.Line -replace '=.*', '=…')" }
  ```

If a follow-up would need one of these, ask the user instead.

## Leave out of the index

Apply the per-line test ("one cheap command answers it → delete") and drop:

- tools pinned by a version manager in each repo (the pin file says it),
- tools that are the latest version everywhere and have no trap,
- facts already in a repo's own files (README, AGENTS.md, build files),
- session data: PIDs, uptime, load, the current directory, running containers,
- counts that change often (package counts, app counts), and full lists,
- hardware detail beyond one short machine line.

## Probe sections → follow-ups

Each section: what to draft from the output, then the follow-ups worth running.

### index
Existing index files and pointers. Update mode: read every index file in full, then
`probe.sh --check-index <file>` for each. A pointer in one agent's file but not another's is a
wiring gap for step 5.

### os
Machine line for `INDEX.md`: model, CPU, RAM, OS version. `command_line_tools: absent` on macOS
means `/usr/bin/git` and `/usr/bin/python3` open an install dialog: record it as a gotcha.

### mdm
`enrollment` / `mdm_agents` → "company-managed (<MDM>)". A VPN app → open question: which resources
need it (databases, internal web UIs, cluster APIs).

### secrets
Password manager apps and CLIs, SSH agent socket. Draft "secrets and SSH keys: <manager>". A
1Password (or other) SSH agent means git-over-SSH can block on an approval popup: ask the user for
the error text they see when it times out.

### packages
Record the manager, its prefix and the listing command, not the list. Note `pipx`, `cargo`, `go`
global installs only when agents may need them.

### languages
For each manager found:

- Where it lives, when not at its documented default (SDKMAN via Homebrew, nvm via a formula).
- Whether agent shells get its env (cross-check `envgap`: `SDKMAN_DIR`, `NVM_DIR`, `PYENV_ROOT`).
- Ambient version vs installed versions.

Two managers for one stack (nvm and fnm, pyenv and uv-managed Pythons, SDKMAN and
`/usr/libexec/java_home` JDKs) → open question: which is canonical, which is leftover.

Find which pins repos actually use (run per repo root from the `repos` section):

```bash
find <root> -maxdepth 2 \( -name .sdkmanrc -o -name .nvmrc -o -name .node-version \
  -o -name .python-version -o -name .tool-versions -o -name mise.toml -o -name uv.lock \
  -o -name poetry.lock -o -name rust-toolchain.toml -o -name go.mod -o -name gradlew \
  -o -name pom.xml -o -name package.json \) 2>/dev/null | sed 's|.*/||' | sort | uniq -c | sort -rn
```

Then the pinned values (for example `cat <root>/*/.sdkmanrc | sort | uniq -c`) and whether each
pinned version is installed. A common pin that differs from the ambient version is a gotcha.

Build the activation snippet per stack and test it in this (agent) shell: it must work without the
rc files, for example:

```bash
export SDKMAN_DIR=<path>; export JAVA_HOME="$SDKMAN_DIR/candidates/java/<pin>"; "$JAVA_HOME/bin/java" -version
```

### containers
Which runtime, how it starts, whether the CLI works without `DOCKER_HOST` (current Docker context),
socket path, resources. `docker_daemon: unreachable` → record the start command, don't run it.
`.testcontainers.properties` keys and any Testcontainers env var in `envgap` → gotcha for
agent-shell test runs.

### clusters
- Every context name; flag the ones named `prod` and ask about the rest.
- The current context is global state shared with the user's terminals.
- Cloud CLIs: active account and project, config count, whether ADC exists, and where a re-login
  must happen (interactive only).
- Tools present (helm, kustomize, argocd, k9s) and any GitOps UI host → open question.

### githosts
Git hosts from `repos` origin counts plus CLI auth status. For each host: its CLI (`gh`, `glab`,
`tea`), the config path, and whether it uses HTTPS or SSH. Team helper scripts often sit on PATH:
look at unusual PATH dirs (`echo "$PATH" | tr : '\n'`) and list their executables; ask what each
does.

### shells
Login shell vs the shell the terminal starts (`wezterm_default_prog`, `kitty_shell`, …; follow a
variable to its definition in the same config). When they differ, rerun
`probe.sh --section envgap --shell <interactive shell>`. rc files that are symlinks → where the
real config lives (`synced`). Read rc structure with the masked grep above to find helpers and
aliases worth one line.

### envgap
Variables set by the user's login + interactive shell but missing in this agent shell, plus missing
PATH entries. For each name: which tool needs it, what breaks without it, and the activation
command. Ignore prompt and terminal noise. Missing PATH dirs that hold tools agents call are the
important ones. `path_entries_missing` compares with the shell that started the probe, so it is
empty when you start the probe from an interactive terminal. `path_entries_interactive_only`
compares with a non-interactive shell from a clean env (what `ssh host cmd` and many services get):
a dir listed there holds tools that such agent shells cannot find (for example `~/.opencode/bin`).
System dirs that PAM, `/etc/profile` or macOS `path_helper` add can show there too; ignore them.

### agents
- Installed agents, versions, global instruction files, skill dirs, MCP server names.
- MCP servers and connectors defined outside these files (Claude.ai connectors, plugins, project
  scopes) don't show here: ask the user.
- Multi-agent tools (`tmux`, `zellij`, `herdr`, …) and shared skill dirs (`~/.agents/skills`).
- Other knowledge stores the agents should read (a team knowledge base, a work log repo): ask.

### apps
Only the dev-relevant list matters. Ask which app the user uses per purpose (IDE per language,
DB client, API client, browser, chat) and which tools the agents use instead.

### repos
Roots with repo counts and origin hosts. For each root: purpose (work, personal, scratch), where
new projects go, legacy or tool-generated dirs agents should ignore. Many repos under one root →
ask whether a grouping exists (team, product, capability) that folder names don't show; that is
`paths.md`.

### synced
Symlinks from `~` into cloud drives or dotfiles repos. Records where configs really live, and is
the natural home for the index's source of truth (step 4).

## Windows (`probe.ps1`) follow-ups

Sections with the same name mean the same thing. Run follow-ups in pwsh; quote paths with spaces.

### os
One short machine line from `windows`, `model`, `cpu`. `mdm_enrollments` above 0 or
`domain_joined: yes` → ask whether the machine is company-managed.

### packages
Record the manager and its list command (`winget list`, `scoop list`, `choco list`). Tools that
winget installs as links sit in `winget_links`; their real folders are under
`%LOCALAPPDATA%\Microsoft\WinGet\Packages`. `npm_global_prefix` under an NVM link folder changes
with `nvm use`: record it.

### languages
- NVM for Windows: `nvm list`; the active version is the target of `NVM_SYMLINK`.
- Python: `python_on_path_order`. When the WindowsApps stub comes first, `python` opens the
  Store: record the real interpreter or `uv run`. `uv python list --only-installed` for versions.
- Java: `jdks` folders vs `java_ambient` and `java_home_env`. IDE-managed JDKs in `~\.jdks` are
  not on PATH; the activation is `$env:JAVA_HOME='<jdk>'; $env:PATH="$env:JAVA_HOME\bin;$env:PATH"`.
  Test it in a pwsh command before you write it down.

### containers
`docker_daemon: unreachable` → record the start command (open Docker Desktop), don't run it.
`wsl_distros` → which distro the runtime uses, and whether agents run commands inside WSL.

### shells
`claude_code_shell`, `this_shell`, `parent_process`. Ask which shell the terminal starts
(`wezterm_default_prog`, `windows_terminal_default_profile`) and which shell each agent uses. A
profile under OneDrive (`documents_redirected`) syncs between machines: record that.

### envgap
- `path_entries_missing_in_this_process` / `restart_needed: yes` → the harness started before an
  install. Tell the user to restart it; record the trap in `toolchains.md`.
- `ssh_order_this_process`, `git_bash_ssh`, `ssh_first_is_git` → record the binary agents must
  call for SSH through an agent on the named pipe (`C:\Windows\System32\OpenSSH\ssh.exe`).
- `vars_added_by_pwsh_profile` → variables agent PowerShell tools miss when they run with
  `-NoProfile`. For each one a tool needs, record the activation.

### secrets
`openssh_agent_pipe` with `ssh_agent_service` stopped → the pipe belongs to another agent (often
1Password). Ask the user which one, and the error text a locked vault gives.

### synced
Junctions and symlinks (`~/.claude/skills/*` → `~/.agents/skills/*`, rc files into a dotfiles
repo). Record where the real files live.

### agents
Same as above. Also `opencode_profiles` and `opencode_config_dir_env`: a profile with its own
AGENTS.md hides the global one (see `wiring.md`). `pi_agents_local_md: present` → pi's AGENTS.md
may be generated; wire through the overlay. `hermes_terminal_cwd` unset or `.` → the Hermes
gateway loads context from the home folder (see `wiring.md`).

### repos
`root <dir>` lines list origin `host/group` counts. Many groups under one root → offer the
"grouped by origin" layout of `assets/paths-template.md`. What a group is for is a question for the
user (or the companion store), not for the probe.
