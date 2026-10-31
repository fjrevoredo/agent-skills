# Device Index: <hostname or short machine name>

<!-- Fill every <…>. Delete a section only when the user marked it N/A. Delete all comments.
     Line budget: about 60 lines. Per-line test: if one cheap command answers it, delete the line.
     Facts only; rules go to the agents' instruction files. -->

- Verified: <YYYY-MM-DD>
- Host: <hostname, exactly as the probe's os section prints it>
- OS: <OS name + version/build, as the probe prints it>
<!-- With a companion profile, add the line it gives, for example:
- Durable facts about this machine and other machines: <store> page `<page id>`. This index never repeats them. -->

Facts about this machine: where things live and how the toolchain is wired for agents.
Rules for how an agent must act are in each agent's own instruction file.

- Source of truth: `<~/.device/ or the synced folder it links to>`
- Topic files (read when the task touches them): [toolchains.md](toolchains.md) (build, test, run,
  install)<, [paths.md](paths.md) (repo groupings: what lives where)>

## Machine

- <role or model>, <OS>, <arch>. <Company-managed (<MDM>) | Personal>.
- Packages: <manager> (list: `<command that lists installed packages>`). Secrets and SSH keys: <manager>.

## Paths

| Path | What |
|---|---|
| `<work root>` | Work repos. **New work projects go here.** |
| `<personal root>` | Personal projects. **New personal projects go here.** |
| `<scratch root>` | Scratch and experiments. **Throwaway work goes here.** |
| `<config path>` | <what config lives here, and where it is linked from> |
| `<knowledge store>` | <what agents should read there, and when> |

<!-- Legacy and tool-generated dirs: name them so agents skip them. -->
Legacy, do not use for new work: `<path>` (<why>).

## Shells and terminal

- Terminal: <app> (`<config path>`) starts <shell>.
- Agent shells: <agent>: <shell>; <agent>: <shell>. They get <PATH entries> but **not** <what
  they miss> (<names>). Details: [toolchains.md](toolchains.md).

## Toolchains (summary)

**Before you build, test, run or install anything, read [toolchains.md](toolchains.md).**

| Stack | Manager | Key fact |
|---|---|---|
| <stack> | <manager (location if non-default)> | <pin file; ambient vs pinned version; the trap> |
| Containers | <runtime> | <how the CLI reaches it; start command> |

## Applications

<!-- Only lines that change what an agent does. Not the user's app inventory. -->
- Git: agents use the `git` CLI<; the user uses <GUI client>>.
- <purpose>: agents use <tool>, not <other tool>.

## Services and accounts (no secrets)

- Git hosts: <host> (CLI `<cli>`, <HTTPS|SSH>).
- Kubernetes: **prod contexts:** <names>. Local/safe: <name>. The current context is shared state.
- <issue tracker / wiki>: access path <CLI | MCP | web>.
- VPN needed for: <resources>.

## Agents

- Wired: <agent>, <agent>. Skills: <shared dir>.
- MCP servers and connectors the probe can't see: <names>.
