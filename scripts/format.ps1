<#
  编码规范检查 / 自动格式化（format）
  用法:
    .\format.ps1 -W <工作区> -Top <module>                  # 仅检查（退出码 0 = FORMAT OK）
    .\format.ps1 -W <工作区> -Top <module> -Report <out.md> # 检查并生成 Markdown 报告（含修改建议）
    .\format.ps1 -W <工作区> -Top <module> -Fix             # verible 格式化 + 安全规范修复 + 复查
    .\format.ps1 -File <rtl.v> [-Fix] [-Report <out.md>]
#>
param(
    [string]$W = (Get-Location).Path,
    [string]$Top = '',
    [string]$File = '',
    [switch]$Fix,
    [string]$Report = ''
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"
$pyScript = Join-Path $PSScriptRoot 'format_check.py'
$pyInfo = Find-RtlPython
if (-not $pyInfo) {
    Write-Host '[MISS] Python 3.8+ not found (tried python/python3/py -3.12/py -3)'
    exit 3
}
$pyExe = $pyInfo.Exe
$pyPre = $pyInfo.Pre

if (-not $File) {
    if (-not $Top) {
        Write-Host 'use -Top <module> (with -W <workspace>) or -File <rtl.v>'
        exit 2
    }
    $File = Join-Path $W "rtl\$Top.v"
}
if (-not (Test-Path -LiteralPath $File)) {
    Write-Host "[MISS] RTL file not found: $File"
    exit 2
}

$reportArgs = @()
if ($Report) {
    $repDir = Split-Path -Parent $Report
    if ($repDir -and -not (Test-Path -LiteralPath $repDir)) {
        New-Item -ItemType Directory -Path $repDir -Force | Out-Null
    }
    $reportArgs = @('--report', $Report)
}

if (-not $Fix) {
    & $pyExe @pyPre $pyScript -f $File @reportArgs
    exit $LASTEXITCODE
}

$fmt = Find-RtlTool 'verible-verilog-format.exe' $W
if (-not $fmt) {
    Write-Host "[WARN] 未找到 verible-verilog-format，仅应用安全规范修复（R5/R7）"
    & $pyExe @pyPre $pyScript --fix -f $File @reportArgs
    exit $LASTEXITCODE
}
$flags = @('--indentation_spaces=4', '--wrap_end_else_clauses', '--inplace')

Write-Host "verible : $fmt"
& $fmt @flags $File
if ($LASTEXITCODE -ne 0) { Write-Host "[ERR] verible 格式化失败"; exit $LASTEXITCODE }
& $pyExe @pyPre $pyScript --fix -f $File
& $fmt @flags $File        # 第二次：规则修复后重新对齐
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pyExe @pyPre $pyScript -f $File @reportArgs
exit $LASTEXITCODE