<#
  wave.ps1 (rtl-closed-loop) - run with DUMP_WAVE, verify VCD, open GTKWave.

  Usage:
    & '<skill>\scripts\wave.ps1' -W <workspace> -Top <module> [-Bug] [-NoGui] [-Fst]

  Unlike the old script this fails if the testbench does not actually create a
  non-empty sim/wave.vcd.  Simulation is run to completion before the viewer
  opens, so the VCD is stable (no live-view race).
#>
param(
    [string]$W = '',
    [string]$Top = 'sync_fifo',
    [switch]$Bug,
    [switch]$NoGui,
    [switch]$Fst
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"

$ws = Get-RtlWorkspace $W
$cli = Join-Path $PSScriptRoot 'rtlq.py'
if (-not (Test-Path -LiteralPath $cli)) {
    Write-Host "[MISS] rtlq.py not found: $cli"
    exit 3
}

$argv = @($cli, 'sim', '--workdir', $ws, '--top', $Top, '--wave')
if ($Bug) { $argv += '--bug' }
if ($Fst) { $argv += '--fst' }

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) { & $py.Source @argv } else { & py -3.12 @argv }
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host "[FAIL] simulation/wave generation failed (rc=$code)"
    exit $code
}

$vcd = Join-Path $ws 'sim\wave.vcd'
if (-not (Test-Path -LiteralPath $vcd) -or (Get-Item -LiteralPath $vcd).Length -eq 0) {
    Write-Host "[FAIL] sim\wave.vcd was not produced; did the TB include DUMP_WAVE?"
    exit 1
}
Write-Host "VCD: $vcd"

if ($NoGui) { exit 0 }
$gtkwave = Find-RtlTool 'gtkwave.exe' $ws
if (-not $gtkwave) {
    Write-Host "[WARN] GTKWave not found; VCD is ready at $vcd"
    exit 0
}
Write-Host "== opening GTKWave =="
Start-Process -FilePath $gtkwave -ArgumentList "`"$vcd`"" -WorkingDirectory (Join-Path $ws 'sim') -Wait
exit 0
