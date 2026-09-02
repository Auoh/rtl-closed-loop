<#
  run.ps1 (rtl-closed-loop 技能) - 编译 + 仿真回归
  用法:
    & '<skill>\scripts\run.ps1' -W <工作区> -Top <module> [-Bug] [-Wave] [-NoFormat]
    工作区 = 包含 rtl\ tb\ 的模块工程根（默认当前目录）
    编译前自动执行格式调整（verible + 规范修复）；-NoFormat 关闭
#>
param(
    [string]$W = '',
    [string]$Top = 'sync_fifo',
    [switch]$Bug,
    [switch]$Wave,
    [switch]$NoFormat
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"

$ws = Get-RtlWorkspace $W
$rtl = Join-Path $ws 'rtl'
$tb  = Join-Path $ws 'tb'
$sim = Join-Path $ws 'sim'
if (-not (Test-Path -LiteralPath $rtl)) { Write-Host "工作区无效（缺少 rtl\ 目录）: $ws"; exit 2 }
New-Item -ItemType Directory -Force -Path $sim | Out-Null

$iverilog = Get-RtlToolOrDie 'iverilog.exe' $ws '编译'
$vvp      = Get-RtlToolOrDie 'vvp.exe'      $ws '仿真'
Write-Host "workspace: $ws"
Write-Host "iverilog : $iverilog"

$defines = @()
if ($Bug)  { $defines += '-DINJECT_BUG=1' }
if ($Wave) { $defines += '-DDUMP_WAVE' }

$dutRtl = Join-Path $rtl "$Top.v"
$dutTb  = Join-Path $tb  "tb_$Top.v"
if (-not (Test-Path -LiteralPath $dutRtl)) { Write-Host "NOT FOUND: $dutRtl"; exit 2 }
if (-not (Test-Path -LiteralPath $dutTb))  { Write-Host "NOT FOUND: $dutTb"; exit 2 }

# 自动格式调整：每次修改后跑回归时生效（可 -NoFormat 关闭；异常不阻断编译）
if (-not $NoFormat) {
    try {
        & "$PSScriptRoot\format.ps1" -File $dutRtl -Fix | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] 编码规范检查未全绿（不影响编译）: format.ps1 exit $LASTEXITCODE"
        }
    } catch {
        Write-Host "[WARN] 自动格式化跳过: $($_.Exception.Message)"
    }
}

Write-Host "== compile ($Top) =="
& $iverilog -g2005 -s "tb_$Top" -o (Join-Path $sim "$Top.vvp") `
    @($defines) `
    $dutRtl `
    $dutTb
if ($LASTEXITCODE -ne 0) { Write-Host "COMPILE FAILED (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Write-Host "== run =="
Push-Location $sim
try {
    & $vvp "$Top.vvp" 2>&1 | Tee-Object -FilePath (Join-Path $sim "$Top.log")
} finally {
    Pop-Location
}
$code = $LASTEXITCODE
Write-Host ""
Write-Host ("vvp exit code: {0} -> {1}" -f $code, $(if ($code -eq 0) { 'PASS' } else { 'FAIL' }))
exit $code