#Requires -Version 7
<#
probe.ps1 - read-only survey of a Windows developer machine for the device-index skill.
Same output contract as probe.sh: "## <section>" headings, then "key: value" lines.
Runs on PowerShell 7+ only. Windows PowerShell 5.1 stops at the #Requires line.
No side effects, no secret values: names only, never the content of config or secret files.
Keep this file ASCII only and free of PowerShell 7-only syntax, so that Windows PowerShell 5.1
can parse it and print the #Requires version error instead of a parse error.
#>
[CmdletBinding()]
param(
    [string[]]$Section = @(),
    [string[]]$Skip = @(),
    [string]$CheckIndex = '',
    [int]$Max = 12,
    [switch]$Help,
    [switch]$Version
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$ConfirmPreference = 'None'

$script:ProbeVersion = '1.3.0'
$script:Partial = $false
$script:AllSections = @('index', 'os', 'packages', 'languages', 'containers', 'shells', 'envgap',
    'secrets', 'synced', 'agents', 'apps', 'repos')
# PROBE_HOME replaces the user profile folder (for tests with a fixture home only).
$script:HomeDir = if ($env:PROBE_HOME) { $env:PROBE_HOME.TrimEnd('\') } else { [Environment]::GetFolderPath('UserProfile') }

# Exit codes (same as probe.sh)
$EXIT_OK = 0; $EXIT_USAGE = 1; $EXIT_PARTIAL = 2; $EXIT_MISSING = 3; $EXIT_NOT_WINDOWS = 4

function Show-Usage {
    @'
probe.ps1 - read-only survey of this Windows machine for a device index

Usage:
  pwsh -NoProfile -File probe.ps1 [-Section NAME[,NAME...]] [-Skip NAME[,NAME...]] [-Max N]
  pwsh -NoProfile -File probe.ps1 -CheckIndex FILE
  pwsh -NoProfile -File probe.ps1 -Help

Options:
  -Section NAME      Run only these sections (comma-separated or repeated). Default: all.
  -Skip NAME         Leave these sections out. Example: -Skip repos,apps
  -Max N             Items shown per list (default 12). Lists print count + first N.
  -CheckIndex FILE   Check that every backticked Windows path in FILE (~\..., C:\...,
                     %VAR%\..., $env:VAR\...) still exists. One "missing:" line per stale path.
  -Version           Print the probe version.
  -Help              This text.

Sections:
  index os packages languages containers shells envgap secrets synced agents apps repos

Output (stdout): "## <section>" headings, then "key: value" lines. Notes go to stderr.
Environment variable values are never printed (names only), except PATH entries in "envgap".
Config and secret files are never read for output: only their names. Exceptions, read in
memory for one field: "instructions" and MCP server key names in agent configs, git remote
hosts (credentials stripped), the INDEX.md header lines, terminal.cwd in the Hermes
config.yaml, the default_prog line of a WezTerm config, and the default profile name in
Windows Terminal settings.json.
"envgap" starts pwsh once with your profile under a 15 s watchdog.
Tests: set PROBE_HOME to a fixture folder to read it instead of the user profile.

Requires PowerShell 7+ (pwsh). Windows PowerShell 5.1 stops with a #Requires error.
Install pwsh: winget install Microsoft.PowerShell, then restart the agent harness.

Exit codes:
  0  ok
  1  usage error (also the #Requires error under Windows PowerShell 5.1)
  2  partial: a section timed out or failed (see stderr)
  3  -CheckIndex found missing paths
  4  not Windows (use probe.sh on macOS and Linux)

Examples:
  pwsh -NoProfile -File probe.ps1
  pwsh -NoProfile -File probe.ps1 -Section languages,containers
  pwsh -NoProfile -File probe.ps1 -Skip repos
  pwsh -NoProfile -File probe.ps1 -CheckIndex $HOME\.device\INDEX.md
'@
}

# ---------------------------------------------------------------- helpers

function Write-Note([string]$Text) { [Console]::Error.WriteLine("note: $Text") }
function Write-Kv([string]$Key, $Value) { [Console]::Out.WriteLine("${Key}: $Value") }
function Write-Section([string]$Name) { [Console]::Out.WriteLine(''); [Console]::Out.WriteLine("## $Name") }
function Set-Partial([string]$What) { Write-Note "$What timed out or failed"; $script:Partial = $true }

# Format-Cap: items -> "N: a, b, c (+M more)" or "0"
function Format-Cap {
    param([object[]]$Items, [int]$Limit = $Max)
    $list = @($Items | Where-Object { $null -ne $_ -and "$_".Trim() -ne '' } | ForEach-Object { "$_".Trim() })
    if ($list.Count -eq 0) { return '0' }
    $shown = ($list | Select-Object -First $Limit) -join ', '
    if ($list.Count -gt $Limit) { return "$($list.Count): $shown (+$($list.Count - $Limit) more)" }
    return "$($list.Count): $shown"
}

function Get-Cmd([string]$Name) {
    Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
}
function Test-Cmd([string]$Name) { $null -ne (Get-Cmd $Name) }
function Get-PresentCmds([string[]]$Names) { @($Names | Where-Object { Test-Cmd $_ }) }

# ~ form of a path under the user profile
function Format-Tilde([string]$Path) {
    if ($Path -and $Path.StartsWith($script:HomeDir, [StringComparison]::OrdinalIgnoreCase)) {
        return '~' + $Path.Substring($script:HomeDir.Length)
    }
    return $Path
}

# Invoke-Ext: run an external program with a watchdog. Returns stdout lines, or $null when the
# program is absent, timed out (also marks the run partial) or failed to start.
function Invoke-Ext {
    param(
        [string]$File,
        [string[]]$Arguments = @(),
        [int]$Seconds = 5,
        [switch]$MergeStderr,
        [hashtable]$Environment = @{}
    )
    $cmd = Get-Cmd $File
    if (-not $cmd) { return $null }
    $psi = [System.Diagnostics.ProcessStartInfo]::new($cmd.Source)
    foreach ($a in $Arguments) { $psi.ArgumentList.Add($a) }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    foreach ($k in $Environment.Keys) { $psi.Environment[$k] = $Environment[$k] }
    try { $p = [System.Diagnostics.Process]::Start($psi) } catch { return $null }
    try { $p.StandardInput.Close() } catch { }
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($Seconds * 1000)) {
        try { $p.Kill($true) } catch { }
        Set-Partial "$File $($Arguments -join ' ')"
        return $null
    }
    $p.WaitForExit()
    $text = $outTask.Result
    if ($MergeStderr) { $text = $text + "`n" + $errTask.Result }
    return @($text -split "`r?`n" | Where-Object { $_ -ne '' })
}

# Version line: "path (first output line)" or "absent"
function Get-VerLine([string]$Name, [string[]]$Arguments = @('--version'), [int]$Seconds = 8) {
    $c = Get-Cmd $Name
    if (-not $c) { return 'absent' }
    $out = Invoke-Ext -File $Name -Arguments $Arguments -Seconds $Seconds -MergeStderr
    $v = if ($out) { ($out | Select-Object -First 1).Trim() } else { 'version unknown' }
    return "$(Format-Tilde $c.Source) ($v)"
}

function Get-ChildNames([string]$Dir, [switch]$Directories) {
    if (-not (Test-Path -LiteralPath $Dir)) { return @() }
    if ($Directories) { return @(Get-ChildItem -LiteralPath $Dir -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object Name) }
    return @(Get-ChildItem -LiteralPath $Dir -Force -ErrorAction SilentlyContinue | ForEach-Object Name)
}

# Link info: "path" or "path -> target (junction|symlink)"
function Get-LinkInfo([System.IO.FileSystemInfo]$Item) {
    if ($Item.LinkType) {
        $t = @($Item.Target) -join ';'
        return "$(Format-Tilde $Item.FullName) -> $(Format-Tilde $t) ($($Item.LinkType.ToLower()))"
    }
    return (Format-Tilde $Item.FullName)
}

# Strip // and /* */ comments and trailing commas from JSONC, outside strings.
function Remove-JsonComments([string]$Text) {
    $sb = [System.Text.StringBuilder]::new()
    $i = 0; $n = $Text.Length; $inStr = $false
    while ($i -lt $n) {
        $c = $Text[$i]
        if ($inStr) {
            [void]$sb.Append($c)
            if ($c -eq '\' -and $i + 1 -lt $n) { [void]$sb.Append($Text[$i + 1]); $i += 2; continue }
            if ($c -eq '"') { $inStr = $false }
            $i++; continue
        }
        if ($c -eq '"') { $inStr = $true; [void]$sb.Append($c); $i++; continue }
        if ($c -eq '/' -and $i + 1 -lt $n -and $Text[$i + 1] -eq '/') {
            while ($i -lt $n -and $Text[$i] -ne "`n") { $i++ }
            continue
        }
        if ($c -eq '/' -and $i + 1 -lt $n -and $Text[$i + 1] -eq '*') {
            $i += 2
            while ($i + 1 -lt $n -and -not ($Text[$i] -eq '*' -and $Text[$i + 1] -eq '/')) { $i++ }
            $i += 2; continue
        }
        [void]$sb.Append($c); $i++
    }
    return ($sb.ToString() -replace ',(\s*[\]}])', '$1')
}

# Read a JSON/JSONC file in memory. Callers print only key names or "instructions" entries.
function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($Path)
        return (Remove-JsonComments $raw | ConvertFrom-Json -AsHashtable -Depth 64)
    } catch { return $null }
}

function Get-KeyNames($Table, [string]$Key) {
    if ($Table -is [System.Collections.IDictionary] -and $Table.Contains($Key) -and $Table[$Key] -is [System.Collections.IDictionary]) {
        return @($Table[$Key].Keys)
    }
    return @()
}

# Hermes: home folder, the raw terminal.cwd value, and the folder gateway sessions load context
# from. Reads only that one key of config.yaml; .env and auth.json are never read.
# terminal.cwd is read only at the first child indent of "terminal:" (not terminal.docker.cwd).
# Placeholders ".", "auto", "cwd" and unset resolve to the home folder on the local backend,
# unless the legacy MESSAGING_CWD is set (Hermes gateway/cwd_placeholder.py).
function Get-HermesHome {
    if ($env:HERMES_HOME) { return $env:HERMES_HOME }
    return (Join-Path $env:LOCALAPPDATA 'hermes')
}
function Get-HermesCwd {
    $cfg = Join-Path (Get-HermesHome) 'config.yaml'
    if (-not (Test-Path -LiteralPath $cfg)) { return '' }
    $inTerminal = $false; $indent = -1
    foreach ($raw in [System.IO.File]::ReadLines($cfg)) {
        $line = $raw.TrimEnd("`r")
        if ($line -match '^terminal:') { $inTerminal = $true; continue }
        if (-not $inTerminal) { continue }
        if ($line -match '^[^\s#]') { break }
        if ($line -match '^(\s+)[^\s#]') {
            $i = $Matches[1].Length
            if ($indent -lt 0) { $indent = $i }
            if ($i -eq $indent -and $line -match '^\s+cwd:\s*(.*?)(\s+#.*)?$') { return $Matches[1].Trim().Trim('"', "'") }
        }
    }
    return ''
}
function Get-HermesContextDir {
    $v = Get-HermesCwd
    if ($v -in @('', '.', 'auto', 'cwd')) { return $script:HomeDir }
    if ($v.StartsWith('~')) { return $script:HomeDir + $v.Substring(1) }
    return $v
}

function Split-PathList([string]$Value) {
    if (-not $Value) { return @() }
    return @($Value -split ';' | Where-Object { $_ } | ForEach-Object { [Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') })
}

# ---------------------------------------------------------------- sections

function Invoke-SectionIndex {
    Write-Section 'index'
    $dev = Join-Path $script:HomeDir '.device'
    if (Test-Path -LiteralPath $dev) {
        Write-Kv 'device_dir' (Get-LinkInfo (Get-Item -LiteralPath $dev -Force))
        Write-Kv 'files' (Format-Cap (Get-ChildNames $dev))
        $idx = Join-Path $dev 'INDEX.md'
        if (Test-Path -LiteralPath $idx) {
            $head = Get-Content -LiteralPath $idx -TotalCount 15 -ErrorAction SilentlyContinue
            foreach ($k in 'Verified', 'Host', 'OS') {
                $line = $head | Where-Object { $_ -match "^\s*-?\s*${k}:\s*(.+)$" } | Select-Object -First 1
                $val = if ($line -and $line -match "^\s*-?\s*${k}:\s*(.+)$") { $Matches[1].Trim(' ', '`') } else { 'absent' }
                Write-Kv "index_header_$($k.ToLower())" $val
                if ($k -eq 'Verified' -and $val -match '^\d{4}-\d{2}-\d{2}') {
                    $age = ((Get-Date).Date - [datetime]::ParseExact($val.Substring(0, 10), 'yyyy-MM-dd', $null)).Days
                    Write-Kv 'index_age_days' $age
                }
            }
            Write-Kv 'index_lines' (@(Get-Content -LiteralPath $idx -ErrorAction SilentlyContinue).Count)
        }
    } else {
        Write-Kv 'device_dir' 'absent'
    }
    $files = @(
        (Join-Path $script:HomeDir '.claude\CLAUDE.md'),
        (Join-Path $script:HomeDir '.pi\agent\AGENTS.md'),
        (Join-Path $script:HomeDir '.pi\agent\AGENTS.local.md'),
        (Join-Path $script:HomeDir '.pi\agent\CLAUDE.md'),
        (Join-Path $script:HomeDir '.config\opencode\AGENTS.md'),
        (Join-Path $script:HomeDir '.codex\AGENTS.md'),
        (Join-Path $script:HomeDir '.gemini\GEMINI.md')
    )
    $rulesDir = Join-Path $script:HomeDir '.claude\rules'
    if (Test-Path -LiteralPath $rulesDir) {
        $files += @(Get-ChildItem -LiteralPath $rulesDir -Filter '*.md' -File -Force -ErrorAction SilentlyContinue | ForEach-Object FullName)
    }
    $profilesDir = Join-Path $script:HomeDir '.config\opencode\profiles'
    if (Test-Path -LiteralPath $profilesDir) {
        $files += @(Get-ChildItem -LiteralPath $profilesDir -Directory -Force -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName 'AGENTS.md' } | Where-Object { Test-Path -LiteralPath $_ })
    }
    if (Test-Path -LiteralPath (Get-HermesHome)) {
        # Hermes: its home AGENTS.md, and the one gateway sessions load (terminal.cwd), when different.
        $h1 = Join-Path (Get-HermesHome) 'AGENTS.md'
        $h2 = Join-Path (Get-HermesContextDir) 'AGENTS.md'
        $files += $h1
        if ($h2 -ne $h1) { $files += $h2 }
    }
    foreach ($f in $files) {
        if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { continue }
        $hits = @(Select-String -LiteralPath $f -CaseSensitive -Pattern '\.device|device index|INDEX\.md' -ErrorAction SilentlyContinue |
            Select-Object -First 3 | ForEach-Object { "$($_.LineNumber):$($_.Line.Trim())".Substring(0, [Math]::Min(120, "$($_.LineNumber):$($_.Line.Trim())".Length)) })
        $kind = if ((Get-Item -LiteralPath $f -Force).LinkType) { ' (link)' } else { '' }
        Write-Kv "pointer $(Format-Tilde $f)$kind" $(if ($hits.Count) { 'yes: ' + ($hits -join ' | ') } else { 'no' })
    }
    foreach ($name in 'opencode.json', 'opencode.jsonc') {
        $f = Join-Path $script:HomeDir ".config\opencode\$name"
        if (-not (Test-Path -LiteralPath $f)) { continue }
        $cfg = Read-JsonFile $f
        if ($null -eq $cfg) { Write-Kv "opencode_instructions $(Format-Tilde $f)" 'unparsed'; continue }
        $ins = if ($cfg.Contains('instructions')) { @($cfg['instructions']) } else { @() }
        Write-Kv "opencode_instructions $(Format-Tilde $f)" $(if ($ins.Count) { Format-Cap $ins } else { 'none' })
    }
}

function Invoke-SectionOs {
    Write-Section 'os'
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    $cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
    $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction SilentlyContinue
    Write-Kv 'hostname' ([Environment]::MachineName)
    Write-Kv 'user' ([Environment]::UserName)
    Write-Kv 'home' $script:HomeDir
    if ($os) { Write-Kv 'windows' "$($os.Caption) $($cv.DisplayVersion) build $($os.BuildNumber).$($cv.UBR) $($os.OSArchitecture)" }
    if ($cs) {
        Write-Kv 'model' "$($cs.Manufacturer) $($cs.Model)"
        Write-Kv 'memory_gib' ([Math]::Round($cs.TotalPhysicalMemory / 1GB))
        Write-Kv 'domain_joined' $(if ($cs.PartOfDomain) { "yes ($($cs.Domain))" } else { 'no' })
    }
    if ($cpu) { Write-Kv 'cpu' "$($cpu.Name.Trim()) x$($cpu.NumberOfLogicalProcessors)" }
    $enroll = @(Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Enrollments' -ErrorAction SilentlyContinue |
        Where-Object { (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).ProviderID })
    Write-Kv 'mdm_enrollments' $enroll.Count
    Write-Kv 'wsl' $(if (Test-Cmd 'wsl') { 'present (see containers)' } else { 'absent' })
}

function Invoke-SectionPackages {
    Write-Section 'packages'
    $w = Get-Cmd 'winget'
    Write-Kv 'winget' $(if ($w) { "$(Format-Tilde $w.Source) (list: winget list --accept-source-agreements)" } else { 'absent' })
    $links = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'
    if (Test-Path -LiteralPath $links) { Write-Kv 'winget_links' "$(Format-Tilde $links) ($(Format-Cap (Get-ChildNames $links)))" }
    $scoop = if ($env:SCOOP) { $env:SCOOP } else { Join-Path $script:HomeDir 'scoop' }
    if (Test-Path -LiteralPath (Join-Path $scoop 'apps')) {
        Write-Kv 'scoop' "$(Format-Tilde $scoop) (list: scoop list) apps $(Format-Cap (Get-ChildNames (Join-Path $scoop 'apps') -Directories))"
    }
    $choco = if ($env:ChocolateyInstall) { $env:ChocolateyInstall } else { 'C:\ProgramData\chocolatey' }
    if (Test-Path -LiteralPath (Join-Path $choco 'lib')) {
        Write-Kv 'choco' "$choco (list: choco list) packages $((Get-ChildNames (Join-Path $choco 'lib') -Directories).Count)"
    }
    if (Test-Cmd 'npm') {
        $prefix = @(Invoke-Ext -File 'npm' -Arguments @('prefix', '-g') -Seconds 10)
        Write-Kv 'npm_global_prefix' $(if ($prefix.Count) { $prefix[0] } else { 'unknown' })
        Write-Kv 'npm_global_list' 'npm ls -g --depth=0'
    }
    if (Test-Cmd 'uv') {
        $tools = Invoke-Ext -File 'uv' -Arguments @('tool', 'list') -Seconds 10
        Write-Kv 'uv_tools' (Format-Cap @($tools | Where-Object { $_ -notmatch '^\s*-' } | ForEach-Object { ($_ -split ' ')[0] }))
    }
    if (Test-Cmd 'pipx') { Write-Kv 'pipx' (Format-Cap (Invoke-Ext -File 'pipx' -Arguments @('list', '--short') -Seconds 10)) }
    $cargo = Join-Path $script:HomeDir '.cargo\bin'
    if (Test-Path -LiteralPath $cargo) { Write-Kv 'cargo_bin' (Format-Cap (Get-ChildNames $cargo)) }
    $gobin = Join-Path $script:HomeDir 'go\bin'
    if (Test-Path -LiteralPath $gobin) { Write-Kv 'go_bin' (Format-Cap (Get-ChildNames $gobin)) }
}

function Invoke-SectionLanguages {
    Write-Section 'languages'
    # Node: NVM for Windows keeps versions in NVM_HOME and links the active one to NVM_SYMLINK.
    if ($env:NVM_HOME -or (Test-Cmd 'nvm')) {
        $nvmHome = if ($env:NVM_HOME) { $env:NVM_HOME } else { Split-Path (Get-Cmd 'nvm').Source }
        Write-Kv 'nvm_windows' (Format-Tilde $nvmHome)
        Write-Kv 'nvm_versions' (Format-Cap @(Get-ChildNames $nvmHome -Directories | Where-Object { $_ -match '^v\d' }))
        Write-Kv 'nvm_symlink' $(if ($env:NVM_SYMLINK) { "$($env:NVM_SYMLINK) (active node; global npm tools live here)" } else { 'NVM_SYMLINK unset' })
    }
    foreach ($m in 'fnm', 'volta') { if (Test-Cmd $m) { Write-Kv $m (Format-Tilde (Get-Cmd $m).Source) } }
    Write-Kv 'node_ambient' (Get-VerLine 'node')

    # Python: uv, py launcher, the Microsoft Store stub in WindowsApps.
    if (Test-Cmd 'uv') {
        Write-Kv 'uv' (Get-VerLine 'uv')
        $py = Invoke-Ext -File 'uv' -Arguments @('python', 'list', '--only-installed') -Seconds 10
        Write-Kv 'uv_pythons' (Format-Cap @($py | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -Unique))
    }
    $localBin = Join-Path $script:HomeDir '.local\bin'
    if (Test-Path -LiteralPath $localBin) {
        $onPath = (Split-PathList $env:PATH) -contains $localBin
        Write-Kv 'local_bin' "$(Format-Tilde $localBin) (on PATH: $(if ($onPath) { 'yes' } else { 'no' }); python shims: $(if (Test-Path (Join-Path $localBin 'python.exe')) { 'yes' } else { 'no' }))"
    }
    Write-Kv 'py_launcher' $(if (Test-Cmd 'py') { Format-Tilde (Get-Cmd 'py').Source } else { 'absent' })
    $pys = @(Get-Command python -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    Write-Kv 'python_on_path_order' (Format-Cap @($pys | ForEach-Object { Format-Tilde $_ }))
    if ($pys.Count -and $pys[0] -like '*\Microsoft\WindowsApps\*') {
        Write-Kv 'python_store_stub_first' 'yes (python opens the Microsoft Store; call the real interpreter or uv)'
    } elseif (@($pys | Where-Object { $_ -like '*\Microsoft\WindowsApps\*' }).Count) {
        Write-Kv 'python_store_stub_first' 'no (stub present later on PATH)'
    }
    Write-Kv 'python_ambient' (Get-VerLine 'python')

    # Java
    $jdkRoots = @('C:\Program Files\Java', 'C:\Program Files\Eclipse Adoptium', 'C:\Program Files\Microsoft',
        'C:\Program Files\Zulu', 'C:\Program Files\Amazon Corretto', (Join-Path $script:HomeDir '.jdks'))
    $jdks = foreach ($r in $jdkRoots) {
        Get-ChildNames $r -Directories | Where-Object { $_ -match 'jdk|jre|zulu|corretto|temurin|^\d' } | ForEach-Object { Format-Tilde (Join-Path $r $_) }
    }
    if (@($jdks).Count) { Write-Kv 'jdks' (Format-Cap @($jdks)) }
    Write-Kv 'java_ambient' (Get-VerLine 'java' @('-version'))
    Write-Kv 'java_home_env' $(if ($env:JAVA_HOME) { 'set' } else { 'unset' })

    if (Test-Cmd 'rustup') { Write-Kv 'rustup_default' ((Invoke-Ext -File 'rustup' -Arguments @('default') -Seconds 8) -join ' ') }
    if (Test-Cmd 'go') { Write-Kv 'go' (Get-VerLine 'go' @('version')) }
    if (Test-Cmd 'dotnet') { Write-Kv 'dotnet_sdks' (Format-Cap @(Invoke-Ext -File 'dotnet' -Arguments @('--list-sdks') -Seconds 10 | ForEach-Object { ($_ -split ' ')[0] })) }
    if (Test-Cmd 'mise') { Write-Kv 'mise' (Format-Tilde (Get-Cmd 'mise').Source) }
}

function Invoke-SectionContainers {
    Write-Section 'containers'
    if (Test-Cmd 'docker') {
        Write-Kv 'docker_cli' (Format-Tilde (Get-Cmd 'docker').Source)
        Write-Kv 'docker_context_current' ((Invoke-Ext -File 'docker' -Arguments @('context', 'show') -Seconds 5) -join ' ')
        $sv = @(Invoke-Ext -File 'docker' -Arguments @('version', '--format', '{{.Server.Version}}') -Seconds 6)
        Write-Kv 'docker_daemon' $(if ($sv.Count) { "reachable ($($sv[0]))" } else { 'unreachable (start: Docker Desktop app)' })
    } else {
        Write-Kv 'docker_cli' 'absent'
    }
    Write-Kv 'docker_host_env' $(if ($env:DOCKER_HOST) { 'set' } else { 'unset' })
    $dd = @((Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop'), 'C:\Program Files\Docker\Docker') | Where-Object { Test-Path -LiteralPath $_ }
    if ($dd) { Write-Kv 'docker_desktop' (Format-Tilde @($dd)[0]) }
    foreach ($m in 'podman', 'nerdctl', 'rdctl') { if (Test-Cmd $m) { Write-Kv $m (Format-Tilde (Get-Cmd $m).Source) } }
    if (Test-Cmd 'wsl') {
        $out = Invoke-Ext -File 'wsl' -Arguments @('--list', '--verbose') -Seconds 8 -Environment @{ WSL_UTF8 = '1' }
        $distros = @($out | Select-Object -Skip 1 | ForEach-Object {
                $parts = ($_ -replace '^\s*\*?\s*', '') -split '\s+'
                if ($parts.Count -ge 3) { "$($parts[0]) $($parts[1]) v$($parts[2])" }
            })
        Write-Kv 'wsl_distros' (Format-Cap $distros)
    }
}

function Invoke-SectionShells {
    Write-Section 'shells'
    Write-Kv 'this_shell' "pwsh $($PSVersionTable.PSVersion) ($([System.Diagnostics.Process]::GetCurrentProcess().Path))"
    try {
        $parent = (Get-Process -Id $PID).Parent
        if ($parent) { Write-Kv 'parent_process' $parent.ProcessName }
    } catch { }
    Write-Kv 'pwsh' $(if (Test-Cmd 'pwsh') { Format-Tilde (Get-Cmd 'pwsh').Source } else { 'absent (install: winget install Microsoft.PowerShell)' })
    Write-Kv 'windows_powershell' $(if (Test-Cmd 'powershell') { "$(Format-Tilde (Get-Cmd 'powershell').Source) (5.1)" } else { 'absent' })
    $gitBash = @('C:\Program Files\Git\bin\bash.exe', (Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe')) |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    Write-Kv 'git_bash' $(if ($gitBash) { $gitBash } else { 'absent' })
    Write-Kv 'claude_code_shell' $(if ($env:CLAUDE_CODE_GIT_BASH_PATH) { 'git bash (CLAUDE_CODE_GIT_BASH_PATH set)' }
        elseif ($gitBash) { 'git bash (Bash tool; Git for Windows found), PowerShell tool may also be present' }
        else { 'powershell (no Git for Windows)' })
    Write-Kv 'installed_shells' (Format-Cap (Get-PresentCmds @('pwsh', 'powershell', 'bash', 'nu', 'cmd', 'zsh', 'fish', 'elvish', 'xonsh')))
    Write-Kv 'terminal_apps' (Format-Cap (Get-PresentCmds @('wt', 'wezterm', 'alacritty', 'tabby', 'warp')))
    foreach ($f in (Join-Path $script:HomeDir '.wezterm.lua'), (Join-Path $script:HomeDir '.config\wezterm\wezterm.lua')) {
        if (Test-Path -LiteralPath $f) {
            $line = Select-String -LiteralPath $f -Pattern 'default_prog' -ErrorAction SilentlyContinue | Select-Object -First 1
            Write-Kv "wezterm_default_prog $(Format-Tilde $f)" $(if ($line) { $line.Line.Trim().Substring(0, [Math]::Min(120, $line.Line.Trim().Length)) } else { 'not set' })
        }
    }
    $wtSettings = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'
    if (Test-Path -LiteralPath $wtSettings) {
        $wt = Read-JsonFile $wtSettings
        if ($wt -and $wt.Contains('defaultProfile') -and $wt.Contains('profiles')) {
            $list = if ($wt['profiles'] -is [System.Collections.IDictionary]) { $wt['profiles']['list'] } else { $wt['profiles'] }
            $def = @($list | Where-Object { $_['guid'] -eq $wt['defaultProfile'] }) | Select-Object -First 1
            if ($def) { Write-Kv 'windows_terminal_default_profile' $def['name'] }
        }
    }
    $profiles = @(
        (Join-Path $script:HomeDir 'Documents\PowerShell\Microsoft.PowerShell_profile.ps1'),
        (Join-Path $script:HomeDir 'Documents\PowerShell\profile.ps1'),
        (Join-Path $script:HomeDir 'Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1'),
        (Join-Path $script:HomeDir '.bashrc'), (Join-Path $script:HomeDir '.bash_profile'),
        (Join-Path $env:APPDATA 'nushell\config.nu'), (Join-Path $env:APPDATA 'nushell\env.nu'),
        (Join-Path $script:HomeDir '.config\starship.toml')
    )
    foreach ($f in $profiles) {
        if (Test-Path -LiteralPath $f) { Write-Kv 'rc' (Get-LinkInfo (Get-Item -LiteralPath $f -Force)) }
    }
    $docs = [Environment]::GetFolderPath('MyDocuments')
    if ($docs -like '*OneDrive*') { Write-Kv 'documents_redirected' "yes ($(Format-Tilde $docs)); the pwsh profile lives there" }
}

function Invoke-SectionEnvgap {
    Write-Section 'envgap'
    # 1. Registry (what a new process gets) vs this process. A winget install changes the
    #    registry PATH, but running harness processes keep the old PATH until restart (winget-cli issue 2815).
    $userEnv = [Environment]::GetEnvironmentVariables('User')
    $machineEnv = [Environment]::GetEnvironmentVariables('Machine')
    $procEnv = [Environment]::GetEnvironmentVariables('Process')
    # Windows variable names are case-insensitive (Path vs PATH).
    $procNames = [System.Collections.Generic.HashSet[string]]::new([string[]]@($procEnv.Keys), [StringComparer]::OrdinalIgnoreCase)
    $regNames = @($userEnv.Keys) + @($machineEnv.Keys) | Sort-Object -Unique
    $missingVars = @($regNames | Where-Object { -not $procNames.Contains($_) })
    Write-Kv 'vars_in_registry_missing_in_this_process' (Format-Cap $missingVars 40)
    $regPath = @(Split-PathList $machineEnv['Path']) + @(Split-PathList $userEnv['Path'])
    $procPath = @(Split-PathList $env:PATH)
    $missingPath = @($regPath | Where-Object { $procPath -notcontains $_ } | Select-Object -Unique)
    Write-Kv 'path_entries_missing_in_this_process' (Format-Cap @($missingPath | ForEach-Object { Format-Tilde $_ }))
    Write-Kv 'restart_needed' $(if ($missingPath.Count -or $missingVars.Count) { 'yes (PATH is read at process start: restart the harness after a winget install)' } else { 'no' })

    # 2. PATH order traps: ssh and python resolve to the first match.
    $ssh = @(Get-Command ssh -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    Write-Kv 'ssh_order_this_process' (Format-Cap @($ssh | ForEach-Object { Format-Tilde $_ }))
    $winSsh = 'C:\Windows\System32\OpenSSH\ssh.exe'
    $gitSsh = @('C:\Program Files\Git\usr\bin\ssh.exe', (Join-Path $env:LOCALAPPDATA 'Programs\Git\usr\bin\ssh.exe')) |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    Write-Kv 'windows_openssh' $(if (Test-Path -LiteralPath $winSsh) { $winSsh } else { 'absent' })
    Write-Kv 'git_bash_ssh' $(if ($gitSsh) { "$gitSsh (Git Bash puts /usr/bin first: plain ssh is this one, not Windows OpenSSH)" } else { 'absent' })
    if ($ssh.Count -and $gitSsh -and $ssh[0] -ieq $gitSsh) {
        Write-Kv 'ssh_first_is_git' 'yes (this process inherited Git Bash PATH order)'
    }
    Write-Kv 'CLAUDE_CODE_GIT_BASH_PATH' $(if ($env:CLAUDE_CODE_GIT_BASH_PATH) { 'set' } else { 'unset' })

    # 3. What the pwsh profile adds (agent PowerShell tools often run with -NoProfile).
    if (Test-Cmd 'pwsh') {
        $script = '$e=[Environment]::GetEnvironmentVariables("Process"); "__N__"; $e.Keys; "__P__"; $env:PATH'
        $with = Invoke-Ext -File 'pwsh' -Arguments @('-NoLogo', '-NonInteractive', '-Command', $script) -Seconds 15
        $without = Invoke-Ext -File 'pwsh' -Arguments @('-NoLogo', '-NonInteractive', '-NoProfile', '-Command', $script) -Seconds 15
        if ($null -eq $with -or $null -eq $without) {
            Write-Kv 'profile_gap' 'unknown (pwsh timed out)'
        } else {
            $parse = {
                param($lines)
                $iN = [Array]::IndexOf($lines, '__N__'); $iP = [Array]::IndexOf($lines, '__P__')
                @{ Names = @($lines[($iN + 1)..($iP - 1)]); Path = @(Split-PathList ($lines[($iP + 1)..($lines.Count - 1)] -join '')) }
            }
            $a = & $parse $with; $b = & $parse $without
            $volatile = '^(PS|POWERSHELL_|__)'
            Write-Kv 'vars_added_by_pwsh_profile' (Format-Cap @($a.Names | Where-Object { $b.Names -notcontains $_ -and $_ -notmatch $volatile }) 40)
            Write-Kv 'path_added_by_pwsh_profile' (Format-Cap @($a.Path | Where-Object { $b.Path -notcontains $_ } | ForEach-Object { Format-Tilde $_ }))
        }
    }
}

function Invoke-SectionSecrets {
    Write-Section 'secrets'
    $opApp = @((Join-Path $env:LOCALAPPDATA '1Password\app\8\1Password.exe'), 'C:\Program Files\1Password\app\8\1Password.exe',
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\1Password.exe')) |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    Write-Kv 'onepassword_app' $(if ($opApp) { 'present' } else { 'absent' })
    Write-Kv 'clis' (Format-Cap (Get-PresentCmds @('op', 'bw', 'gopass', 'vault', 'sops', 'age', 'doppler', 'infisical', 'keepassxc-cli')))
    $pipes = @()
    try { $pipes = [System.IO.Directory]::GetFiles('\\.\pipe\') } catch { }
    Write-Kv 'openssh_agent_pipe' $(if ($pipes -contains '\\.\pipe\openssh-ssh-agent') { 'present (\\.\pipe\openssh-ssh-agent; 1Password or the ssh-agent service)' } else { 'absent' })
    $svc = Get-Service ssh-agent -ErrorAction SilentlyContinue
    Write-Kv 'ssh_agent_service' $(if ($svc) { "$($svc.Status) ($($svc.StartType))" } else { 'absent' })
    Write-Kv 'ssh_auth_sock' $(if ($env:SSH_AUTH_SOCK) { 'set' } else { 'unset' })
    Write-Kv 'ssh_config_file' $(if (Test-Path -LiteralPath (Join-Path $script:HomeDir '.ssh\config')) { 'present (not read)' } else { 'absent' })
    if (Test-Cmd 'git') {
        $g = { param($k) $v = @(Invoke-Ext -File 'git' -Arguments @('config', '--global', '--get', $k) -Seconds 5); if ($v.Count) { $v[0] } else { 'unset' } }
        Write-Kv 'git_ssh_command' (& $g 'core.sshCommand')
        Write-Kv 'git_signing' "gpg.format=$(& $g 'gpg.format') commit.gpgsign=$(& $g 'commit.gpgsign')"
        Write-Kv 'git_credential_helper' (& $g 'credential.helper')
    }
}

function Invoke-SectionSynced {
    Write-Section 'synced'
    $dirs = @($script:HomeDir, (Join-Path $script:HomeDir '.config'), (Join-Path $script:HomeDir '.claude'),
        (Join-Path $script:HomeDir '.claude\skills'), (Join-Path $script:HomeDir '.agents\skills'),
        (Join-Path $script:HomeDir '.config\opencode'), (Join-Path $script:HomeDir '.pi\agent'))
    $links = foreach ($d in $dirs) {
        if (-not (Test-Path -LiteralPath $d)) { continue }
        # System junctions ("Application Data", "Cookies", ...) carry the System attribute: skip them.
        Get-ChildItem -LiteralPath $d -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.LinkType -and -not ($_.Attributes -band [System.IO.FileAttributes]::System) } | ForEach-Object {
            $t = @($_.Target) -join ';'
            $kind = switch -Wildcard ($t) {
                '*OneDrive*' { 'onedrive' } '*Google Drive*' { 'google-drive' } '*GoogleDrive*' { 'google-drive' }
                '*Dropbox*' { 'dropbox' } '*iCloud*' { 'icloud' } default { 'local' }
            }
            "$kind $(Get-LinkInfo $_)"
        }
    }
    Write-Kv 'links' (Format-Cap @($links | Sort-Object) 30)
    Write-Kv 'onedrive' $(if ($env:OneDrive) { 'present' } else { 'absent' })
    Write-Kv 'dotfile_managers' (Format-Cap (Get-PresentCmds @('chezmoi', 'yadm', 'dotbot', 'stow')))
}

function Invoke-SectionAgents {
    Write-Section 'agents'
    $claudeDir = Join-Path $script:HomeDir '.claude'
    if ((Test-Path -LiteralPath $claudeDir) -or (Test-Cmd 'claude')) {
        Write-Kv 'claude_code' (Get-VerLine 'claude')
        $md = Join-Path $claudeDir 'CLAUDE.md'
        if (Test-Path -LiteralPath $md) { Write-Kv 'claude_md_imports' (Format-Cap @(Select-String -LiteralPath $md -Pattern '^@' | ForEach-Object { $_.Line.Trim() })) }
        Write-Kv 'claude_rules' (Format-Cap @(Get-ChildNames (Join-Path $claudeDir 'rules')))
        Write-Kv 'claude_skills' (Format-Cap (Get-ChildNames (Join-Path $claudeDir 'skills')))
        $cj = Read-JsonFile (Join-Path $script:HomeDir '.claude.json')
        if ($cj) { Write-Kv 'claude_mcp_user' (Format-Cap (Get-KeyNames $cj 'mcpServers')) }
    }
    $ocDir = Join-Path $script:HomeDir '.config\opencode'
    if ((Test-Path -LiteralPath $ocDir) -or (Test-Cmd 'opencode')) {
        Write-Kv 'opencode' (Get-VerLine 'opencode' @('--version') 15)
        Write-Kv 'opencode_agents_md' $(if (Test-Path -LiteralPath (Join-Path $ocDir 'AGENTS.md')) { 'present' } else { 'absent' })
        $cfgFiles = @('opencode.json', 'opencode.jsonc') | Where-Object { Test-Path -LiteralPath (Join-Path $ocDir $_) }
        Write-Kv 'opencode_config' (Format-Cap @($cfgFiles))
        foreach ($c in $cfgFiles) {
            $cfg = Read-JsonFile (Join-Path $ocDir $c)
            if ($cfg) { Write-Kv "opencode_mcp $c" (Format-Cap (Get-KeyNames $cfg 'mcp')) }
        }
        Write-Kv 'opencode_instruction_dir' (Format-Cap (Get-ChildNames (Join-Path $ocDir 'instructions')))
        Write-Kv 'opencode_profiles' (Format-Cap (Get-ChildNames (Join-Path $ocDir 'profiles') -Directories))
        Write-Kv 'opencode_config_dir_env' $(if ($env:OPENCODE_CONFIG_DIR) { 'set (a profile AGENTS.md there is read first)' } else { 'unset' })
        Write-Kv 'opencode_skills' (Format-Cap (Get-ChildNames (Join-Path $ocDir 'skills')))
        Write-Kv 'opencode_shell' 'Windows PowerShell 5.1 observed on OpenCode v2 (run pwsh -NoProfile -File for pwsh scripts)'
    }
    $piDir = Join-Path $script:HomeDir '.pi\agent'
    if ((Test-Path -LiteralPath $piDir) -or (Test-Cmd 'pi')) {
        Write-Kv 'pi' (Get-VerLine 'pi')
        Write-Kv 'pi_skills' (Format-Cap (Get-ChildNames (Join-Path $piDir 'skills')))
        $local = Join-Path $piDir 'AGENTS.local.md'
        if (Test-Path -LiteralPath $local) { Write-Kv 'pi_agents_local_md' 'present (local overlay; AGENTS.md may be generated)' }
    }
    $hermesHome = Get-HermesHome
    if ((Test-Path -LiteralPath $hermesHome) -or (Test-Cmd 'hermes')) {
        $hermesExe = Join-Path $hermesHome 'bin\hermes.exe'
        if (Test-Cmd 'hermes') {
            Write-Kv 'hermes' (Get-VerLine 'hermes' @('--version') 10)
        } elseif (Test-Path -LiteralPath $hermesExe) {
            $hv = @(Invoke-Ext -File $hermesExe -Arguments @('--version') -Seconds 10 -MergeStderr) | Select-Object -First 1
            Write-Kv 'hermes' "$(Format-Tilde $hermesExe), not on this PATH ($(if ($hv) { $hv.Trim() } else { 'version unknown' }))"
        } else {
            Write-Kv 'hermes' 'absent'
        }
        Write-Kv 'hermes_home' (Format-Tilde $hermesHome)
        $hc = Get-HermesCwd
        $hcText = if ($hc -in @('', '.', 'auto', 'cwd')) {
            "$(if ($hc) { $hc } else { 'unset' }) (gateway sessions load context from the home folder)"
        } else { Format-Tilde $hc }
        Write-Kv 'hermes_terminal_cwd' $hcText
        Write-Kv 'hermes_skills' (Format-Cap (Get-ChildNames (Join-Path $hermesHome 'skills') -Directories))
    }
    Write-Kv 'shared_skills' (Format-Cap (Get-ChildNames (Join-Path $script:HomeDir '.agents\skills')))
    $other = @()
    foreach ($pair in @(@('.codex', 'codex'), @('.gemini', 'gemini'), @('.cursor', 'cursor'), @('.config\zed', 'zed'))) {
        if (Test-Path -LiteralPath (Join-Path $script:HomeDir $pair[0])) { $other += $pair[1] }
    }
    $other += Get-PresentCmds @('aider', 'goose')
    Write-Kv 'other_agents' (Format-Cap $other)
    Write-Kv 'multiplexers' (Format-Cap (Get-PresentCmds @('herdr', 'wezterm', 'zellij', 'tmux')))
}

$script:AppPattern = 'IntelliJ|PyCharm|WebStorm|GoLand|Rider|CLion|RubyMine|PhpStorm|DataGrip|Fleet|Android Studio|Visual Studio|Cursor|Zed|Sublime|Notepad\+\+|Chrome|Firefox|Brave|Edge|Vivaldi|WezTerm|Windows Terminal|Alacritty|Docker|Rancher|Podman|Postman|Insomnia|Bruno|DBeaver|HeidiSQL|TablePlus|Beekeeper|Compass|GitKraken|Fork|Sourcetree|GitHub Desktop|Git version|Slack|Teams|Zoom|Discord|Obsidian|Notion|Logseq|Claude|ChatGPT|PowerToys|1Password|WinSCP|PuTTY|Tailscale|WireGuard|OpenVPN|FortiClient|Cisco'

function Invoke-SectionApps {
    Write-Section 'apps'
    $keys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
    $all = @(Get-ItemProperty $keys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName } |
        ForEach-Object { ($_.DisplayName -replace '\s+\(?\d+(\.\d+)+.*$', '').Trim() } | Sort-Object -Unique)
    Write-Kv 'total' "$($all.Count) (list: winget list, or Settings > Apps)"
    Write-Kv 'dev_relevant' (Format-Cap @($all | Where-Object { $_ -match $script:AppPattern -and $_ -notmatch 'Redistributable|Runtime|Update|Helper|SDK' }) 40)
}

function Invoke-SectionRepos {
    Write-Section 'repos'
    Write-Kv 'git' (Get-VerLine 'git')
    Write-Kv 'git_host_clis' (Format-Cap (Get-PresentCmds @('gh', 'glab', 'tea', 'az')))
    # Scan the profile and each fixed drive root, depth <= 3, for .git folders. Time budget 25 s.
    $roots = @($script:HomeDir) + @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction SilentlyContinue | ForEach-Object { "$($_.DeviceID)\" })
    $skip = '^(AppData|node_modules|target|vendor|venv|dist|build|bin|obj|Windows|Program Files|Program Files \(x86\)|ProgramData|\$Recycle\.Bin|System Volume Information|Recovery|PerfLogs|\.cache|\.npm|\.cargo|\.rustup|scoop|go|OneDrive.*|Users|\.vscode|\.nuget|\.gradle|\.m2)$'
    $deadline = (Get-Date).AddSeconds(25)
    $gits = [System.Collections.Generic.List[string]]::new()
    $queue = [System.Collections.Generic.Queue[object]]::new()
    foreach ($r in $roots) { $queue.Enqueue(@($r, 0)) }
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $opts = [System.IO.EnumerationOptions]::new()
    $opts.IgnoreInaccessible = $true
    $opts.AttributesToSkip = [System.IO.FileAttributes]::ReparsePoint
    while ($queue.Count -gt 0) {
        if ((Get-Date) -gt $deadline) { Set-Partial 'repo scan'; break }
        $item = $queue.Dequeue(); $dir = $item[0]; $depth = $item[1]
        if (-not $seen.Add($dir.TrimEnd('\'))) { continue }
        try { $subs = [System.IO.Directory]::GetDirectories($dir, '*', $opts) } catch { continue }
        $names = @($subs | ForEach-Object { [System.IO.Path]::GetFileName($_) })
        # A repo: record it and do not descend into it.
        if ($names -contains '.git' -or [System.IO.File]::Exists([System.IO.Path]::Combine($dir, '.git'))) { $gits.Add($dir.TrimEnd('\')); continue }
        if ($depth -ge 3) { continue }
        for ($i = 0; $i -lt $subs.Count; $i++) {
            $name = $names[$i]
            if ($name.StartsWith('.') -or $name -match $skip) { continue }
            $queue.Enqueue(@($subs[$i], $depth + 1))
        }
    }
    Write-Kv 'repos_found' $gits.Count
    $groups = $gits | Group-Object { Split-Path $_ -Parent } | Where-Object { $_.Count -ge 3 } | Sort-Object Count -Descending | Select-Object -First $Max
    foreach ($g in $groups) {
        $origins = foreach ($repo in $g.Group) {
            $cfg = Join-Path $repo '.git\config'
            if (-not (Test-Path -LiteralPath $cfg)) { continue }
            $url = $null; $inOrigin = $false
            foreach ($line in [System.IO.File]::ReadLines($cfg)) {
                if ($line -match '^\s*\[') { $inOrigin = $line -match '^\s*\[remote "origin"\]' ; continue }
                if ($inOrigin -and $line -match '^\s*url\s*=\s*(.+)$') { $url = $Matches[1].Trim(); break }
            }
            if (-not $url) { 'none'; continue }
            # host/first-group only; scheme, user and any credentials are stripped
            $u = $url -replace '^[a-z+]+://', '' -replace '^[^@/]*@', '' -replace '^([^:/]+):\d+/', '$1/'
            $hostName = ($u -split '[:/]')[0]
            $grp = ($u -replace '^[^:/]+[:/]', '' -split '/')[0]
            if ($grp -and $grp -notmatch '\.git$') { "$hostName/$grp" } else { $hostName }
        }
        $summary = ($origins | Group-Object | Sort-Object Count -Descending | Select-Object -First $Max | ForEach-Object { "$($_.Name) ($($_.Count))" }) -join ', '
        Write-Kv "root $(Format-Tilde $g.Name)" "$($g.Count) repos; origins: $(if ($summary) { $summary } else { 'none' })"
    }
}

# ---------------------------------------------------------------- check-index

function Resolve-IndexPath([string]$Token) {
    $t = $Token
    if ($t -match '^~([\\/]|$)') { $t = $script:HomeDir + $t.Substring(1) }
    elseif ($t -match '^\$HOME([\\/]|$)') { $t = $script:HomeDir + $t.Substring(5) }
    elseif ($t -match '^\$env:([A-Za-z_][A-Za-z0-9_]*)(.*)$') {
        $v = [Environment]::GetEnvironmentVariable($Matches[1])
        if (-not $v) { return $null }
        $t = $v + $Matches[2]
    }
    $t = [Environment]::ExpandEnvironmentVariables($t)
    return $t
}

function Invoke-CheckIndex([string]$File) {
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) {
        [Console]::Error.WriteLine("error: cannot read $File")
        exit $EXIT_USAGE
    }
    Write-Section "check-index $(Format-Tilde (Resolve-Path -LiteralPath $File).Path)"
    $n = 0; $ok = 0; $missing = 0; $skipped = 0; $lineNo = 0
    foreach ($line in [System.IO.File]::ReadLines((Resolve-Path -LiteralPath $File).Path)) {
        $lineNo++
        foreach ($m in [regex]::Matches($line, '`([^`]+)`')) {
            $tok = $m.Groups[1].Value
            if ($tok -notmatch '^(~([\\/]|$)|\$HOME[\\/]|\$env:|%[A-Za-z_]+%|[A-Za-z]:[\\/]|\\\\)') { continue }
            $n++
            if ($tok -match '[*?<>{}|]') { $skipped++; continue }
            $path = Resolve-IndexPath $tok
            if (-not $path -or $path -match '%[A-Za-z_]+%') { $skipped++; continue }
            if (Test-Path -LiteralPath $path) { $ok++; continue }
            # "C:\Program Files\Git (portable)": drop trailing words until a prefix exists.
            $words = $path -split ' '
            $found = $false
            for ($k = $words.Count - 1; $k -ge 1 -and -not $found; $k--) {
                $prefix = ($words[0..($k - 1)] -join ' ').TrimEnd(':', ',', '.')
                if (Test-Path -LiteralPath $prefix) { $found = $true }
            }
            if ($found) { $ok++; continue }
            $missing++
            [Console]::Out.WriteLine("missing: $tok (line $lineNo)")
        }
    }
    Write-Kv 'summary' "checked=$n ok=$ok missing=$missing skipped=$skipped (globs/placeholders/unset variables)"
    if ($missing -eq 0) { exit $EXIT_OK } else { exit $EXIT_MISSING }
}

# ---------------------------------------------------------------- main

if ($Help) { Show-Usage; exit $EXIT_OK }
if ($Version) { [Console]::Out.WriteLine($script:ProbeVersion); exit $EXIT_OK }
if (-not $IsWindows) {
    [Console]::Error.WriteLine('error: probe.ps1 is for Windows. On macOS and Linux run: bash scripts/probe.sh')
    exit $EXIT_NOT_WINDOWS
}
if ([Console]::IsOutputRedirected) { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) }
if ($Max -lt 1) { [Console]::Error.WriteLine('error: -Max needs a number >= 1'); exit $EXIT_USAGE }

if ($CheckIndex) { Invoke-CheckIndex $CheckIndex }

$Section = @($Section | ForEach-Object { $_ -split ',' } | Where-Object { $_ } | ForEach-Object { $_.Trim().ToLower() })
$Skip = @($Skip | ForEach-Object { $_ -split ',' } | Where-Object { $_ } | ForEach-Object { $_.Trim().ToLower() })
foreach ($s in @($Section) + @($Skip)) {
    if ($script:AllSections -notcontains $s) {
        [Console]::Error.WriteLine("error: unknown section '$s'. Sections: $($script:AllSections -join ' ')")
        exit $EXIT_USAGE
    }
}

[Console]::Out.WriteLine("# probe.ps1 $($script:ProbeVersion) on $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
foreach ($s in $script:AllSections) {
    if ($Section.Count -and $Section -notcontains $s) { continue }
    if ($Skip -contains $s) { continue }
    $fn = 'Invoke-Section' + $s.Substring(0, 1).ToUpper() + $s.Substring(1)
    try { & $fn } catch { Write-Note "section $s failed: $($_.Exception.Message)"; $script:Partial = $true }
}

if ($script:Partial) { exit $EXIT_PARTIAL }
exit $EXIT_OK
