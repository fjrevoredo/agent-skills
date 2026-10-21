# Device Index: <hostname or short machine name>

<!-- Fill every <…>. Delete a section only when the user marked it N/A. Delete all comments.
     Target: about one screen. Facts only; rules go to the agents' instruction files. -->

Facts about this machine: what is installed, where things live, and how the toolchain is wired.
It holds facts only. Rules for how an agent must act are in each agent's own instruction file.

- Source of truth: `<~/.device/ or the synced folder it links to>`
- Topic files (read when the task touches them): [toolchains.md](toolchains.md) (build, test, run,
  install)<, [paths.md](paths.md) (repo groupings: what lives where)>

## Machine

- <model>, <CPU> (<arch>), <RAM>, <OS + version>
- <package manager + prefix> (list: `<command that lists installed packages>`)
- <Company-managed (<MDM>) | Personal>. VPN: <app>, needed for <resources>. Secrets and SSH keys: <manager>.

## Paths

| Path | What |
|---|---|
| `<work root>` | Work repos (<host>, ~<count>). **New work projects go here.** |
| `<personal root>` | Personal projects. **New personal projects go here.** |
| `<scratch root>` | Scratch and experiments. **Throwaway work goes here.** |
| `<config path>` | <what config lives here, and where it is symlinked from> |
| `<agent config dirs>` | <agent>: config, instructions, skills |
| `<knowledge store>` | <what agents should read there, and when> |

<!-- Legacy and tool-generated dirs: name them so agents skip them. -->
Legacy, do not use for new work: `<path>` (<why>).
Tool-generated, ignore: `<paths>`.

## Shells and terminal

- Terminal: <app> (`<config path>`). <key bindings agents may mention, if any>
- Interactive shell: <shell>. Login shell (`$SHELL`): <shell>. Prompt: <prompt tool>.
- <shell> config: `<path>` → <link target>. <what it copies from the login shell, what it does not>
- Agent shells get <PATH entries> but **not** <the exports agents miss> (<names>). Details: [toolchains.md](toolchains.md).

## Toolchains (summary)

**Before you build, test, run or install anything, read [toolchains.md](toolchains.md).**
The table below is a summary only.

| Stack | Manager | Key fact |
|---|---|---|
| <stack> | <manager (location if non-default)> | <pin file; ambient vs pinned version; the trap> |
| Containers | <runtime> | <how the CLI reaches it; start command> |
| Kubernetes | <tools> | Contexts include **prod**: see Services |
| Other | <tools> | — |

## Applications

| Purpose | App |
|---|---|
| <language / task> | <app> |
| Git | Agents: `git` CLI. User: <GUI client>. |
| Browser | <browser> (<logged in? used by a browser MCP?>) |

## Services and accounts (no secrets)

- Git hosts: <host> (CLI `<cli>`, config `<path>`, <HTTPS|SSH>); <team helper scripts and what they do>
- Cloud: account <which>, project <id>, region <region>. <re-login: interactive, user only, symptom: "<error>">
- Kubernetes: **prod contexts:** <names>. Other: <names>. Local/safe: <name>.
  The current context is global state shared with the user's shells.
- <issue tracker / wiki>: access path <CLI | MCP | web>.
- VPN needed for: <resources>.
- Local URLs that hit shared backends: <url> → <backend>.

## Agents

- Installed: <agent (version)>, … Global instructions: <paths>.
- Skills: <shared dir> (shared), <per-agent dirs>.
- MCP servers: <agent>: <names>; <connectors defined elsewhere>.
- Multi-agent tooling: <tools and what they do>.
