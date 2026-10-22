<#
  export.ps1 - 导出离线包（技能 + 便携工具链 -> zip），供无网络环境部署
  用法:
    & '<技能>\scripts\export.ps1'                                 # 默认当前目录 rtl-closed-loop-offline.zip
    & '<技能>\scripts\export.ps1' -Out D:\rtl-offline.zip
    & '<技能>\scripts\export.ps1' -NoToolchain                    # 只打技能（目标机已有工具时）
    & '<技能>\scripts\export.ps1' -ToolchainSource X:\iverilog    # 指定工具链来源（纯ASCII路径）
    & '<技能>\scripts\export.ps1' -QualityLiteSource X:\quality-lite  # 指定 Yosys/slang/sby 来源
    & '<技能>\scripts\export.ps1' -NoToolchain                    # 只打技能（不含任何工具链）

  目标机（无网）部署: & '<解压后的技能>\scripts\setup.ps1' -Offline -Zip <zip路径>
  注意: zip 内工具链是导出机器平台的二进制，跨平台需用对应平台的工具链。
#>
param(
    [string]$Out = '',
    [string]$ToolchainSource = '',
    [string]$QualityLiteSource = '',
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
robocopy $skillRoot "$tmp\skill\rtl-closed-loop" /E /NFL /NDL /NJH /NJS `
    /XD ".git" "__pycache__" /XF "*.pyc" | Out-Null
if ($toolSrc) {
    Write-Host "== 打包工具链 ($toolSrc) -> toolchain\iverilog =="
    robocopy $toolSrc "$tmp\toolchain\iverilog" /E /NFL /NDL /NJH /NJS | Out-Null
} else {
    Write-Host "（未包含工具链）"
}

# verible（格式化工具）可选打入离线包
if (-not $NoToolchain) {
    $fmtExe = Find-RtlTool 'verible-verilog-format.exe' ''
    $veribleSrc = $null
    if ($fmtExe) { $veribleSrc = Get-RtlInstallRoot $fmtExe }
    if ($veribleSrc -and (Test-Path -LiteralPath (Join-Path $veribleSrc 'bin\verible-verilog-format.exe'))) {
        Write-Host "== 打包 verible ($veribleSrc) -> toolchain\verible =="
        robocopy $veribleSrc "$tmp\toolchain\verible" /E /NFL /NDL /NJH /NJS | Out-Null
    } else {
        Write-Host "（未找到 verible，离线包不含格式化工具）"
    }
}

# quality-lite（Yosys + slang + sby）可选打入离线包
if (-not $NoToolchain) {
    $qSrc = $QualityLiteSource
    if (-not $qSrc) { $qSrc = Get-RtlQualityRoot (Get-Location).Path }
    if ($qSrc -and -not (Test-Path -LiteralPath (Join-Path $qSrc 'yosys\bin\yosys.exe'))) {
        $alt = Join-Path $qSrc 'quality-lite'
        if (Test-Path -LiteralPath (Join-Path $alt 'yosys\bin\yosys.exe')) { $qSrc = $alt }
    }
    if ($qSrc -and (Test-Path -LiteralPath (Join-Path $qSrc 'yosys\bin\yosys.exe'))) {
        $qSrc = (Resolve-Path -LiteralPath $qSrc).Path
        Write-Host "== 打包 quality-lite ($qSrc) -> toolchain\quality-lite =="
        robocopy $qSrc "$tmp\toolchain\quality-lite" /E /NFL /NDL /NJH /NJS `
            /XD "__pycache__" /XF "*.pyc" | Out-Null
    } else {
        Write-Host "（未找到 quality-lite，离线包不含 Yosys/slang/sby）"
    }
}

# 工具清单/哈希（可选）
foreach ($m in @((Join-Path (Get-Location).Path 'tools\manifest.json'),
                 (Join-Path $skillRoot 'tools\manifest.json'))) {
    if (Test-Path -LiteralPath $m) {
        Copy-Item -LiteralPath $m -Destination "$tmp\toolchain\manifest.json" -Force
        Write-Host "== 打包工具清单 ($m) -> toolchain\manifest.json =="
        break
    }
}

Write-Host "== 压缩 =="
# Compress to a temp file first: antivirus may briefly lock freshly copied
# binaries, and a failed -Force compression must not destroy the previous zip.
$tmpZip = "$outZip.tmp-" + [guid]::NewGuid().ToString('N') + ".zip"
$ok = $false
for ($i = 1; $i -le 5; $i++) {
    try {
        Compress-Archive -Path "$tmp\*" -DestinationPath $tmpZip -CompressionLevel Optimal -Force
        $ok = $true
        break
    } catch {
        Write-Host ("[WARN] 压缩失败（第 {0}/5 次）: {1}" -f $i, $_.Exception.Message)
        Start-Sleep -Seconds 2
    }
}
if (-not $ok) {
    Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tmp -Recurse -Force
    Write-Host "压缩失败；保留原包（如有）"
    exit 1
}
Move-Item -LiteralPath $tmpZip -Destination $outZip -Force
$mb = [math]::Round((Get-Item -LiteralPath $outZip).Length / 1MB, 1)
Remove-Item -LiteralPath $tmp -Recurse -Force
Write-Host "导出完成: $outZip  ($mb MB)"
Write-Host ""
Write-Host "目标机（无网）部署:"
Write-Host "  & '<技能>\scripts\setup.ps1' -Offline -Zip '$outZip'"