<#
  rtlq.ps1 - rtl-closed-loop quality CLI (skill-level entry point).

  Usage (run from a workspace containing rtl/ tb/):
    & '<skill>\scripts\rtlq.ps1' doctor
    & '<skill>\scripts\rtlq.ps1' lint  -Top ch_num_gen
    & '<skill>\scripts\rtlq.ps1' sim   -Top ch_num_gen
    & '<skill>\scripts\rtlq.ps1' synth -Top ch_num_gen
    & '<skill>\scripts\rtlq.ps1' all   -Top ch_num_gen
    & '<skill>\scripts\rtlq.ps1' all   -Top ch_num_gen -W <workspace> -Strict
    & '<skill>\scripts\rtlq.ps1' compare -Top ch_num_gen [-Baseline <snapshot>]

  GNU long options pass through unchanged; PowerShell-style switches are
  translated below. Default workspace = current directory.
#>
param(
    # Explicit alias avoids the -W prefix ambiguity with PowerShell common
    # parameters (-WarningAction / -WarningVariable).
    [Alias('W')]
    [string]$Workdir = '',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$cli = Join-Path $PSScriptRoot 'rtlq.py'
if (-not (Test-Path -LiteralPath $cli)) {
    Write-Host "[MISS] rtlq.py not found: $cli"
    exit 3
}

function Find-RtlqPython {
    # Skip broken stubs (e.g. the Windows Store python3 alias exits 49).
    $cands = @(
        @{ Exe = 'python';  Pre = @() },
        @{ Exe = 'python3'; Pre = @() },
        @{ Exe = 'py';      Pre = @('-3.12') },
        @{ Exe = 'py';      Pre = @('-3') }
    )
    foreach ($c in $cands) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $pre = $c.Pre
        & $cmd.Source @pre -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return @{ Exe = $cmd.Source; Pre = $pre }
        }
    }
    return $null
}

$py = Find-RtlqPython
if (-not $py) {
    Write-Host "[MISS] Python 3.8+ not found (tried python/python3/py -3.12/py -3)"
    exit 3
}
$pyPre = $py.Pre

if (-not $Rest -or $Rest.Count -eq 0) {
    & $py.Exe @pyPre $cli --help
    exit $LASTEXITCODE
}

$map = @{
    '-W' = '--workdir'
    '-Workdir' = '--workdir'
    '-Top' = '--top'
    '-Files' = '--files'
    '-ReportDir' = '--report-dir'
    '-Policy' = '--policy'
    '-BudgetFile' = '--budget-file'
    '-Timeout' = '--timeout'
    '-Strict' = '--strict'
    '-Json' = '--json'
    '-Tb' = '--tb'
    '-TbTop' = '--tb-top'
    '-Bug' = '--bug'
    '-Wave' = '--wave'
    '-Fst' = '--fst'
    '-Grammar' = '--grammar'
    '-Sby' = '--sby'
    '-Blacklist' = '--blacklist'
    '-NoNegative' = '--no-negative'
    '-NoSynth' = '--no-synth'
    '-NoLec' = '--no-lec'
    '-NoFormal' = '--no-formal'
    '-NoFailPpa' = '--no-fail-ppa'
    '-Baseline' = '--baseline'
    '-AllowPpaRegression' = '--allow-ppa-regression'
}
$cmd = $Rest[0]
$tail = @()
if ($Workdir) { $tail += @('--workdir', $Workdir) }
for ($i = 1; $i -lt $Rest.Count; $i++) {
    $a = $Rest[$i]
    if ($map.ContainsKey($a)) { $tail += $map[$a] } else { $tail += $a }
}

$hasWs = $false
foreach ($a in $tail) {
    if ($a -eq '--workdir' -or $a -eq '-W') { $hasWs = $true; break }
}
if (-not $hasWs) { $tail = @('--workdir', (Get-Location).Path) + $tail }

& $py.Exe @pyPre $cli $cmd @tail
exit $LASTEXITCODE
