#!/usr/bin/env bash
# Check or install the popup side of the needs-you plugin: Hammerspoon, the NeedsYou Spoon and its load line.
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: setup.sh [--check | --install]

  --check     (default) Report the state as JSON on stdout; change nothing.
  --install   Install Hammerspoon with Homebrew when missing, copy the NeedsYou Spoon to
              ~/.hammerspoon/Spoons/, add hs.loadSpoon("NeedsYou"):start() to ~/.hammerspoon/init.lua
              when absent (a symlinked init.lua is followed), restart Hammerspoon and show a test popup.
              Safe to run again. Prints the state after the install as JSON.

Needs jq (macOS ships /usr/bin/jq from version 15; --install adds it with Homebrew otherwise).

Exit codes: 0 ready, 1 something is missing (see "missing"), 2 not macOS, 3 install step failed, 64 bad usage.
Environment: HAMMERSPOON_DIR overrides ~/.hammerspoon (for tests).
EOF
}

mode="check"
case "${1:-}" in
  "" | --check) ;;
  --install) mode="install" ;;
  -h | --help) usage; exit 0 ;;
  *) echo "setup.sh: unknown argument '$1' (expected --check or --install)" >&2; exit 64 ;;
esac

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo '{"macos": false, "missing": ["macos"]}'
  echo "setup.sh: the popup needs macOS and Hammerspoon; the plugin's hooks stay silent elsewhere." >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(cd "$script_dir/../../.." && pwd)"
source_spoon="$plugin_root/NeedsYou.spoon"
hs_dir="${HAMMERSPOON_DIR:-$HOME/.hammerspoon}"
target_spoon="$hs_dir/Spoons/NeedsYou.spoon"
init_lua="$hs_dir/init.lua"
load_line='hs.loadSpoon("NeedsYou"):start()'
# An active (not commented-out) load line, either quote style.
load_pattern='^[[:space:]]*(local[[:space:]]+[[:alnum:]_]+[[:space:]]*=[[:space:]]*)?hs\.loadSpoon\(["'\'']NeedsYou["'\'']\)'
jq="$(command -v jq || echo /usr/bin/jq)"

spoon_version() {
  sed -n 's/^obj\.version *= *"\([^"]*\)".*/\1/p' "$1" 2>/dev/null | head -n 1
}

hs_installed() { open -Ra Hammerspoon >/dev/null 2>&1; }
hs_running() { pgrep -xq Hammerspoon; }

report() {
  local installed=false running=false spoon_installed spoon_wanted load=false old=false
  hs_installed && installed=true
  hs_running && running=true
  spoon_installed="$(spoon_version "$target_spoon/init.lua")"
  spoon_wanted="$(spoon_version "$source_spoon/init.lua")"
  grep -qE "$load_pattern" "$init_lua" 2>/dev/null && load=true
  grep -qE 'urlevent\.bind\(["'\'']needs-you' "$init_lua" 2>/dev/null && old=true

  local missing=()
  [[ "$installed" == true ]] || missing+=("hammerspoon")
  [[ "$running" == true ]] || missing+=("hammerspoon_running")
  [[ -n "$spoon_installed" && "$spoon_installed" == "$spoon_wanted" ]] || missing+=("spoon")
  [[ "$load" == true ]] || missing+=("load_line")
  [[ "$old" == false ]] || missing+=("remove_old_binding")

  "$jq" -n \
    --argjson installed "$installed" --argjson running "$running" \
    --arg spoon_installed "$spoon_installed" --arg spoon_wanted "$spoon_wanted" \
    --arg init_lua "$init_lua" --arg init_lua_target "$(readlink "$init_lua" 2>/dev/null)" \
    --argjson load "$load" --argjson old "$old" \
    --args '{
      macos: true,
      hammerspoon_installed: $installed,
      hammerspoon_running: $running,
      spoon_installed_version: (if $spoon_installed == "" then null else $spoon_installed end),
      spoon_plugin_version: $spoon_wanted,
      init_lua: $init_lua,
      init_lua_symlink_to: (if $init_lua_target == "" then null else $init_lua_target end),
      load_line_present: $load,
      old_binding_present: $old,
      missing: $ARGS.positional
    }' "${missing[@]+"${missing[@]}"}"
  [[ ${#missing[@]} -eq 0 ]]
}

fail() { echo "setup.sh: $*" >&2; exit 3; }

install() {
  if [[ ! -x "$jq" ]]; then
    command -v brew >/dev/null 2>&1 || fail "jq is missing (macOS ships it from version 15) and Homebrew isn't on PATH"
    brew install jq >&2 || fail "brew install jq failed"
    jq="$(command -v jq)"
  fi
  if ! hs_installed; then
    command -v brew >/dev/null 2>&1 || fail "Hammerspoon is missing and Homebrew isn't on PATH; install it from https://www.hammerspoon.org"
    echo "Installing Hammerspoon with Homebrew…" >&2
    brew install --cask hammerspoon >&2 || fail "brew install --cask hammerspoon failed"
  fi

  mkdir -p "$hs_dir/Spoons" || fail "cannot create $hs_dir/Spoons"
  # A copy, not a symlink: the plugin's cache path changes with every plugin update.
  rm -rf "$target_spoon" && cp -R "$source_spoon" "$target_spoon" || fail "cannot copy the Spoon to $target_spoon"
  echo "Copied the Spoon to $target_spoon" >&2

  if ! grep -qE "$load_pattern" "$init_lua" 2>/dev/null; then
    # >> follows a symlinked init.lua, so the line lands in the real file (for example in a dotfiles repo).
    if [[ -s "$init_lua" ]] && [[ -n "$(tail -c 1 "$init_lua")" ]]; then echo >>"$init_lua"; fi
    printf '%s\n' "$load_line" >>"$init_lua" || fail "cannot write $init_lua"
    echo "Added the load line to $init_lua" >&2
  fi

  if grep -qE 'urlevent\.bind\(["'\'']needs-you' "$init_lua" 2>/dev/null; then
    echo "Warning: $init_lua still binds hammerspoon://needs-you by hand; remove that block or it overrides the Spoon." >&2
  fi

  killall Hammerspoon >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do hs_running || break; sleep 0.5; done
  open -g -a Hammerspoon || fail "cannot start Hammerspoon"
  for _ in 1 2 3 4 5 6 7 8 9 10; do hs_running && break; sleep 0.5; done
  sleep 2 # let init.lua load before the test URL arrives
  open -g "hammerspoon://needs-you?session=needs-you-setup-test&kind=gate&title=needs-you&reason=Setup%20works.%20Click%20to%20close." \
    >/dev/null 2>&1 || echo "Warning: could not send the test popup" >&2
}

[[ "$mode" == "install" ]] && install
if [[ ! -x "$jq" ]]; then
  # The hook needs jq too; without it no popup ever shows.
  echo '{"macos": true, "jq_installed": false, "missing": ["jq"]}'
  exit 1
fi
report
