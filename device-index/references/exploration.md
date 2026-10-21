# Exploration

How to read `probe.sh` output, which follow-up probes to run per finding, and what to leave
unread. Everything here is read-only: no installs, no logins, no `start`, no context switches.

## Never read or print

- Secret files: `~/.ssh/*` (keys, `config`, `known_hosts`), `.env*`, `auth.json`, `*credentials*`,
  `~/.netrc`, `~/.npmrc` / `~/.pypirc` tokens, `~/.docker/config.json` auths, `~/.kube/config`
  users section, keychains, password manager stores, browser profiles.
- Environment variable values. Names are fine (`env | cut -d= -f1`); PATH entries are fine.
- Command output that may carry tokens: `gh auth token`, `gcloud auth print-access-token`,
  `kubectl config view --raw`, `docker context inspect` (TLS material).
- rc files in full. They often export tokens. Read their structure with values cut off:

  ```bash
  grep -n -E '^[[:space:]]*(export|alias|source|\.|eval|path|PATH|fpath|\$env)' ~/.zshrc | sed -E 's/=.*/=…/'
  ```

If a follow-up would need one of these, ask the user instead.

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
important ones.

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
