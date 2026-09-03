# CLI tool

CLIs are the simplest case — usually no background process to manage, no ports, no lifecycle.
Focus on **installation**, **representative invocations**, and **exit codes**.

## What matters

- **How to get the binary on `PATH`.** Installed globally? Run via a runner (`npx`, `uv run`,
  `poetry run`, `./gradlew run`)? Built to a local path like `./target/release/foo`? Be explicit —
  don't assume the ambient toolchain version matches what the project pins.
- **Two or three example invocations** that cover the main use cases, with expected output so it's
  obvious whether it worked.
- **Exit codes**, if they carry meaning (e.g. a linter returns non-zero on findings).
- **Stdin behavior**, if the tool reads from stdin.

## Steps

1. Install or build the tool per the project's own instructions (README, `package.json` scripts,
   Makefile, build config).
2. Confirm it resolves: run a version or help flag and check the output.
3. Run a representative command against realistic input — not the trivial/empty case — and read
   the actual output.
4. Check the exit code where it's meaningful: `echo $?` after the command.
5. If the tool reads from stdin, pipe a realistic input through it.

## Example project-skill snippet

If this project's launch steps turn out to be non-obvious, a committed skill for it might look
like:

```markdown
---
name: run-mytool
description: Build, install, and run mytool. Use when asked to run mytool, test it, or verify it's installed correctly.
---

## Setup

    pip install -e .

This puts `mytool` on PATH. Verify:

    mytool --version
    # -> mytool 0.3.1

## Run

Process a single file:

    mytool process input.json
    # -> Processed 42 records, wrote output.json

Read from stdin, write to stdout:

    cat input.json | mytool process -

Lint a directory (exits non-zero on problems):

    mytool lint ./src
    echo $?  # 0 if clean, 1 if issues found
```

## Keep it short

A CLI's run recipe can be very compact. Don't pad it with every flag — `--help` output covers
that. Just show enough that an agent can (a) get it running, (b) confirm it works against real
input, (c) read the result.
