# Toolchains: details and gotchas

Back to [INDEX.md](INDEX.md).

<!-- One section per stack the user works in, plus containers and shell gotchas. Each section:
     where the manager really lives, where projects pin versions, a tested activation snippet that
     works in an agent shell, and the traps already hit. Delete all comments. -->

## Agent shells do not get the interactive setup

The toolchain is set up in `<rc file>` (<login | interactive> shell only). In agent tool calls,
<names of missing variables> are **empty**, and the <shell functions> are not reliable.
Activate the toolchain explicitly in each command.

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
<tested activation snippet that works without the rc files>
<build command>
```

<Alternative activation, when the manager has one: command + side effects.> Version not
installed → `<install command>` (needs the user's approval).

## Containers: <runtime>

- <runtime>; <app agents must not suggest, if any>. The CLI works only while <runtime> runs.
- `<status command>` · `<start command>` · `<stop command>`. Daemon unreachable → `<start command>`.
- Default resources: <cpu / memory>. Heavy stacks: `<start with more resources>`.
- The CLI uses the `<context>` context, so it works without `DOCKER_HOST`. Socket: `<path>`.
- <test containers: config file, env var agent shells miss, the export that fixes it>

## Shell gotchas

- <BSD vs GNU tools (`sed -i ''`), missing GNU variants>
- <agent-specific limits the user has hit>

## SSH and signing

- <where SSH keys live; approval popups; the error text a timeout produces and what it means>
- <which CLIs use HTTPS and work without SSH>
