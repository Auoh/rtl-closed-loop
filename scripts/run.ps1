<#
  run.ps1 (rtl-closed-loop) - compile + run the self-checking testbench.

  Usage:
    & '<skill>\scripts\run.ps1' -W <workspace> -Top <module> [-Bug] [-Wave]
                                [-Files a.v,b.v] [-Timeout 120] [-FixFormat]

  This is now a thin wrapper around rtlq.py sim:
    - all rtl/*.v and rtl/*.sv files are compiled automatically;
    - -g2012 is used by default (override with policy);
    - the run is bounded by a timeout;
    - RTL is never modified unless -FixFormat is explicitly requested;
    - -Wave checks that sim/wave.vcd is actually produced.
#>
param(
    [string]$W = '',
    [string]$Top = 'sync_fifo',
    [switch]$Bug,
    [switch]$Wave,
    [switch]$NoFormat,       # deprecated, kept for compatibility (default is no mutation)
    [switch]$FixFormat,
    [string[]]$Files = @(),
    [int]$Timeout = 0
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"

$ws = Get-RtlWorkspace $W
$cli = Join-Path $PSScriptRoot 'rtlq.py'
if (-not (Test-Path -LiteralPath $cli)) {
    Write-Host "[MISS] rtlq.py not found: $cli"
    exit 3
}

if ($FixFormat) {
    Write-Host "== explicit format fix (RTL will be modified) =="
    $fmt = Join-Path $PSScriptRoot 'format.ps1'
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $ws 'rtl') -File -ErrorAction SilentlyContinue |
                     Where-Object { $_.Extension -in '.v', '.sv' })) {
        & $fmt -File $f.FullName -Fix | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] format check still has issues: $($f.Name)"
        }
    }
}

$argv = @($cli, 'sim', '--workdir', $ws, '--top', $Top)
if ($Bug) { $argv += '--bug' }
if ($Wave) { $argv += '--wave' }
if ($Timeout -gt 0) { $argv += @('--timeout', [string]$Timeout) }
if ($Files.Count -gt 0) { $argv += '--files'; $argv += $Files }

$pyInfo = Find-RtlPython
if (-not $pyInfo) {
    Write-Host '[MISS] Python 3.8+ not found (tried python/python3/py -3.12/py -3)'
    exit 3
}
$pyArgs = @($pyInfo.Pre) + $argv
& $pyInfo.Exe @pyArgs
exit $LASTEXITCODE
