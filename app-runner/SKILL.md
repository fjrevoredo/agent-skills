---
name: app-runner
description: |
  Launch and drive a real running app to prove a change actually works — not run its test suite,
  not import a function and print the result. Covers CLI tools, servers/APIs, and browser-driven
  web apps. First checks whether this project already has a committed skill documenting how to
  launch this exact app and defers to it verbatim; otherwise dispatches to a built-in
  launch-and-drive pattern by project type, then writes up anything non-obvious it had to discover
  as a new project skill for next time. Use whenever the user asks to run, start, launch, boot, or
  spin up the app, wants a screenshot or manual proof a change works, asks to smoke-test a build, or
  wants to verify behavior beyond what unit tests show.
  Triggers: run the app, start the app, launch it, boot up, spin up the server, try it out, smoke
  test, take a screenshot, does it actually work, run it manually, click through the app, drive the
  UI, verify end-to-end, run the CLI.
metadata:
  version: "1.0.0"
---

# App Runner

Running an app means launching it and interacting with it the way a real user or caller would —
not running its test suite, and not importing a function to print a return value. A test suite
proves the code does what the tests assert; running the app proves the thing a user would actually
hit works.

## Step 1 — Check for an existing project skill first

Someone may have already documented how to launch this exact app. Reusing that beats reinventing
it, and following a maintained recipe catches drift a generic dispatch table can't.

Walk up from the current directory toward the repository root. At each level, check the common
skill-directory conventions for one that already covers launching this app:

- `.claude/skills/`
- `.agents/skills/`
- `.github/skills/`
- `.codex/skills/`
- a plain mention in `CLAUDE.md` or `AGENTS.md` pointing at a runbook or script

Look for a `SKILL.md` or `ENTRY.md` whose description mentions launching, running, starting, or
booting this app.

- **Found a clear match.** Follow it verbatim — don't paraphrase steps or skip patches it
  describes. It encodes project-specific knowledge (ports, env vars, auth) that a generic recipe
  can't guess.
- **Mega-repo, several plausible matches.** Ask the user which unit/service/package they mean
  before picking one.
- **Found something, but it looks stale** (fails on unrelated mechanics — wrong port, missing
  script, outdated command). Tell the user it looks out of date, then either follow it with
  corrections or fall through to Step 2. Offer to refresh it per Step 4 once the app is running.
- **Nothing found.** Fall through to Step 2.

## Step 2 — Match the project type

| Project type | Read |
|---|---|
| CLI tool / script | `references/cli.md` |
| Server / API / backend service | `references/server.md` |
| Browser-driven web app (has a dev server serving HTML) | `references/browser.md` |

If the project is a TUI, a desktop GUI, a library/SDK with no runnable entrypoint of its own, or
otherwise doesn't cleanly match one of the three rows above: start from whichever reference is
closest in shape (a TUI is closest to CLI; a desktop GUI is closest to browser) and adapt. If this
kind of project comes up often, add a new `references/<type>.md` file following the same shape and
a new row to the table above — that's a minor addition, not a redesign of this skill.

## Step 3 — Drive it, don't just launch it

Launching proves the entrypoint resolves. Driving proves the app actually does the thing. Do both,
in order, and don't report success after only the first.

| Type | Minimum bar to call it "driven" |
|---|---|
| CLI | Run a representative command with realistic input, inspect the output, check the exit code. |
| Server / API | `curl` (or equivalent) the specific route the change touches, not just a generic `/health` check, and read the response body. |
| Browser app | Click or fill the control the change touches, wait for the resulting element, take a screenshot, and **look at it** — a blank or error frame is a failure to investigate, not a sign to wait longer. |

Each reference file has the concrete mechanics (launch pattern, readiness check, driving snippet)
for its type.

## Step 4 — Write up what you learned

If getting the app running required anything non-obvious — a package that had to be installed
first, an environment variable nobody documented, a config file that needed a local patch, a
specific flag to avoid a broken default — commit it as a project-level skill so the next agent (or
person) doesn't have to rediscover it.

- If Step 1 found an existing skill-directory convention in this repo, add the new skill there,
  matching its shape.
- If Step 1 found nothing, default to a `.claude/skills/run-<app-name>/SKILL.md`-shaped file —
  reasonable to assume as a default even on repos that don't otherwise use it, since it's the most
  common convention.
- Use the `references/*.md` file you followed in Step 2/3 as the shape to imitate: prerequisites,
  the exact run command, how to verify readiness, one representative interaction, how to stop it.

Skip this step entirely if nothing surprising came up — a skill that just repeats the built-in
recipe verbatim isn't worth committing.

## Gotchas

- **A broad `pkill -f "<pattern>"` can kill your own session.** If the pattern matches your own
  command line (e.g. `pkill -f node` while running inside a Node-based agent process), you can take
  yourself out along with the target. Stop a launched process by its captured PID or by the
  specific port's listener instead: `lsof -ti:PORT -sTCP:LISTEN | xargs -r kill`.
- **A fixed `sleep` before checking readiness is a race, not a wait.** Poll for the real signal
  (an HTTP health check, a specific log line, a port accepting connections) instead of guessing a
  duration.
- **A blank or broken screenshot means investigate, not "give it more time."** Check console/network
  errors and the dev-server log before retrying with a longer wait.
- **In a mega-repo, ask which unit** rather than guessing which service or package "the app" refers
  to.
- **A stale project skill is still worth flagging to the user**, even when you route around it
  manually by falling through to Step 2 — someone should fix or remove it.
- **"It ran" and "it works" are different claims.** Only make the second one after Step 3's driving
  check has actually passed.
