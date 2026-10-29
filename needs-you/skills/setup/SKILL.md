---
name: setup
description: |
  Set up, check or repair the needs-you desktop popup (Hammerspoon and its NeedsYou Spoon) on macOS. Use this
  skill when the user runs /needs-you:setup, just installed or updated the needs-you plugin, asks why the
  "needs you" popup doesn't appear, or when the session context says the popup Spoon is missing or outdated.
  Triggers: needs-you setup, popup not showing, install the popup, Hammerspoon Spoon, NeedsYou.spoon,
  update the Spoon.
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/setup.sh *)
compatibility: macOS with Homebrew; Hammerspoon is installed by the script when the user agrees.
metadata:
  version: "1.0.0"
---

# Set up the needs-you popup

The plugin's hooks decide *when* to show or close a popup; the popup itself is a Hammerspoon Spoon that
has to live in `~/.hammerspoon/Spoons/`. This skill puts it there.

## 1. Check

```bash
${CLAUDE_SKILL_DIR}/scripts/setup.sh --check
```

Prints JSON. `missing` lists what is not ready: `jq`, `hammerspoon`, `hammerspoon_running`, `spoon` (missing or
another version than the plugin's), `load_line`, `remove_old_binding`. Exit 0 means ready: say so and stop.
Exit 2 means not macOS: the popup can't work there; say so and stop.

## 2. Install

If `jq` or `hammerspoon` is in `missing`, ask the user first: the script runs `brew install jq` or
`brew install --cask hammerspoon`.
Then run:

```bash
${CLAUDE_SKILL_DIR}/scripts/setup.sh --install
```

It copies the Spoon, adds `hs.loadSpoon("NeedsYou"):start()` to `~/.hammerspoon/init.lua` when absent,
restarts Hammerspoon and sends a test popup. Progress goes to stderr, the final state to stdout as JSON.

## 3. Verify

Ask the user whether the test popup ("needs-you … Setup works.") appeared at the top centre of the screen.
If `missing` still lists items, fix them by the Gotchas below and run `--check` again.

## Gotchas

- `~/.hammerspoon/init.lua` is often a symlink into a dotfiles repo. The script appends to the real file;
  tell the user which file changed (`init_lua_symlink_to`) so they can commit it there.
- `remove_old_binding`: init.lua still has a hand-made `hs.urlevent.bind("needs-you", …)`. It overrides the
  Spoon. Show the user the block and remove it only with their OK; then run `--install` again to reload.
- `hammerspoon_running` missing after an install: on its very first launch Hammerspoon opens its
  Preferences window and may ask for permissions. The user closes it; enabling "Launch at login" there keeps
  the popup working after a reboot.
- After a plugin update, the SessionStart hook says when the copied Spoon is outdated; `--install` again
  replaces it. Never symlink the Spoon into the plugin folder: that path changes with every update.
- No popup during a live test is often expected: Claude Code sends `permission_prompt` only after about six
  seconds, and with herdr a popup is skipped while the user looks at that pane.
