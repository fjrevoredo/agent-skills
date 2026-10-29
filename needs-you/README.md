# needs-you

A Claude Code plugin for macOS: a floating popup while a session waits for you, and only then. A tool
approval, an `AskUserQuestion`, an MCP prompt, or an approval gate written in plain text each raise one;
it closes itself once you answer. "Done" stays whatever your terminal already does.

The popup is a [Hammerspoon](https://www.hammerspoon.org) Spoon: it floats above all windows, never takes
the keyboard focus and is not a notification, so Focus modes don't hide it. Click it to jump to the session;
Option-click to dismiss. [herdr](https://herdr.dev) is optional: with it, the popup shows the pane title,
is skipped while you look at that pane, and a click focuses the pane.

## Install

```bash
claude plugin marketplace add https://github.com/fjrevoredo/agent-skills.git
claude plugin install needs-you@fjrevoredo-agent-skills
```

Then, in a new session, run `/needs-you:setup`: it installs Hammerspoon (Homebrew cask, after asking),
copies the Spoon to `~/.hammerspoon/Spoons/`, adds `hs.loadSpoon("NeedsYou"):start()` to
`~/.hammerspoon/init.lua` and shows a test popup. Run it again after a plugin update when the session says
the Spoon is outdated.

Uninstall with `claude plugin uninstall needs-you@fjrevoredo-agent-skills`, then delete
`~/.hammerspoon/Spoons/NeedsYou.spoon` and the load line.

## What it contains

| Part | Purpose |
|---|---|
| `hooks/hooks.json` | Wires every event below to the one hook script |
| `scripts/needs-you.sh` | The hook: decides when to show and when to clear (bash + jq; macOS ships `/usr/bin/jq` from version 15) |
| `NeedsYou.spoon/` | The popup (Hammerspoon Lua). Config: `width`, `colors`, `herdrPath`, `defaultTerminal` |
| `skills/setup` | `/needs-you:setup` and its `setup.sh --check / --install` |
| `tests/` | Hook tests with fake `open`, `herdr`, `uname` and `jq` |

## When it shows and when it closes

| Event | Effect |
|---|---|
| `SessionStart` | Adds the marker rule to the context (below), plus a setup hint when the Spoon is missing or another version |
| `Notification` `permission_prompt`, `elicitation_dialog`, `elicitation_url_dialog` | Show |
| `Notification` `elicitation_response`, `elicitation_complete` | Close |
| `Stop` | Show when the reply's last non-empty line is `[needs-you: <reason>]`; otherwise close |
| `UserPromptSubmit`, `SessionEnd` | Close |
| `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | Close, when the event comes from the same agent (main or subagent) that showed the popup |

The tool events cost one directory check while no popup is open; state older than a day (a crashed session) is dropped. State lives in `${TMPDIR}/needs-you/`,
one file per session with an open popup.

## The marker rule

A question in plain text ends the turn exactly like "done". So the plugin tells the agent, at session start:
prefer `AskUserQuestion`; when the question has to stay in plain text, end the reply with the line
`[needs-you: <short reason>]`; never on reports or "done".

## Limits

- macOS only. Elsewhere the hooks exit silently.
- Claude Code sends `permission_prompt` only after the prompt has waited about six seconds, and only when
  you seem to be away from the terminal. A quick answer never raises a popup.
- After you approve a tool, the popup closes when the tool finishes (`PostToolUse`): no event fires between the
  approval and the end of the tool, so a long build keeps it up.
- A rejected permission ends the turn without `PostToolUse`; the popup stays until your next prompt or a
  click.
- If a parallel tool call of the same agent finishes while another one waits for approval, its
  `PostToolUse` closes the popup early.
- One popup per session. While a background subagent waits, the main agent's `Stop`, your next prompt or a
  new wait in the same session replaces or closes its popup. A subagent's prompt that arrives without an
  `agent_id` isn't closed by that subagent's tool events either; the main agent's `Stop` or your next prompt is.
- The click runs `herdr agent focus` with Hammerspoon's environment, so it reaches herdr only on its default
  socket.
- A click brings the terminal app to the front by its bundle id (`$__CFBundleIdentifier`, set by macOS in
  each terminal); without herdr it can't pick the right tab.

## Development

```bash
python3 -m unittest discover needs-you/tests
claude plugin validate needs-you
needs-you/skills/setup/scripts/setup.sh --check
claude --plugin-dir ./needs-you      # live test without installing
```
