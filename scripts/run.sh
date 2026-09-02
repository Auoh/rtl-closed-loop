#!/usr/bin/env bash
# run.sh (rtl-closed-loop 技能) - 编译 + 仿真回归（Linux/macOS）
# 用法: ./run.sh [模块=sync_fifo] [bug|wave] [工作区=当前目录]
set -euo pipefail

TOP="${1:-sync_fifo}"
MODE="${2:-}"
WS="${3:-$(pwd)}"

[ -d "$WS/rtl" ] || { echo "工作区无效（缺少 rtl/）: $WS"; exit 2; }
mkdir -p "$WS/sim"

IVERILOG="$(command -v iverilog || true)"
VVP="$(command -v vvp || true)"
if [ -z "$IVERILOG" ] || [ -z "$VVP" ]; then
  echo "[MISS] 未找到 iverilog/vvp，请安装:"
  echo "  Ubuntu/Debian : sudo apt install iverilog"
  echo "  macOS         : brew install icarus-verilog"
  exit 3
fi
echo "workspace: $WS"
echo "iverilog : $IVERILOG"

DEFS=()
if [ "$MODE" = "bug"  ]; then DEFS+=(-DINJECT_BUG=1); fi
if [ "$MODE" = "wave" ]; then DEFS+=(-DDUMP_WAVE); fi

echo "== compile ($TOP) =="
iverilog -g2005 -s "tb_$TOP" -o "$WS/sim/${TOP}.vvp" "${DEFS[@]}" "$WS/rtl/${TOP}.v" "$WS/tb/tb_${TOP}.v"
echo "== run =="
(cd "$WS/sim" && vvp "${TOP}.vvp")