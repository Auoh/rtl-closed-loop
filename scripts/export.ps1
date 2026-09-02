<#
  export.ps1 - 导出离线包（技能 + 便携工具链 -> zip），供无网络环境部署
  用法:
    & '<技能>\scripts\export.ps1'                                 # 默认当前目录 rtl-closed-loop-offline.zip
    & '<技能>\scripts\export.ps1' -Out D:\rtl-offline.zip
    & '<技能>\scripts\export.ps1' -NoToolchain                    # 只打技能（目标机已有工具时）
    & '<技能>\scripts\export.ps1' -ToolchainSource X:\iverilog    # 指定工具链来源（纯ASCII路径）

  目标机（无网）部署: & '<解压后的技能>\scripts\setup.ps1' -Offline -Zip <zip路径>
  注意: zip 内工具链是导出机器平台的二进制，跨平台需用对应平台的工具链。
#>
param(
    [string]$Out = '',
    [string]$ToolchainSource = '',
    [switch]$NoToolchain
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"

$skillRoot = Split-Path $PSScriptRoot -Parent

# ---- 工具链来源 ----
$toolSrc = $ToolchainSource
if (-not $toolSrc -and -not $NoToolchain) {
    $exe = Find-RtlTool 'iverilog.exe' ''
    if ($exe) { $toolSrc = Get-RtlInstallRoot $exe }
}
if ($toolSrc -and -not (Test-Path -LiteralPath (Join-Path $toolSrc 'bin\iverilog.exe'))) {
    Write-Host "工具链来源无效（缺少 bin\iverilog.exe）: $toolSrc"; exit 1
}
if (-not $toolSrc -and -not $NoToolchain) {
    Write-Host "[WARN] 未找到工具链来源，仅打包技能。可用 -ToolchainSource 指定便携目录。"
}

# ---- 暂存并压缩 ----
$outZip = $Out
if (-not $outZip) { $outZip = Join-Path (Get-Location) 'rtl-closed-loop-offline.zip' }
$tmp = Join-Path $env:TEMP ("rtl-offline-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path "$tmp\skill"      | Out-Null
New-Item -ItemType Directory -Path "$tmp\toolchain"  | Out-Null

Write-Host "== 打包技能 -> skill\rtl-closed-loop =="
robocopy $skillRoot "$tmp\skill\rtl-closed-loop" /E /NFL /NDL /NJH /NJS | Out-Null
if ($toolSrc) {
    Write-Host "== 打包工具链 ($toolSrc) -> toolchain\iverilog =="
    robocopy $toolSrc "$tmp\toolchain\iverilog" /E /NFL /NDL /NJH /NJS | Out-Null
} else {
    Write-Host "（未包含工具链）"
}

# verible（格式化工具）可选打入离线包
$fmtExe = Find-RtlTool 'verible-verilog-format.exe' ''
$veribleSrc = $null
if ($fmtExe) { $veribleSrc = Get-RtlInstallRoot $fmtExe }
if ($veribleSrc -and (Test-Path -LiteralPath (Join-Path $veribleSrc 'bin\verible-verilog-format.exe'))) {
    Write-Host "== 打包 verible ($veribleSrc) -> toolchain\verible =="
    robocopy $veribleSrc "$tmp\toolchain\verible" /E /NFL /NDL /NJH /NJS | Out-Null
} else {
    Write-Host "（未找到 verible，离线包不含格式化工具）"
}

Write-Host "== 压缩 =="
Compress-Archive -Path "$tmp\*" -DestinationPath $outZip -CompressionLevel Optimal -Force
$mb = [math]::Round((Get-Item -LiteralPath $outZip).Length / 1MB, 1)
Remove-Item -LiteralPath $tmp -Recurse -Force
Write-Host "导出完成: $outZip  ($mb MB)"
Write-Host ""
Write-Host "目标机（无网）部署:"
Write-Host "  & '<技能>\scripts\setup.ps1' -Offline -Zip '$outZip'"