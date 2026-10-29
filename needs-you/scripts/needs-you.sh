#!/usr/bin/env bash
# needs-you hook: raise a Hammerspoon popup while a Claude Code session waits for the user, and close it
# once the wait is over. One script for every event in hooks/hooks.json; it dispatches on hook_event_name.
#
#   SessionStart                   print the marker rule (becomes context), plus a setup hint when the
#                                  installed Spoon is missing or differs from this plugin's version
#   Notification                   permission_prompt, elicitation_dialog, elicitation_url_dialog: show;
#                                  elicitation_response, elicitation_complete: clear
#   Stop                           last non-empty line is "[needs-you: <reason>]": show; else clear
#   UserPromptSubmit, SessionEnd   clear
#   Pre/PostToolUse(Failure)       clear, only when the event's agent_id matches the one stored at show
#                                  time (a background subagent's tool call must not close the main
#                                  agent's popup). Called with --if-pending: exits before jq when no
#                                  popup is open, so ordinary tool calls cost one directory check.
#
# State: ${TMPDIR:-/tmp}/needs-you/<session_id> exists while a popup is open; it holds the agent_id.
# The popup is driven through hammerspoon://needs-you and hammerspoon://needs-you-clear (open -g keeps
# the focus where it is). herdr is optional: with it, the popup gets the pane title, skips a pane the
# user is looking at, and a click focuses the pane. macOS only; elsewhere it exits silently.

set -uo pipefail

input="$(cat)"

[[ "$(uname -s)" == "Darwin" ]] || exit 0

state_dir="${TMPDIR:-/tmp}"
state_dir="${state_dir%/}/needs-you"

if [[ "${1:-}" == "--if-pending" ]]; then
  compgen -G "$state_dir/*" >/dev/null || exit 0
  # State older than a day is left over from a crashed session; drop it so tool calls stay on the fast path.
  find "$state_dir" -type f -mtime +0 -delete 2>/dev/null
  compgen -G "$state_dir/*" >/dev/null || exit 0
fi

jq="$(command -v jq || echo /usr/bin/jq)"
[[ -x "$jq" ]] || exit 0

plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

event="" session="" agent="" ntype="" message="" cwd="" last_line=""
eval "$("$jq" -r '@sh "event=\(.hook_event_name // "") session=\(.session_id // "") agent=\(.agent_id // "") ntype=\(.notification_type // "") message=\(.message // "") cwd=\(.cwd // "") last_line=\((.last_assistant_message // "") | split("\n") | map(select(test("^\\s*$") | not)) | last // "")"' <<<"$input" 2>/dev/null)" || exit 0

[[ "$session" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || session=""
state_file="$state_dir/$session"

spoon_version() {
  sed -n 's/^obj\.version *= *"\([^"]*\)".*/\1/p' "$1" 2>/dev/null | head -n 1
}

session_start() {
  cat <<'EOF'
needs-you: when you stop because you need the user's answer or approval, prefer the AskUserQuestion tool. If the question has to stay in plain text (for example a long draft to review), make the very last line of the reply `[needs-you: <short reason>]`, for example `[needs-you: approve the release notes]`; a hook turns it into a desktop popup. Don't add it to replies that are only reports or "done".
EOF
  local wanted installed
  wanted="$(spoon_version "$plugin_root/NeedsYou.spoon/init.lua")"
  installed="$(spoon_version "$HOME/.hammerspoon/Spoons/NeedsYou.spoon/init.lua")"
  if [[ -z "$installed" ]]; then
    echo "needs-you: the popup (Hammerspoon Spoon) is not installed. If the user asks about the popup, suggest running /needs-you:setup."
  elif [[ -n "$wanted" && "$installed" != "$wanted" ]]; then
    echo "needs-you: the installed popup Spoon is version $installed, the plugin has $wanted. Tell the user once to run /needs-you:setup."
  fi
}

show() {
  local kind="$1" reason="$2"
  [[ -n "$session" ]] || return 0
  mkdir -p "$state_dir"
  printf '%s' "$agent" >"$state_file"

  local pane="${HERDR_PANE_ID:-}" title="" focused=0 info
  if [[ -n "$pane" ]]; then
    info="$("${HERDR_BIN_PATH:-herdr}" pane get "$pane" 2>/dev/null)" || info=""
    if [[ -n "$info" ]]; then
      eval "$("$jq" -r '.result.pane as $p | @sh "title=\($p.terminal_title_stripped // "") focused=\(if $p.focused then 1 else 0 end)"' <<<"$info" 2>/dev/null)" || true
    fi
  fi
  [[ -n "$title" ]] || title="$(basename "${cwd:-Claude}")"

  local url
  url="$("$jq" -rn \
    --arg session "$session" --arg kind "$kind" --arg reason "$reason" --arg title "$title" \
    --arg pane "$pane" --arg terminal "${__CFBundleIdentifier:-}" --arg focused "$focused" \
    '"hammerspoon://needs-you?session=\($session|@uri)&kind=\($kind|@uri)&reason=\($reason|@uri)&title=\($title|@uri)&pane=\($pane|@uri)&terminal=\($terminal|@uri)&focused=\($focused|@uri)"')"
  open -g "$url" >/dev/null 2>&1 || true
}

# Clear the popup of this session. With "match", only when the event comes from the agent that showed it.
clear_popup() {
  [[ -n "$session" && -f "$state_file" ]] || return 0
  if [[ "${1:-}" == "match" && "$(cat "$state_file")" != "$agent" ]]; then
    return 0
  fi
  rm -f "$state_file"
  open -g "hammerspoon://needs-you-clear?session=$session" >/dev/null 2>&1 || true
}

case "$event" in
  SessionStart) session_start ;;
  Notification)
    case "$ntype" in
      permission_prompt) show permission "${message:-Claude needs your approval}" ;;
      elicitation_dialog | elicitation_url_dialog) show elicitation "${message:-Claude needs your input}" ;;
      elicitation_response | elicitation_complete) clear_popup ;;
    esac
    ;;
  Stop)
    # Models sometimes wrap the marker in backticks or emphasis; lines may end with CR.
    marker='^[[:space:]]*[`*_]*\[needs-you:[[:space:]]*(.+)\][`*_]*[[:space:]]*$'
    if [[ "$last_line" =~ $marker ]]; then
      show gate "${BASH_REMATCH[1]}"
    else
      clear_popup
    fi
    ;;
  UserPromptSubmit | SessionEnd) clear_popup ;;
  PreToolUse | PostToolUse | PostToolUseFailure) clear_popup match ;;
esac
exit 0
