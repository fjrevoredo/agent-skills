# Feedback routing

Where each kind of target lives on this machine, and how a fix gets there. `/agent-feedback:process`
reads this file to pick the hand-off for each group. Fill in the angle-bracket parts, delete rows that
don't apply, add a row whenever processing meets a target that isn't listed.

## Hand-offs

| Hand-off | When | How |
|---|---|---|
| **setup edit** | The fix is in a file you own and edit directly | Draft the diff, apply it after the user approves, entries → `proposed/` with the file as link |
| **brief** | The fix is a change in a repo that has its own review (MR/PR) | Write `briefs/<slug>.md`, entries → `proposed/` with the brief as link; someone starts it in that repo |
| **relay** | The fix is a message, ticket or page for other people | Hand the exact text to <who sends it for you, e.g. the user, or an agent that posts after approval>, entries → `proposed/` |
| **wontfix** | Obsolete, a one-off, or tracked somewhere else | Entries → `wontfix/` with the reason (and where it is tracked) |

## Targets

| Target | Where it lives | Hand-off | Notes |
|---|---|---|---|
| Global agent instructions | <~/.claude/CLAUDE.md, AGENTS.md> | setup edit | One short line per lesson; check it isn't already there |
| Agent memory | <memory dir> | setup edit | |
| Machine facts (paths, toolchains, CLIs) | <a device index or dotfiles README> | setup edit | |
| Agent settings and permissions | <~/.claude/settings.json> | setup edit | |
| Own skills and plugins | <repo of your skills> | setup edit or brief | |
| Installed third-party skills | <skill lock file> | setup edit (steering line) | Never edit an upstream copy: an update overwrites it. Add a line to the global instructions, or fork |
| Shared team skills or knowledge base | <repo> | brief | Opening the MR/PR is a write others see: needs approval |
| A work repo's docs and dev tooling | that repo (`repo:` field of the entry) | brief | |
| Tickets, wiki pages, chat | <Jira, Confluence, Slack …> | relay | |
| Your tool vendor (CLI, MCP, agent harness bug) | <issue tracker or feedback command> | relay or wontfix | |
