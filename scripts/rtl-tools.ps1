# rtl-tools.ps1 - rtl-closed-loop 技能公共函数（工作区定位 + 工具链查找）

# 纯 ASCII 判断（iverilog 内部子进程在非 ASCII 路径下会解析失败）
function Test-Ascii {
    param([string]$S)
    foreach ($ch in $S.ToCharArray()) {
        if ([int]$ch -gt 127) { return $false }
    }
    return $true
}

# 工具链安装根目录：环境变量 RTL_TOOLCHAIN 优先；
# 否则 $HOME\.codex\rtl-toolchain（要求 $HOME 为纯 ASCII）；
# 否则尝试纯 ASCII 根（C:\ D:\ ...），再不行返回 $null
function Get-RtlToolchainRoot {
    if ($env:RTL_TOOLCHAIN) { return $env:RTL_TOOLCHAIN }
    if (Test-Ascii $HOME) {
        return (Join-Path $HOME '.codex\rtl-toolchain\iverilog')
    }
    foreach ($root in @('C:\rtl-toolchain', 'D:\rtl-toolchain', 'E:\rtl-toolchain', 'F:\rtl-toolchain')) {
        try {
            New-Item -ItemType Directory -Force -Path $root -ErrorAction Stop | Out-Null
            return (Join-Path $root 'iverilog')
        } catch { }
    }
    return $null
}

# 工作区根：显式 -W 优先，否则当前目录
function Get-RtlWorkspace {
    param([string]$W)
    if (-not $W -or -not (Test-Path -LiteralPath $W)) { $W = (Get-Location).Path }
    return (Resolve-Path -LiteralPath $W).Path
}

# quality-lite 根目录（Yosys + slang + sby）：环境变量优先 -> 工作区
# tools\quality-lite -> 缓存根旁 quality-lite -> 纯 ASCII 根。
function Get-RtlQualityRoot {
    param([string]$Ws)
    if ($env:RTL_QUALITY_LITE -and (Test-Path -LiteralPath $env:RTL_QUALITY_LITE)) {
        return (Resolve-Path -LiteralPath $env:RTL_QUALITY_LITE).Path
    }
    if ($Ws) {
        $p = Join-Path $Ws 'tools\quality-lite'
        if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
    }
    $iver = Get-RtlToolchainRoot
    if ($iver) {
        $parent = Split-Path $iver -Parent
        foreach ($q in @((Join-Path $parent 'quality-lite'), (Join-Path $iver 'quality-lite'))) {
            if (Test-Path -LiteralPath $q) { return (Resolve-Path -LiteralPath $q).Path }
        }
    }
    foreach ($root in @('C:\rtl-toolchain\quality-lite', 'D:\rtl-toolchain\quality-lite',
                        'E:\rtl-toolchain\quality-lite', 'F:\rtl-toolchain\quality-lite')) {
        if (Test-Path -LiteralPath $root) { return (Resolve-Path -LiteralPath $root).Path }
    }
    return $null
}

# 查找 quality-lite 内的可执行文件/脚本，例如：
#   Find-RtlQualityTool 'yosys.exe' 'yosys\bin' $ws
#   Find-RtlQualityTool 'sby.py'    'sby\sbysrc' $ws
function Find-RtlQualityTool {
    param([string]$Exe, [string]$RelDir, [string]$Ws)
    $root = Get-RtlQualityRoot $Ws
    if (-not $root) { return $null }
    $p = Join-Path $root (Join-Path $RelDir $Exe)
    if (Test-Path -LiteralPath $p) { return $p }
    return $null
}

# 工具链查找顺序: 用户缓存(Get-RtlToolchainRoot) -> 工作区 tools -> PATH
# 支持 iverilog（bin/gtkwave/bin）与 verible（同级目录 verible/bin）
function Find-RtlTool {
    param([string]$Exe, [string]$Ws)
    $root = Get-RtlToolchainRoot
    if ($root) {
        $parent = Split-Path $root -Parent
        foreach ($rel in @("bin\$Exe", "gtkwave\bin\$Exe", "verible\bin\$Exe")) {
            $cache = Join-Path $root $rel
            if (Test-Path -LiteralPath $cache) { return $cache }
        }
        if ($parent) {
            $v = Join-Path $parent "verible\bin\$Exe"
            if (Test-Path -LiteralPath $v) { return $v }
        }
    }
    if ($Ws) {
        foreach ($rel in @("tools\iverilog\bin\$Exe", "tools\iverilog\gtkwave\bin\$Exe",
                           "tools\verible\bin\$Exe")) {
            $wsTool = Join-Path $Ws $rel
            if (Test-Path -LiteralPath $wsTool) { return $wsTool }
        }
    }
    $c = Get-Command $Exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}


# 查找离线包 zip：工作区根 -> 工作区 tools\ -> 技能目录旁
function Find-OfflineZip {
    param([string]$Ws)
    $cands = @(
        (Join-Path $Ws 'rtl-closed-loop-offline.zip'),
        (Join-Path $Ws 'tools\rtl-closed-loop-offline.zip'),
        (Join-Path $PSScriptRoot '..\rtl-closed-loop-offline.zip')
    )
    foreach ($c in $cands) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

# 从离线包恢复工具链到缓存根（zip 为空时按 Find-OfflineZip 查找）
function Restore-OfflineToolchain {
    param([string]$Zip, [string]$Ws)
    if (-not $Zip -and $Ws) { $Zip = Find-OfflineZip $Ws }
    if (-not $Zip) { return $null }
    $dest = Get-RtlToolchainRoot
    if (-not $dest) { return $null }
    if (Test-Path -LiteralPath (Join-Path $dest 'bin\iverilog.exe')) { return $dest }
    Write-Host "[AUTO] 检测到离线包: $Zip"
    Write-Host "[AUTO] 自动部署工具链到: $dest ..."
    $tmp = Join-Path $env:TEMP ("rtl-offline-auto-" + [guid]::NewGuid().ToString('N'))
    try {
        Expand-Archive -LiteralPath $Zip -DestinationPath $tmp -Force
        $toolDir = Join-Path $tmp 'toolchain\iverilog'
        if (-not (Test-Path -LiteralPath (Join-Path $toolDir 'bin\iverilog.exe'))) {
            Write-Host "[WARN] 离线包结构无效（缺少 toolchain\iverilog\bin\iverilog.exe）: $Zip"
            return $null
        }
        if (Test-Path -LiteralPath $dest) {
            $item = Get-Item -LiteralPath $dest
            if ($item.LinkType) { $item.Delete() }
            else { Remove-Item -LiteralPath $dest -Recurse -Force }
        }
        New-Item -ItemType Directory -Path $dest | Out-Null
        robocopy $toolDir $dest /E /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) { Write-Host "[WARN] robocopy 失败"; return $null }
        Write-Host "[AUTO] 工具链就绪: $(Join-Path $dest 'bin\iverilog.exe')"
        # verible 可选组件：离线包如含 toolchain\verible 则一并恢复
        $vTmp = Join-Path $tmp 'toolchain\verible'
        if (Test-Path -LiteralPath (Join-Path $vTmp 'bin\verible-verilog-format.exe')) {
            $vDest = Join-Path (Split-Path $dest -Parent) 'verible'
            New-Item -ItemType Directory -Force -Path $vDest | Out-Null
            robocopy $vTmp $vDest /E /NFL /NDL /NJH /NJS | Out-Null
            if ($LASTEXITCODE -ge 8) { Write-Host "[WARN] verible 恢复失败" }
            else { Write-Host "[AUTO] verible 就绪: $(Join-Path $vDest 'bin\verible-verilog-format.exe')" }
        }
        # quality-lite（Yosys/slang/sby）可选组件：与 iverilog 缓存同级
        $qTmp = Join-Path $tmp 'toolchain\quality-lite'
        if (Test-Path -LiteralPath (Join-Path $qTmp 'yosys\bin\yosys.exe')) {
            $qDest = Join-Path (Split-Path $dest -Parent) 'quality-lite'
            if (Test-Path -LiteralPath $qDest) {
                $qi = Get-Item -LiteralPath $qDest
                if ($qi.LinkType) { $qi.Delete() }
                else { Remove-Item -LiteralPath $qDest -Recurse -Force }
            }
            New-Item -ItemType Directory -Force -Path $qDest | Out-Null
            robocopy $qTmp $qDest /E /NFL /NDL /NJH /NJS | Out-Null
            if ($LASTEXITCODE -ge 8) { Write-Host "[WARN] quality-lite 恢复失败" }
            else { Write-Host "[AUTO] quality-lite 就绪: $qDest" }
        }
        return $dest
    } finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    }
}

# 找不到就尝试自动恢复，仍失败则报错退出
function Get-RtlToolOrDie {
    param([string]$Exe, [string]$Ws, [string]$Label)
    $p = Find-RtlTool $Exe $Ws
    if (-not $p) {
        Write-Host "[AUTO] 缺少 $Exe（$Label），尝试从工作区离线包自动恢复工具链..."
        $null = Restore-OfflineToolchain '' $Ws
        $p = Find-RtlTool $Exe $Ws
    }
    if (-not $p) {
        Write-Host "[MISS] 未找到 $Exe（$Label）。"
        Write-Host "  请运行: & '$PSScriptRoot\setup.ps1' -Install   （部署便携工具链）"
        Write-Host "  或将离线包 rtl-closed-loop-offline.zip 放到工作区根目录后重试"
        Write-Host "  或安装系统版 iverilog 并加入 PATH。"
        exit 3
    }
    return $p
}

# 从已找到的 exe 反推安装根目录（<root>\bin\xx.exe）
function Get-RtlInstallRoot {
    param([string]$ExePath)
    if (-not $ExePath) { return $null }
    $bin = Split-Path $ExePath -Parent
    return Split-Path $bin -Parent
}