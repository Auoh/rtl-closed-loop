<#
  wave.ps1 (rtl-closed-loop 技能) - 后台仿真 + GTKWave 波形
  用法:
    & '<skill>\scripts\wave.ps1' -W <工作区> -Top <module> [-Bug] [-NoGui]
  实时加观测信号: GTKWave File->Enable Live View；搜索框输入信号名拖入即可
#>
param(
    [string]$W = '',
    [string]$Top = 'sync_fifo',
    [switch]$Bug,
    [switch]$NoGui
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"

$ws = Get-RtlWorkspace $W
$sim = Join-Path $ws 'sim'
$rtl = Join-Path $ws 'rtl'
$tb  = Join-Path $ws 'tb'
if (-not (Test-Path -LiteralPath $rtl)) { Write-Host "工作区无效（缺少 rtl\ 目录）: $ws"; exit 2 }
New-Item -ItemType Directory -Force -Path $sim | Out-Null

$iverilog = Get-RtlToolOrDie 'iverilog.exe' $ws '编译'
$vvp      = Get-RtlToolOrDie 'vvp.exe'      $ws '仿真'
$gtkwave  = Find-RtlTool 'gtkwave.exe' $ws

$defines = @()
if ($Bug) { $defines += '-DINJECT_BUG=1' }
$defines += '-DDUMP_WAVE'

Write-Host "== compile ($Top) =="
& $iverilog -g2005 -s "tb_$Top" -o (Join-Path $sim "$Top.vvp") `
    @($defines) `
    (Join-Path $rtl "$Top.v") `
    (Join-Path $tb "tb_$Top.v")
if ($LASTEXITCODE -ne 0) { Write-Host "COMPILE FAILED"; exit $LASTEXITCODE }

$vcd = Join-Path $sim 'wave.vcd'
Remove-Item -LiteralPath $vcd -ErrorAction SilentlyContinue

Write-Host "== 后台启动仿真 =="
$simProc = Start-Process -FilePath $vvp -ArgumentList "$Top.vvp" `
    -WorkingDirectory $sim -WindowStyle Hidden -PassThru
Write-Host "仿真 PID=$($simProc.Id) 运行中，VCD: $vcd"

if ($NoGui -or -not $gtkwave) {
    if (-not $gtkwave) { Write-Host "GTKWave 未找到，仅生成 VCD" }
    $simProc.WaitForExit()
    Write-Host "仿真结束，退出码=$($simProc.ExitCode)"
    exit $simProc.ExitCode
}

Write-Host "== 打开 GTKWave（关闭窗口后脚本结束）=="
Write-Host "提示: File -> Enable Live View 实时刷新；搜索框输入 dut.wptr 等拖入波形区"
Start-Process -FilePath $gtkwave -ArgumentList "`"$vcd`"" -WorkingDirectory $sim -Wait

if (-not $simProc.HasExited) { $simProc.WaitForExit() }
Write-Host "完成。波形文件: $vcd"