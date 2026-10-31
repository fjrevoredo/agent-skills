# Toolchains: details and gotchas

Back to [INDEX.md](INDEX.md).

<!-- One section per stack the user works in, plus containers and shell gotchas. Each section:
     where the manager really lives, where projects pin versions, a tested activation snippet that
     works in an agent shell, and the traps already hit. Delete the macOS/Linux or the Windows
     rows that do not apply. Delete all comments. -->

## Agent shells do not get the interactive setup

<!-- macOS / Linux -->
The toolchain is set up in `<rc file>` (<login | interactive> shell only). In agent tool calls,
<names of missing variables> are **empty**, and the <shell functions> are not reliable.
Activate the toolchain explicitly in each command.

<!-- Windows: check each item with the envgap and shells sections of probe.ps1 -->
- Agent shells: <agent>: <Git Bash | pwsh | Windows PowerShell 5.1>; <agent>: <shell>.
- PATH is read at process start. After a `winget` install, restart the agent harness before you
  use the new tool (`envgap` → `path_entries_missing_in_this_process`).
- pwsh profile: agent PowerShell tools run <with | without> it. It adds <names> (`envgap` →
  `vars_added_by_pwsh_profile`).
- Claude Code Bash tool: <Git Bash at `<path>` | PowerShell>. `CLAUDE_CODE_GIT_BASH_PATH`: <set | unset>.

## <Stack>: <manager>

```
<VAR>=<real path>     # NOT <documented default>, when it differs
<installed versions>: <path pattern>
```

- Projects pin the version in **`<pin file>`** (for example `<example pin>`).
- Ambient version is **<version>** (`<path>`). Most repos want `<pinned version>`.
- <trap: what fails, why, and the fix>
- <build tool: wrapper script, task runner>

```bash
<tested activation snippet that works without the rc files or profile>
<build command>
```

<Alternative activation, when the manager has one: command + side effects.> Version not
installed → `<install command>` (needs the user's approval).

<!-- Windows rows that often apply:
- Node: NVM for Windows; versions in `<NVM_HOME>`, active version linked at `<NVM_SYMLINK>`;
  global npm tools live in that link folder and change with `nvm use`.
- Python: `<uv | py launcher>`; `python` on PATH resolves to `<path>`. The Microsoft Store stub
  (`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`) is <first | later | absent> on PATH.
- Java: JDKs in `<folder>`; `JAVA_HOME` <set | unset> in agent shells. -->

## Containers: <runtime>

- <runtime>; <app agents must not suggest, if any>. The CLI works only while <runtime> runs.
- `<status command>` · `<start command>` · `<stop command>`. Daemon unreachable → `<start command>`.
- The CLI uses the `<context>` context, so it works without `DOCKER_HOST`.
- <Windows: WSL distros and their state; which distro the runtime uses>

## Shell gotchas

- <BSD vs GNU tools (`sed -i ''`), missing GNU variants>
- <Windows: path forms each shell accepts (`C:\x`, `C:/x`, `/c/x`); quoting in PowerShell>
- <agent-specific limits the user has hit>

## SSH and signing

- <where SSH keys live; approval popups; the error text a timeout produces and what it means>
- <Windows: agents call `<ssh binary>`. In Git Bash, plain `ssh` is `<Git ssh path>` and cannot
  reach the agent on `\\.\pipe\openssh-ssh-agent`.>
- <which CLIs use HTTPS and work without SSH>
