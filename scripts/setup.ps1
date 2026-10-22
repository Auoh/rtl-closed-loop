<#
  setup.ps1 (rtl-closed-loop 技能) - 工具链检测 / 部署（迁移用）
  用法:
    & '<skill>\scripts\setup.ps1'            # 检测 iverilog/vvp/gtkwave/python
    & '<skill>\scripts\setup.ps1' -Install   # 把便携工具链部署到 $HOME\.codex\rtl-toolchain
    & '<skill>\scripts\setup.ps1' -Offline              # 无网恢复：自动找工作区根目录的离线包
    & '<skill>\scripts\setup.ps1' -Offline -Zip <zip>   # 或显式指定离线包路径
    & '<skill>\scripts\setup.ps1' -Bundle -W <工作区>   # 部署到工作区 tools\iverilog + tools\quality-lite
    & '<skill>\scripts\setup.ps1' -Install -Source "X:\path\to\iverilog"
    & '<skill>\scripts\setup.ps1' -Install -QualitySource "X:\path\to\quality-lite"
#>
param(
    [switch]$Check,
    [switch]$Install,
    [switch]$Bundle,
    [switch]$Auto,
    [switch]$Offline,
    [string]$Zip = '',
    [string]$Source = '',
    [string]$QualitySource = '',
    [string]$Target = '',
    [string]$W = ''
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rtl-tools.ps1"
$ws = Get-RtlWorkspace $W

function Find-Py {
    foreach ($n in @('python','python3','py')) {
        $c = Get-Command $n -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    return $null
}

# 部署 quality-lite（Yosys/slang/sby）。Src 可以是 quality-lite 根，
# 也可以是其父目录（自动探测 quality-lite 子目录）。
function Copy-QualityLite {
    param([string]$Src, [string]$Dest)
    if (-not $Src -or -not (Test-Path -LiteralPath $Src)) {
        Write-Host "[WARN] quality-lite 来源不存在: $Src"
        return $false
    }
    $Src = (Resolve-Path -LiteralPath $Src).Path
    if (-not (Test-Path -LiteralPath (Join-Path $Src 'yosys\bin\yosys.exe'))) {
        $alt = Join-Path $Src 'quality-lite'
        if (Test-Path -LiteralPath (Join-Path $alt 'yosys\bin\yosys.exe')) {
            $Src = (Resolve-Path -LiteralPath $alt).Path
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Src 'yosys\bin\yosys.exe'))) {
        Write-Host "[WARN] 来源不是有效的 quality-lite（缺少 yosys\bin\yosys.exe）: $Src"
        return $false
    }
    $sf = [System.IO.Path]::GetFullPath($Src).TrimEnd('\')
    $df = [System.IO.Path]::GetFullPath($Dest).TrimEnd('\')
    if ($sf -ieq $df) {
        Write-Host "  quality-lite 源与目标相同，跳过: $Dest"
        return $true
    }
    if (Test-Path -LiteralPath $Dest) {
        $item = Get-Item -LiteralPath $Dest
        if ($item.LinkType) { $item.Delete() }
        else { Remove-Item -LiteralPath $Dest -Recurse -Force }
    }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Write-Host "  拷贝 quality-lite ..."
    robocopy $Src $Dest /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Host "[WARN] quality-lite 拷贝失败"; return $false }
    $sz = (Get-ChildItem -LiteralPath $Dest -Recurse -File | Measure-Object Length -Sum).Sum
    Write-Host ("[OK] quality-lite 就绪: {0} ({1:N1} MB)" -f $Dest, ($sz / 1MB))
    return $true
}

Write-Host "== RTL 工具链检测 =="
$iverilog = Find-RtlTool 'iverilog.exe' $ws
$vvp      = Find-RtlTool 'vvp.exe'      $ws
$gtkwave  = Find-RtlTool 'gtkwave.exe'  $ws
$verible = Find-RtlTool 'verible-verilog-format.exe' $ws
$python   = Find-Py
$qualityRoot = Get-RtlQualityRoot $ws
$yosys = Find-RtlQualityTool 'yosys.exe' 'yosys\bin' $ws
$slang = Find-RtlQualityTool 'slang.exe' 'slang\bin' $ws
$sby   = Find-RtlQualityTool 'sby.py'    'sby\sbysrc' $ws
$ok = $true
foreach ($row in @(
    @{N='iverilog (编译)'; V=$iverilog},
    @{N='vvp (仿真)     '; V=$vvp},
    @{N='GTKWave (波形) '; V=$gtkwave},
    @{N='Python (生成器)'; V=$python},
    @{N='Yosys (综合/LEC)'; V=$yosys},
    @{N='slang (lint)  '; V=$slang},
    @{N='sby (formal)  '; V=$sby},
    @{N='Verible (可选)'; V=$verible; Optional=$true}
)) {
    if ($row.V) { Write-Host ("[OK]   {0}  -> {1}" -f $row.N, $row.V) }
    elseif ($row.Optional) { Write-Host ("[OPT]  {0}" -f $row.N) }
    else        { Write-Host ("[MISS] {0}" -f $row.N); $ok = $false }
}
if ($qualityRoot) { Write-Host "quality-lite: $qualityRoot" }
Write-Host ("== 结果: {0} ==" -f $(if ($ok) { '齐全' } else { '有缺失，可 -Install/-Bundle 或 -Offline 部署' }))

if ($Auto -and -not $ok) {
    Write-Host ""
    Write-Host "== 自动安装 iverilog（需要网络与包管理器）=="
    $try = $null
    foreach ($m in @('scoop', 'choco')) {
        if (Get-Command $m -ErrorAction SilentlyContinue) { $try = $m; break }
    }
    if ($try -eq 'scoop') {
        Write-Host "使用 scoop install iverilog gtkwave ..."
        scoop install iverilog gtkwave
    }
    elseif ($try -eq 'choco') {
        Write-Host "使用 choco install iverilog -y ..."
        choco install iverilog -y
    }
    else {
        Write-Host "未找到 scoop/choco。请手动安装后重跑本脚本（或 -Install 收拢便携工具链）："
        Write-Host "  Windows: https://bleyer.org/icarus/ （官方安装包含 GTKWave）"
        Write-Host "  Linux  : sudo apt install iverilog gtkwave"
        Write-Host "  macOS  : brew install icarus-verilog gtkwave"
        exit 1
    }
    if ($LASTEXITCODE -ne 0) { Write-Host "自动安装失败，请手动安装"; exit 1 }
    Write-Host "安装完成（PATH 可能需新开终端生效）。可再运行本脚本确认，或 -Install 收拢到缓存。"
    exit 0
}

if ($Offline) {
    # 离线恢复: 从 export.ps1 导出的 zip 解压 toolchain\iverilog 到缓存根（无网环境用）
    $zip = $Zip
    if (-not $zip) { $zip = Find-OfflineZip $ws }
    if (-not $zip) {
        Write-Host "未找到离线包：请用 -Offline -Zip <路径> 指定，或把 rtl-closed-loop-offline.zip 放到工作区根目录"
        exit 1
    }
    if (-not (Test-Path -LiteralPath $zip)) {
        Write-Host "离线包不存在: $zip"; exit 1
    }
    $dest = $Target
    if (-not $dest) { $dest = Get-RtlToolchainRoot }
    if (-not $dest) { Write-Host '无法确定缓存位置：请用 -Offline -Target <纯ASCII路径> 指定'; exit 1 }

    Write-Host ""
    Write-Host "== 离线恢复工具链: $zip -> $dest =="
    $tmp = Join-Path $env:TEMP ("rtl-offline-restore-" + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    $toolDir = Join-Path $tmp 'toolchain\iverilog'
    if (-not (Test-Path -LiteralPath (Join-Path $toolDir 'bin\iverilog.exe'))) {
        Write-Host "[WARN] 离线包中未找到 toolchain\iverilog（该包只含技能，需另装工具链）。"
        Remove-Item -LiteralPath $tmp -Recurse -Force
        exit 1
    }
    if (Test-Path -LiteralPath $dest) {
        $item = Get-Item -LiteralPath $dest
        if ($item.LinkType) {
            Write-Host "  移除旧 junction/symlink（仅删链接本身）"
            $item.Delete()
        } else {
            Write-Host "  目标已存在，先删除"
            Remove-Item -LiteralPath $dest -Recurse -Force
        }
    }
    New-Item -ItemType Directory -Path $dest | Out-Null
    Write-Host "  解压拷贝中..."
    robocopy $toolDir $dest /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Host "robocopy 失败"; Remove-Item -LiteralPath $tmp -Recurse -Force; exit 1
    }
    # verible 可选组件：离线包如含 toolchain\verible 则一并恢复/刷新
    $vTmp = Join-Path $tmp 'toolchain\verible'
    if (Test-Path -LiteralPath (Join-Path $vTmp 'bin\verible-verilog-format.exe')) {
        $vDest = Join-Path (Split-Path $dest -Parent) 'verible'
        New-Item -ItemType Directory -Force -Path $vDest | Out-Null
        robocopy $vTmp $vDest /E /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) { Write-Host "[WARN] verible 恢复失败" }
        else { Write-Host "[OK] verible 就绪: $(Join-Path $vDest 'bin\verible-verilog-format.exe')" }
    }
    # quality-lite 可选组件：离线包如含 toolchain\quality-lite 则恢复到 iverilog 缓存同级
    $qTmp = Join-Path $tmp 'toolchain\quality-lite'
    if (Test-Path -LiteralPath (Join-Path $qTmp 'yosys\bin\yosys.exe')) {
        $qDest = Join-Path (Split-Path $dest -Parent) 'quality-lite'
        Write-Host "  quality-lite -> $qDest"
        $null = Copy-QualityLite $qTmp $qDest
    } else {
        Write-Host "[OPT] 离线包不含 quality-lite（Yosys/slang/sby），仅基础仿真工具可用"
    }
    # 工具清单（可选）：仅在工作区尚无 tools\manifest.json 时恢复
    $mTmp = Join-Path $tmp 'toolchain\manifest.json'
    if (Test-Path -LiteralPath $mTmp) {
        $mDest = Join-Path $ws 'tools\manifest.json'
        if (Test-Path -LiteralPath $mDest) {
            Write-Host "[OPT] 保留已有清单: $mDest"
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path $mDest -Parent) | Out-Null
            Copy-Item -LiteralPath $mTmp -Destination $mDest -Force
            Write-Host "[OK] 工具清单: $mDest"
        }
    }
    Remove-Item -LiteralPath $tmp -Recurse -Force
    $sz = (Get-ChildItem -LiteralPath $dest -Recurse -File | Measure-Object Length -Sum).Sum
    Write-Host ("  完成: {0:N1} MB 已就位。" -f ($sz / 1MB))
    $exe = Join-Path $dest 'bin\iverilog.exe'
    if (Test-Path -LiteralPath $exe) {
        Write-Host "[OK] 离线工具链恢复成功: $exe"
    } else {
        Write-Host "[WARN] 未找到 $exe，请检查离线包内容"
        exit 1
    }
    exit 0
}

if (-not ($Install -or $Bundle)) { exit $(if ($ok) { 0 } else { 1 }) }

$src = $Source
if (-not $src) {
    $found = Find-RtlTool 'iverilog.exe' $ws
    if ($found) { $src = Get-RtlInstallRoot $found }
}
if (-not $src -or -not (Test-Path -LiteralPath $src)) {
    Write-Host "未找到来源安装，请用 -Source 指定"; exit 1
}

if ($Install) {
    $dest = $Target
    if (-not $dest) { $dest = Get-RtlToolchainRoot }
    if (-not $dest) { Write-Host '无法确定缓存位置：请用 -Install -Target <纯ASCII路径> 指定'; exit 1 }
}
else          { $dest = Join-Path $ws 'tools\iverilog' }

Write-Host ""
Write-Host "== 部署便携工具链: $src  ->  $dest =="
$sz = (Get-ChildItem -LiteralPath $src -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("  源大小: {0:N1} MB" -f ($sz / 1MB))

if (Test-Path -LiteralPath $dest) {
    $item = Get-Item -LiteralPath $dest
    if ($item.LinkType) {
        Write-Host "  移除旧 junction/symlink（仅删链接本身）"
        $item.Delete()
    } else {
        Write-Host "  目标已存在，先删除"
        Remove-Item -LiteralPath $dest -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $dest | Out-Null
Write-Host "  拷贝中..."
robocopy $src $dest /E /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Host "robocopy 失败"; exit 1 }
Write-Host ("  完成: {0:N1} MB 已就位。" -f ((Get-ChildItem -LiteralPath $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1MB))

# quality-lite（Yosys/slang/sby）一并部署：-Install 放缓存根同级，-Bundle 放工作区 tools
$qSrc = $QualitySource
if (-not $qSrc) { $qSrc = Get-RtlQualityRoot $ws }
if ($qSrc) {
    if ($Install) { $qDest = Join-Path (Split-Path $dest -Parent) 'quality-lite' }
    else          { $qDest = Join-Path $ws 'tools\quality-lite' }
    Write-Host ""
    Write-Host "== 部署 quality-lite: $qSrc  ->  $qDest =="
    $null = Copy-QualityLite $qSrc $qDest
} else {
    Write-Host ""
    Write-Host "[OPT] 未找到 quality-lite 来源（Yosys/slang/sby），跳过。可用 -QualitySource 指定。"
}