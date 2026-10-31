#!/bin/bash
# shellcheck disable=SC2329,SC2012,SC2010,SC2016,SC1091  # functions are called by name; ls on known dirs
# Read-only survey of a developer machine for the device-index skill.
# Runs on macOS /bin/bash 3.2 and Linux bash. No side effects, no secret values.

VERSION="1.1.0"
MAX=12          # items shown per list
PARTIAL=0       # set to 1 when a section times out or fails
SHELL_TO_PROBE="${SHELL:-}"
ONLY=""
SKIP=""
CHECK_INDEX=""
ALL_SECTIONS="index os mdm secrets packages languages containers clusters githosts shells envgap agents apps repos synced"
OS="$(uname -s)"

usage() {
  cat <<'EOF'
probe.sh - read-only survey of this machine for a device index

Usage:
  probe.sh [--section NAME]... [--skip NAME]... [--shell PATH] [--max N]
  probe.sh --check-index FILE
  probe.sh --help

Options:
  --section NAME      Run only this section (repeatable). Default: all.
  --skip NAME         Leave this section out (repeatable). Example: --skip envgap.
  --shell PATH        Shell whose login+interactive env is compared in "envgap".
                      Default: $SHELL. Use it when the terminal runs another shell.
  --max N             Items shown per list (default 12). Lists print count + first N.
  --check-index FILE  Check every backticked path in FILE (~/..., /..., $HOME/...) still
                      exists. Prints one "missing:" line per stale path.
  --help              This text.

Sections:
  index os mdm secrets packages languages containers clusters githosts shells
  envgap agents apps repos synced

Output (stdout): "## <section>" headings, then "key: value" lines. Notes go to stderr.
Values of environment variables are never printed (only names), except PATH entries in
"envgap". Secret files (auth.json, .env, ~/.ssh/*, credential stores) are never read.
"envgap" runs your shell's rc files (login + interactive) under a 15 s watchdog.

Exit codes:
  0  ok
  1  usage error
  2  partial: a section timed out or failed (see stderr)
  3  --check-index found missing paths

Examples:
  probe.sh
  probe.sh --section languages --section containers
  probe.sh --skip envgap --skip repos
  probe.sh --check-index ~/.device/INDEX.md
EOF
}

note() { printf 'note: %s\n' "$*" >&2; }
kv() { printf '%s: %s\n' "$1" "$2"; }
section() { printf '\n## %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# cap_list: lines on stdin -> "N: a, b, c (+M more)"
cap_list() {
  awk -v max="$MAX" 'NF { n++; if (n <= max) s = s (n > 1 ? ", " : "") $0 }
    END { if (n == 0) print "0"; else printf "%d: %s%s\n", n, s, (n > max ? " (+" n - max " more)" : "") }'
}

# run_wd SECS CMD...: run CMD with a watchdog; stdout passes through, stderr dropped.
# Returns 124 on timeout.
run_wd() {
  local secs="$1" out pid wd rc
  shift
  out="$(mktemp "${TMPDIR:-/tmp}/probe.XXXXXX")" || return 1
  "$@" >"$out" 2>/dev/null </dev/null &
  pid=$!
  ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) >/dev/null 2>&1 &
  wd=$!
  wait "$pid" 2>/dev/null
  rc=$?
  kill "$wd" 2>/dev/null
  wait "$wd" 2>/dev/null
  cat "$out"
  rm -f "$out"
  [ "$rc" -eq 137 ] && return 124
  return "$rc"
}

# run_wd2 SECS CMD...: like run_wd, but keeps stderr (version banners, auth status).
run_wd2() {
  local secs="$1"
  shift
  run_wd "$secs" sh -c '"$@" 2>&1' sh "$@"
}

timed_out() { note "$1 timed out"; PARTIAL=1; }

# On macOS without Command Line Tools, /usr/bin shims (git, python3, ...) open an
# install dialog. safe_cmd refuses them.
CLT_OK=1
if [ "$OS" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then CLT_OK=0; fi
safe_cmd() {
  local p
  p="$(command -v "$1" 2>/dev/null)" || return 1
  if [ "$CLT_OK" -eq 0 ]; then
    case "$p" in /usr/bin/git|/usr/bin/python3|/usr/bin/pip3|/usr/bin/make|/usr/bin/cc|/usr/bin/clang|/usr/bin/gcc) return 1 ;; esac
  fi
  printf '%s' "$p"
}

# link_info PATH -> "path" or "path -> target"
link_info() {
  if [ -L "$1" ]; then printf '%s -> %s' "$1" "$(readlink "$1")"; else printf '%s' "$1"; fi
}

tilde() { case "$1" in "$HOME"*) printf '~%s' "${1#"$HOME"}" ;; *) printf '%s' "$1" ;; esac; }

# ---------------------------------------------------------------- sections

s_index() {
  section index
  if [ -e "$HOME/.device" ]; then
    kv device_dir "$(tilde "$(link_info "$HOME/.device")")"
    kv files "$(ls -1 "$HOME/.device" 2>/dev/null | cap_list)"
    if [ -f "$HOME/.device/INDEX.md" ]; then
      local k v
      for k in Verified Host OS; do
        v="$(head -15 "$HOME/.device/INDEX.md" | sed -n -E "s/^[[:space:]]*-?[[:space:]]*${k}:[[:space:]]*//p" | head -1 | tr -d '\`')"
        kv "index_header_$(printf '%s' "$k" | tr 'A-Z' 'a-z')" "${v:-absent}"
      done
      kv index_lines "$(wc -l <"$HOME/.device/INDEX.md" | tr -d ' ')"
    fi
  else
    kv device_dir "absent"
  fi
  local f
  for f in "$HOME/.claude/CLAUDE.md" "$HOME"/.claude/rules/*.md "$HOME/.pi/agent/AGENTS.md" \
           "$HOME/.pi/agent/AGENTS.local.md" "$HOME/.pi/agent/CLAUDE.md" \
           "$HOME/.config/opencode/AGENTS.md" "$HOME"/.config/opencode/profiles/*/AGENTS.md \
           "$HOME/.codex/AGENTS.md" "$HOME/.gemini/GEMINI.md"; do
    [ -f "$f" ] || continue
    if grep -q -E '\.device|device index|INDEX\.md' "$f" 2>/dev/null; then
      kv "pointer $(tilde "$f")" "yes: $(grep -n -E '\.device|INDEX\.md' "$f" | head -3 | cut -c1-120 | tr '\n' ' ')"
    else
      kv "pointer $(tilde "$f")" "no"
    fi
  done
  for f in "$HOME/.config/opencode/opencode.json" "$HOME/.config/opencode/opencode.jsonc"; do
    [ -f "$f" ] || continue
    if grep -q '"instructions"' "$f"; then
      # Only the instructions array: the same file can hold API keys or passwords.
      kv "opencode_instructions $(tilde "$f")" "$(tr -d '\n' <"$f" | grep -o '"instructions"[[:space:]]*:[[:space:]]*\[[^]]*\]' | head -1 | tr -s ' ' | cut -c1-200)"
    else
      kv "opencode_instructions $(tilde "$f")" "none"
    fi
  done
}

s_os() {
  section os
  kv hostname "$(uname -n)"
  kv kernel "$OS $(uname -r) $(uname -m)"
  kv user "$(id -un)"
  kv home "$HOME"
  if [ "$OS" = "Darwin" ]; then
    kv macos "$(sw_vers -productVersion 2>/dev/null)"
    kv model "$(sysctl -n hw.model 2>/dev/null)"
    kv cpu "$(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
    kv memory_gib "$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))"
    kv command_line_tools "$([ "$CLT_OK" -eq 1 ] && xcode-select -p 2>/dev/null || echo absent)"
  else
    [ -r /etc/os-release ] && kv distro "$(. /etc/os-release; printf '%s' "$PRETTY_NAME")"
    kv cpu "$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ *//') x$(nproc 2>/dev/null)"
    kv memory_gib "$(awk '/MemTotal/ { printf "%d", $2 / 1048576 }' /proc/meminfo 2>/dev/null)"
    grep -qi microsoft /proc/version 2>/dev/null && kv wsl "yes"
  fi
}

app_present() {
  # app_present NAME... -> names of macOS apps that exist
  local n
  for n in "$@"; do
    { [ -d "/Applications/$n.app" ] || [ -d "$HOME/Applications/$n.app" ]; } && printf '%s\n' "$n"
  done
}

cmds_present() {
  # cmds_present NAME... -> names of commands on PATH
  local n
  for n in "$@"; do have "$n" && printf '%s\n' "$n"; done
  return 0
}

s_mdm() {
  section mdm
  if [ "$OS" = "Darwin" ]; then
    local enr
    enr="$(run_wd 5 profiles status -type enrollment | tr '\n' ' ')"
    kv enrollment "${enr:-unknown}"
    kv mdm_agents "$( { app_present "Self Service" "Company Portal" "Kandji Self Service" "Mosyle Self-Service" "Workspace ONE Intelligent Hub";
      [ -d /Library/Application\ Support/JAMF ] && echo Jamf; } | cap_list)"
    kv vpn_apps "$(app_present FortiClient "Cisco Secure Client" "Cisco AnyConnect Secure Mobility Client" GlobalProtect \
      Tunnelblick Viscosity WireGuard Tailscale "OpenVPN Connect" NordLayer "Cloudflare WARP" "Zscaler" "Twingate" | cap_list)"
  else
    kv vpn_cmds "$(cmds_present tailscale wg openvpn openconnect forticlient globalprotect warp-cli twingate | cap_list)"
    have nmcli && kv nm_vpn "$(run_wd 5 nmcli -t -f NAME,TYPE connection show | grep -E ':(vpn|wireguard)$' | cut -d: -f1 | cap_list)"
  fi
}

s_secrets() {
  section secrets
  if [ "$OS" = "Darwin" ]; then
    kv apps "$(app_present 1Password "1Password 7" Bitwarden KeePassXC Dashlane | cap_list)"
    [ -S "$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock" ] && kv onepassword_ssh_agent "socket present"
  fi
  kv clis "$(cmds_present op bw pass gopass vault sops age doppler infisical | cap_list)"
  kv ssh_auth_sock "$([ -n "${SSH_AUTH_SOCK:-}" ] && echo set || echo unset)"
  if safe_cmd git >/dev/null; then
    kv git_signing "gpg.format=$(git config --global --get gpg.format || echo unset) commit.gpgsign=$(git config --global --get commit.gpgsign || echo unset)"
  fi
}

s_packages() {
  section packages
  if have brew; then
    kv brew "$(command -v brew)"
    kv brew_leaves "$(run_wd 20 brew leaves | wc -l | tr -d ' ') (list: brew leaves)"
    [ "$OS" = "Darwin" ] && kv brew_casks "$(run_wd 20 brew list --cask | wc -l | tr -d ' ') (list: brew list --cask)"
  fi
  have port && kv macports "$(command -v port)"
  have dpkg-query && kv apt_packages "$(dpkg-query -f '.\n' -W 2>/dev/null | wc -l | tr -d ' ')"
  have rpm && kv rpm_packages "$(rpm -qa 2>/dev/null | wc -l | tr -d ' ')"
  have pacman && kv pacman_packages "$(pacman -Qq 2>/dev/null | wc -l | tr -d ' ')"
  have nix && kv nix "$(command -v nix)"
  have flatpak && kv flatpak_apps "$(flatpak list --app 2>/dev/null | wc -l | tr -d ' ')"
  have snap && kv snaps "$(snap list 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')"
  have pipx && kv pipx "$(run_wd 10 pipx list --short | awk '{print $1}' | cap_list)"
  [ -d "$HOME/.cargo/bin" ] && kv cargo_bin "$(ls -1 "$HOME/.cargo/bin" | cap_list)"
  [ -d "$HOME/go/bin" ] && kv go_bin "$(ls -1 "$HOME/go/bin" | cap_list)"
}

ver_line() {
  # ver_line NAME CMD... -> "path (first output line)"
  local name="$1" p v
  shift
  p="$(safe_cmd "$name")" || { printf 'absent'; return; }
  v="$(run_wd2 5 "$@" | head -1)"
  printf '%s (%s)' "$p" "${v:-version unknown}"
}

s_languages() {
  section languages
  # SDKMAN can live in ~/.sdkman, a Homebrew prefix, or elsewhere.
  local d found=""
  for d in "${SDKMAN_DIR:-}" "$HOME/.sdkman" /opt/homebrew/opt/sdkman-cli/libexec /usr/local/opt/sdkman-cli/libexec \
           /home/linuxbrew/.linuxbrew/opt/sdkman-cli/libexec /usr/local/sdkman; do
    [ -n "$d" ] && [ -d "$d/candidates" ] || continue
    found="$d"; break
  done
  if [ -n "$found" ]; then
    kv sdkman "$found"
    kv sdkman_env "SDKMAN_DIR $([ -n "${SDKMAN_DIR:-}" ] && echo set || echo unset) in this shell"
    for d in "$found"/candidates/*; do
      [ -d "$d" ] && kv "sdkman_$(basename "$d")" "$(ls -1 "$d" | grep -v '^current$' | cap_list)"
    done
  fi
  if [ "$OS" = "Darwin" ] && /usr/libexec/java_home >/dev/null 2>&1; then
    kv java_home_jdks "$(/usr/libexec/java_home -V 2>&1 | grep -E '^ +[0-9]' | sed 's/^ *//' | cut -d, -f1 | cap_list)"
    kv java_ambient "$(ver_line java java -version)"
  elif [ "$OS" != "Darwin" ] && have java; then
    kv java_ambient "$(ver_line java java -version)"
  else
    kv java_ambient "absent"
  fi
  kv java_home_env "$([ -n "${JAVA_HOME:-}" ] && echo set || echo unset)"

  local nvm_dir="${NVM_DIR:-$HOME/.nvm}"
  if [ -d "$nvm_dir/versions/node" ]; then
    kv nvm "$nvm_dir"
    kv nvm_versions "$(ls -1 "$nvm_dir/versions/node" | cap_list)"
    [ -f "$nvm_dir/alias/default" ] && kv nvm_default "$(cat "$nvm_dir/alias/default")"
  fi
  have fnm && kv fnm "$(fnm list 2>/dev/null | cap_list)"
  have volta && kv volta "$(command -v volta)"
  kv node_ambient "$(ver_line node node --version)"

  if have pyenv; then
    local proot
    proot="$(pyenv root 2>/dev/null)"
    kv pyenv "$proot"
    kv pyenv_versions "$(ls -1 "$proot/versions" 2>/dev/null | cap_list)"
    kv pyenv_global "$(run_wd 5 pyenv global | tr '\n' ' ')"
  fi
  kv python3_ambient "$(ver_line python3 python3 --version)"
  have uv && kv uv "$(ver_line uv uv --version)"
  if have poetry; then
    kv poetry "$(ver_line poetry poetry --version)"
    kv poetry_in_project "$(run_wd 10 poetry config virtualenvs.in-project)"
  fi
  have conda && kv conda "$(command -v conda)"

  have rustup && kv rustup_default "$(run_wd 5 rustup default)"
  have go && kv go "$(ver_line go go version)"
  have rbenv && kv rbenv_versions "$(rbenv versions --bare 2>/dev/null | cap_list)"
  have tfenv && kv tfenv_versions "$(run_wd2 5 tfenv list | grep -E '^[ *]*[0-9]' | tr -d ' *' | sed 's/(.*//' | cap_list)"
  have asdf && kv asdf_plugins "$(run_wd 5 asdf plugin list | cap_list)"
  have mise && kv mise "$(run_wd 5 mise ls --current | awk '{print $1" "$2}' | cap_list)"
  have jenv && kv jenv "$(command -v jenv)"
}

s_containers() {
  section containers
  if have docker; then
    kv docker_cli "$(command -v docker)"
    kv docker_context_current "$(run_wd 5 docker context show)"
    kv docker_contexts "$(run_wd 5 docker context ls -q | cap_list)"
    local sv
    sv="$(run_wd 6 docker version --format '{{.Server.Version}}')"
    kv docker_daemon "$([ -n "$sv" ] && echo "reachable ($sv)" || echo unreachable)"
  else
    kv docker_cli "absent"
  fi
  kv docker_host_env "$([ -n "${DOCKER_HOST:-}" ] && echo set || echo unset)"
  have colima && kv colima "$(run_wd 6 colima list | tail -n +2 | awk '{print $1" "$2" cpu="$4" mem="$5}' | cap_list)"
  have orb && kv orbstack "$(run_wd 5 orb status | head -1)"
  have podman && kv podman_machines "$(run_wd 6 podman machine list --format '{{.Name}} {{.LastUp}}' | cap_list)"
  have limactl && kv lima "$(run_wd 5 limactl list -q | cap_list)"
  [ "$OS" = "Darwin" ] && kv desktop_apps "$(app_present Docker OrbStack "Rancher Desktop" "Podman Desktop" | cap_list)"
  [ -f "$HOME/.testcontainers.properties" ] && \
    kv testcontainers_properties "keys: $(grep -E '^[a-z]' "$HOME/.testcontainers.properties" | cut -d= -f1 | tr '\n' ' ')"
}

s_clusters() {
  section clusters
  if have kubectl; then
    local ctx
    ctx="$(run_wd 5 kubectl config get-contexts -o name)"
    kv kube_contexts "$(printf '%s\n' "$ctx" | cap_list)"
    kv kube_prod_named "$(printf '%s\n' "$ctx" | grep -i prod | cap_list)"
    kv kube_current "$(run_wd 5 kubectl config current-context)"
  fi
  kv k8s_tools "$(cmds_present kubectl kubectx kubens helm kustomize argocd k9s stern kind minikube k3d | cap_list)"
  if have gcloud; then
    kv gcloud_configs "$(run_wd 10 gcloud config configurations list --format='value(name,is_active,properties.core.account,properties.core.project)' | tr '\t' ' ' | cap_list)"
    [ -f "$HOME/.config/gcloud/application_default_credentials.json" ] && kv gcloud_adc "file present"
  fi
  have aws && kv aws_profiles "$(run_wd 6 aws configure list-profiles | cap_list)"
  have az && kv az_account "$(run_wd 10 az account show --query name -o tsv)"
  kv iac_tools "$(cmds_present terraform tofu pulumi ansible | cap_list)"
}

s_githosts() {
  section githosts
  kv git "$(ver_line git git --version)"
  if have gh; then
    kv gh_auth "$(run_wd2 8 gh auth status | grep -E 'Logged in|account' | sed 's/^[^A-Za-z]*//' | cap_list)"
  fi
  if have glab; then
    kv glab_auth "$(run_wd2 8 glab auth status | grep -E 'Logged in' | sed 's/^[^A-Za-z]*//' | cap_list)"
  fi
  have tea && kv gitea_cli "$(command -v tea)"
  have bb && kv bitbucket_cli "$(command -v bb)"
  if safe_cmd git >/dev/null; then
    kv git_user_name "$(git config --global --get user.name || echo unset)"
    kv git_default_branch "$(git config --global --get init.defaultBranch || echo unset)"
  fi
}

s_shells() {
  section shells
  local login
  if [ "$OS" = "Darwin" ]; then
    login="$(dscl . -read "$HOME" UserShell 2>/dev/null | awk '{print $2}')"
  else
    login="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f7)"
  fi
  kv login_shell "${login:-unknown}"
  kv SHELL "${SHELL:-unset}"
  kv installed_shells "$(cmds_present zsh bash fish nu elvish xonsh pwsh | cap_list)"
  [ "$OS" = "Darwin" ] && kv terminal_apps "$(app_present WezTerm iTerm Ghostty kitty Alacritty Warp Terminal | cap_list)"
  # The shell the terminal starts (may differ from the login shell)
  local f
  for f in "$HOME/.wezterm.lua" "$HOME/.config/wezterm/wezterm.lua"; do
    [ -f "$f" ] && kv "wezterm_default_prog" "$(grep -m1 'default_prog' "$f" | sed 's/^ *//' | cut -c1-120)"
  done
  f="$HOME/.config/kitty/kitty.conf"
  [ -f "$f" ] && kv "kitty_shell" "$(grep -m1 -E '^shell ' "$f" | cut -c1-120)"
  for f in "$HOME/.config/alacritty/alacritty.toml" "$HOME/.config/ghostty/config"; do
    [ -f "$f" ] && kv "$(basename "$(dirname "$f")")_shell" "$(grep -m1 -E '^(program|command) *=' "$f" | cut -c1-120)"
  done
  local rc
  for rc in .zshenv .zprofile .zshrc .bash_profile .bashrc .profile .config/fish/config.fish \
            .config/nushell/config.nu .config/nushell/env.nu \
            "Library/Application Support/nushell/config.nu" "Library/Application Support/nushell/env.nu" \
            .config/starship.toml; do
    [ -e "$HOME/$rc" ] && kv rc "$(tilde "$(link_info "$HOME/$rc")")"
  done
}

s_envgap() {
  section envgap
  local sh="$SHELL_TO_PROBE" names here missing pathgap out
  [ -n "$sh" ] && [ -x "$sh" ] || { kv shell "not executable: ${sh:-unset}"; PARTIAL=1; return; }
  kv shell "$sh (login + interactive)"
  out="$(run_wd 15 "$sh" -l -i -c 'env; echo __PROBE_PATH__; echo "$PATH"')"
  if [ $? -eq 124 ] || [ -z "$out" ]; then timed_out "envgap ($sh -l -i -c env)"; return; fi
  names="$(printf '%s\n' "$out" | sed -n '/^__PROBE_PATH__$/q;p' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | cut -d= -f1 | sort -u)"
  here="$(env | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | cut -d= -f1 | sort -u)"
  missing="$(comm -23 <(printf '%s\n' "$names") <(printf '%s\n' "$here") \
    | grep -v -E '^(_|SHLVL|PWD|OLDPWD|TERM|TERM_.*|COLUMNS|LINES|PS[0-9]|PROMPT.*|STARSHIP_.*|ZSH.*|P9K.*|__.*|COLORTERM|ITERM.*|WEZTERM.*|LC_TERMINAL.*)$')"
  kv vars_missing_in_this_shell "$(printf '%s\n' "$missing" | MAX=40 cap_list)"
  pathgap="$(printf '%s\n' "$out" | sed -n '/^__PROBE_PATH__$/{n;p;}' | tr ':' '\n' | grep -v -x -F -f <(printf '%s\n' "$PATH" | tr ':' '\n') | awk '!seen[$0]++')"
  kv path_entries_missing "$(printf '%s\n' "$pathgap" | cap_list)"
}

json_keys() {
  # json_keys FILE EXPR -> key names, or a note when jq is absent
  if have jq; then jq -r "$2 // {} | keys[]" "$1" 2>/dev/null | cap_list; else printf 'unknown (jq absent)'; fi
}

s_agents() {
  section agents
  if [ -d "$HOME/.claude" ]; then
    kv claude_code "$(ver_line claude claude --version)"
    [ -f "$HOME/.claude/CLAUDE.md" ] && kv claude_md_imports "$(grep -E '^@' "$HOME/.claude/CLAUDE.md" | cap_list)"
    kv claude_skills "$(ls -1 "$HOME/.claude/skills" 2>/dev/null | cap_list)"
    [ -f "$HOME/.claude.json" ] && kv claude_mcp_user "$(json_keys "$HOME/.claude.json" .mcpServers)"
  fi
  if [ -d "$HOME/.pi/agent" ]; then
    kv pi "$(ver_line pi pi --version)"
    kv pi_skills "$(ls -1 "$HOME/.pi/agent/skills" 2>/dev/null | cap_list)"
    [ -f "$HOME/.pi/agent/mcp.json" ] && kv pi_mcp "$(json_keys "$HOME/.pi/agent/mcp.json" .mcpServers)"
    [ -f "$HOME/.pi/agent/settings.json" ] && have jq && \
      kv pi_skill_paths "$(jq -r '.skills // [] | .[]?' "$HOME/.pi/agent/settings.json" 2>/dev/null | cap_list)"
  fi
  if [ -d "$HOME/.config/opencode" ]; then
    kv opencode "$(ver_line opencode opencode --version)"
    kv opencode_agents_md "$([ -f "$HOME/.config/opencode/AGENTS.md" ] && echo "present (turns off the ~/.claude/CLAUDE.md fallback)" || echo absent)"
    [ -f "$HOME/.config/opencode/opencode.json" ] && kv opencode_mcp "$(json_keys "$HOME/.config/opencode/opencode.json" .mcp)"
    kv opencode_skills "$(ls -1 "$HOME/.config/opencode/skills" 2>/dev/null | cap_list)"
  fi
  kv shared_skills "$(ls -1 "$HOME/.agents/skills" 2>/dev/null | cap_list)"
  kv other_agents "$( { [ -d "$HOME/.codex" ] && echo codex; [ -d "$HOME/.gemini" ] && echo gemini;
    [ -d "$HOME/.cursor" ] && echo cursor; have aider && echo aider; have goose && echo goose; } | cap_list)"
  kv multiplexers "$(cmds_present tmux zellij screen herdr | cap_list)"
}

APP_PATTERN='IntelliJ|PyCharm|WebStorm|GoLand|Rider|CLion|RubyMine|PhpStorm|DataGrip|Fleet|Android Studio|Visual Studio Code|Cursor|Zed|Sublime|Nova|Xcode|Chrome|Firefox|Safari|Arc|Brave|Edge|Vivaldi|WezTerm|iTerm|Ghostty|kitty|Alacritty|Warp|Docker|OrbStack|Rancher|Postman|Insomnia|Bruno|DBeaver|TablePlus|Sequel|Beekeeper|Compass|GitKraken|Fork|Tower|Sourcetree|GitHub Desktop|Slack|Teams|Zoom|Discord|Mattermost|Obsidian|Notion|Logseq|Claude|ChatGPT|Raycast|Alfred'

s_apps() {
  section apps
  local all
  if [ "$OS" = "Darwin" ]; then
    all="$(ls -1 /Applications "$HOME/Applications" 2>/dev/null | grep '\.app$' | sed 's/\.app$//' | sort -u)"
  else
    all="$(ls -1 /usr/share/applications "$HOME/.local/share/applications" /var/lib/flatpak/exports/share/applications 2>/dev/null \
      | grep '\.desktop$' | sed 's/\.desktop$//' | sort -u)"
  fi
  kv total "$(printf '%s\n' "$all" | grep -c .)"
  kv dev_relevant "$(printf '%s\n' "$all" | grep -E "$APP_PATTERN" | grep -v -E 'Uninstaller|URL Handler|for Safari' | MAX=40 cap_list)"
}

s_repos() {
  section repos
  # Dirs under ~ (depth <= 3) that hold several git repos. Symlinks are not followed.
  local gits
  gits="$(run_wd 25 find "$HOME" -maxdepth 4 \
    \( -path "$HOME/Library" -o -path "$HOME/.Trash" -o -name node_modules -o -path "$HOME/.cache" \
       -o -path "$HOME/.local" -o -path "$HOME/.npm" -o -path "$HOME/.cargo" -o -path "$HOME/go/pkg" \
       -o -path "$HOME/Pictures" -o -path "$HOME/Music" -o -path "$HOME/Movies" \) -prune \
    -o -name .git -print)"
  [ $? -eq 124 ] && timed_out "repo scan"
  kv repos_found "$(printf '%s\n' "$gits" | grep -c .)"
  local roots root
  roots="$(printf '%s\n' "$gits" | grep . | sed 's|/[^/]*/\.git$||' | sort | uniq -c | sort -rn | awk '$1 >= 3')"
  printf '%s\n' "$roots" | head -"$MAX" | while read -r count root; do
    [ -n "$root" ] || continue
    local hosts
    safe_cmd git >/dev/null || { kv "root $(tilde "$root")" "$count repos"; continue; }
    hosts="$(for g in "$root"/*/.git; do
        git config --file "$g/config" --get remote.origin.url 2>/dev/null
      done | sed -E 's#^[a-z+]+://##; s#^[^@/]*@##; s#[:/].*$##' | sort | uniq -c | sort -rn | awk '{print $2" ("$1")"}' | tr '\n' ' ')"
    kv "root $(tilde "$root")" "$count repos; origin hosts: ${hosts:-none}"
  done
}

s_synced() {
  section synced
  local l t kind
  for l in "$HOME"/.[!.]* "$HOME"/* "$HOME"/.config/*; do
    [ -L "$l" ] || continue
    t="$(readlink "$l")"
    case "$t" in
      *CloudStorage/GoogleDrive*|*"Google Drive"*) kind="google-drive" ;;
      *"Mobile Documents"*|*iCloud*) kind="icloud" ;;
      *Dropbox*) kind="dropbox" ;;
      *OneDrive*) kind="onedrive" ;;
      *) kind="local" ;;
    esac
    printf '%s %s -> %s\n' "$kind" "$(tilde "$l")" "$(tilde "$t")"
  done | sort | MAX=30 cap_list | sed 's/^/links: /'
  kv dotfile_managers "$(cmds_present chezmoi stow yadm home-manager rcm | cap_list)"
  [ "$OS" = "Darwin" ] && [ -d "$HOME/Library/CloudStorage" ] && kv cloud_storage "$(ls -1 "$HOME/Library/CloudStorage" | sed 's/-.*//' | sort -u | cap_list)"
}

# ---------------------------------------------------------------- check-index

check_index() {
  local file="$1" n=0 ok=0 missing=0 skipped=0 lineno=0 line tok path first
  [ -r "$file" ] || { echo "error: cannot read $file" >&2; exit 1; }
  section "check-index $(tilde "$file")"
  while IFS= read -r line || [ -n "$line" ]; do
    lineno=$((lineno + 1))
    printf '%s\n' "$line" | grep -o '`[^`]*`' | tr -d '`' | while IFS= read -r tok; do
      case "$tok" in \~/*|\~|/*|\$HOME/*) ;; *) continue ;; esac
      path="${tok/#\~/$HOME}"
      path="${path/#\$HOME/$HOME}"
      if [ -e "$path" ]; then echo ok; continue; fi
      case "$path" in *[\*\?\<\>\{\}\$\|]*) echo skipped; continue ;; esac
      first="${path%% *}"
      first="${first%:}"
      if [ -e "$first" ]; then echo ok; else echo "missing: $tok (line $lineno)"; fi
    done
  done <"$file" >"${TMPDIR:-/tmp}/probe-check.$$"
  n=$(grep -c . "${TMPDIR:-/tmp}/probe-check.$$")
  ok=$(grep -c '^ok$' "${TMPDIR:-/tmp}/probe-check.$$")
  skipped=$(grep -c '^skipped$' "${TMPDIR:-/tmp}/probe-check.$$")
  grep '^missing:' "${TMPDIR:-/tmp}/probe-check.$$"
  missing=$(grep -c '^missing:' "${TMPDIR:-/tmp}/probe-check.$$")
  rm -f "${TMPDIR:-/tmp}/probe-check.$$"
  kv summary "checked=$n ok=$ok missing=$missing skipped=$skipped (globs/variables)"
  [ "$missing" -eq 0 ] && exit 0 || exit 3
}

# ---------------------------------------------------------------- main

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --version) echo "$VERSION"; exit 0 ;;
    --section) [ -n "${2:-}" ] || { echo "error: --section needs a name" >&2; exit 1; }; ONLY="$ONLY $2"; shift 2 ;;
    --skip) [ -n "${2:-}" ] || { echo "error: --skip needs a name" >&2; exit 1; }; SKIP="$SKIP $2"; shift 2 ;;
    --shell) [ -n "${2:-}" ] || { echo "error: --shell needs a path" >&2; exit 1; }; SHELL_TO_PROBE="$2"; shift 2 ;;
    --max) case "${2:-}" in ''|*[!0-9]*) echo "error: --max needs a number" >&2; exit 1 ;; esac; MAX="$2"; shift 2 ;;
    --check-index) [ -n "${2:-}" ] || { echo "error: --check-index needs a file" >&2; exit 1; }; CHECK_INDEX="$2"; shift 2 ;;
    *) echo "error: unknown argument '$1' (see --help)" >&2; exit 1 ;;
  esac
done

[ -n "$CHECK_INDEX" ] && check_index "$CHECK_INDEX"

for s in $ONLY $SKIP; do
  case " $ALL_SECTIONS " in *" $s "*) ;; *) echo "error: unknown section '$s'. Sections: $ALL_SECTIONS" >&2; exit 1 ;; esac
done

printf '# probe.sh %s on %s\n' "$VERSION" "$(date '+%Y-%m-%d %H:%M')"
for s in $ALL_SECTIONS; do
  [ -n "$ONLY" ] && case " $ONLY " in *" $s "*) ;; *) continue ;; esac
  case " $SKIP " in *" $s "*) continue ;; esac
  "s_$s"   # sections report their own timeouts through timed_out
done

[ "$PARTIAL" -eq 1 ] && exit 2
exit 0
