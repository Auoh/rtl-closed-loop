#!/usr/bin/env bash
# run.sh (rtl-closed-loop 技能) - 编译 + 仿真回归（Linux/macOS）
# 用法: ./run.sh [模块=sync_fifo] [bug|wave] [工作区=当前目录]
# 优先走 rtlq.py sim（多文件、-g2012、统一日志/统计）；无 Python 时退回直接 iverilog。
set -euo pipefail

TOP="${1:-sync_fifo}"
MODE="${2:-}"
WS="${3:-$(pwd)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"

[ -d "$WS/rtl" ] || { echo "工作区无效（缺少 rtl/）: $WS"; exit 2; }
mkdir -p "$WS/sim"

# Pick a working Python 3.8+; skip broken stubs such as the Windows Store
# python3 alias, which exits 49 with no output.
find_py() {
  for cand in "${PYTHON:-}" python3 python py; do
    [ -n "$cand" ] || continue
    p="$(command -v "$cand" 2>/dev/null || true)"
    [ -n "$p" ] || continue
    if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$p"
      return 0
    fi
  done
  return 1
}
PY="$(find_py || true)"

if [ -n "$PY" ] && [ -f "$SKILL_ROOT/scripts/rtlq.py" ]; then
  ARGS=(sim --workdir "$WS" --top "$TOP")
  case "$MODE" in
    bug)  ARGS+=(--bug) ;;
    wave) ARGS+=(--wave) ;;
    "")   ;;
    *)    echo "未知模式: $MODE（可选 bug|wave）"; exit 2 ;;
  esac
  exec "$PY" "$SKILL_ROOT/scripts/rtlq.py" "${ARGS[@]}"
fi

# ---- 无 Python 回退：直接 iverilog ----
IVERILOG="$(command -v iverilog || true)"
VVP="$(command -v vvp || true)"
if [ -z "$IVERILOG" ] || [ -z "$VVP" ]; then
  echo "[MISS] 未找到 python3/iverilog/vvp，请安装:"
  echo "  Ubuntu/Debian : sudo apt install iverilog"
  echo "  macOS         : brew install icarus-verilog"
  exit 3
fi
echo "workspace: $WS"
echo "iverilog : $IVERILOG"

DEFS=()
case "$MODE" in
  bug)  DEFS+=(-DINJECT_BUG=1) ;;
  wave) DEFS+=(-DDUMP_WAVE) ;;
  "")   ;;
  *)    echo "未知模式: $MODE（可选 bug|wave）"; exit 2 ;;
esac

shopt -s nullglob
RTL_FILES=("$WS"/rtl/*.v "$WS"/rtl/*.sv)
shopt -u nullglob

echo "== compile ($TOP) =="
"$IVERILOG" -g2012 -s "tb_$TOP" -o "$WS/sim/${TOP}.vvp" "${DEFS[@]}" \
  "${RTL_FILES[@]}" "$WS/tb/tb_${TOP}.v"
echo "== run =="
(cd "$WS/sim" && "$VVP" "${TOP}.vvp")
