# Adapters

One adapter per transcript format. Each is read-only and reports what it found under `coverage`.
When a harness changes its format, coverage shows it (unrecognised records rise, or sessions drop to
zero) instead of the numbers silently going wrong.

## Path rules

| Store | Resolution order |
| --- | --- |
| Storage (this skill's output) | `--home` › `$SESSION_TELEMETRY_HOME` › `$XDG_DATA_HOME/session-telemetry` › `~/.local/share/session-telemetry` |
| Claude Code | `$CLAUDE_CONFIG_DIR/projects` › `~/.claude/projects` |
| OpenCode | `$OPENCODE_DB` › `~/.local/share/opencode/opencode.db` |

A missing store is a coverage line ("missing (path)"), never an error. `telemetry.py sources
[--repo DIR]` prints what exists.

## Claude Code — JSONL

- Folder per project: the absolute repository path with every non-alphanumeric character replaced by
  `-` (`/home/me/src/my-app` → `-home-me-src-my-app`). Matched case-insensitively.
- One `<session-uuid>.jsonl` per session; a `<session-uuid>/` folder beside it holds subagent
  transcripts (not read).
- A session matches when its raw text contains any key.
- Record `type`s used: `assistant` (content blocks `text`, `tool_use`, `thinking`), `user` (a string
  = human prompt unless `isMeta` or a command/caveat/system-reminder wrapper; a list = `tool_result`
  blocks), `system` with `subtype: compact_boundary` (a compaction). Records with `isSidechain` are
  skipped.
- Recognised but unused: `ai-title` (never read: titles are content), `summary`, `attachment`,
  `mode`, `atis-latch`, `last-prompt`, `bridge-session`, `permission-mode`, `file-history-delta`,
  `file-history-snapshot`, `queue-operation`, `agent-name`, `cost-state`, `custom-title`.
  Anything else counts as unrecognised.
- Timing: every record has a UTC `timestamp`. A step spans from the previous non-assistant record to
  its last assistant record; tool time is `tool_result` time − `tool_use` time.
- A few lines per file may be truncated JSON while a session is live; they count as
  `claude:<bad json>`.

## OpenCode — SQLite

Opened with a `file:…?mode=ro` URI: the database is live, in WAL mode, and can be several GB. Never
open it read-write. Sessions are matched on `replace(lower(directory), '\', '/')` equal to the
repository path, then on content; child sessions (`parent_id` set) are skipped.

### v2 — `session_v2` + `session_message`

- `session_message.type`: `user` (`data.text`), `assistant` (`data.time.created/completed`,
  `data.content` blocks `text`, `tool` with `state.input` / `state.content`, `reasoning`),
  `compaction`, `synthetic`, `idle`, `system`, `agent-switched`, `model-switched`.
- **No per-tool timing.** A step's tool time is the gap to the next step, split across its calls.

### v1 — `session` + `message` + `part`

- `message.data.role` and `time.created/completed`; a message with `summary: true` or
  `mode: compaction` is a compaction.
- `part.data.type`: `text` (human prompt when the message role is `user` and not `synthetic`),
  `tool` (`tool`, `state.input`, `state.output`, `state.time.start/end` — the best timing of the
  three formats), `reasoning`, `step-start`, `step-finish`, `patch`, `file`, `compaction`,
  `snapshot`, `agent`, `subtask`, `retry`.

## When coverage drops

1. Run `telemetry.py sources --repo <repo>` — does the store exist, and does it hold sessions for
   the repo?
2. Read one record of the new shape (types only, not content) and add the type to the adapter's
   known set, or map the renamed field.
3. Re-run `report` on an already-closed plan and compare with its stored subject file.
