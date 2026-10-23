# Formal templates: single clock + async reset

最小可运行形式验证模板，配套 `rtl-closed-loop` 的 `formal` 阶段。

| 文件 | 作用 |
|---|---|
| `rtl/demo_ctr.v` | 基础示例 DUT：计数器（异步低有效复位） |
| `formal/demo_ctr.sby` | sby 任务：`mode prove`、`[engines] abc pdr` |
| `formal/demo_ctr_fv.sv` | 基础 wrapper：boot 计数、复位约束、断言门控 |
| `rtl/pulse_stretch.v` | 协议级 DUT：单拍 `req` 拉伸为固定 `LATENCY` 拍 `busy` |
| `formal/pulse_stretch.sby` | 协议级 sby 任务（同上，`abc pdr`） |
| `formal/pulse_stretch_fv.sv` | 协议级 wrapper：影子计数器 + 相邻拍历史寄存器 |

目录结构与工作区一致。把 `rtl/`、`formal/` 复制到工作区后运行：

```powershell
python scripts/rtlq.py formal -W <工作区> --top demo_ctr
python scripts/rtlq.py formal -W <工作区> --top pulse_stretch
```

## 协议级多周期模板（pulse_stretch）

`pulse_stretch` 把单拍 `req` 拉伸成固定长度的 `busy`，`done` 只在最后一个
`busy` 拍为高；`busy` 期间的 `req` 被忽略。它演示了计数器模板没有覆盖的
两类属性：

- **影子计数器**：wrapper 自己维护 `shadow`（`busy` 时加 1，`!busy` 时清零），
  不复用 DUT 内部 `cnt`。这样即使 DUT 把 `done` 和释放条件一起改早，
  断言仍能发现脉冲长度不对。只比较 DUT 自己的 `done` 会被“自洽的错误”骗过。
- **位/拍边界**：用 `past_busy`、`past_done`、`past_shadow` 保存上一拍，
  在 `posedge` 比较相邻两拍，检查“上升沿必须有请求”“未到边界不能释放”
  “到边界必须释放”“`done` 恰好出现在影子计数最后一拍”。

关键写法：

```systemverilog
// 影子计数：独立于 DUT 内部实现
always @(posedge clk or negedge rst_n) begin
    if (rst_n == 1'b0)              shadow <= {CNT_W{1'b0}};
    else if (!busy)                 shadow <= {CNT_W{1'b0}};
    else if (shadow != LATENCY - 1) shadow <= shadow + 1'b1;
end

// 相邻拍属性（节选）
if (past_busy && (past_shadow != LATENCY - 1)) assert(busy);   // 不许早退
if (past_busy && (past_shadow == LATENCY - 1)) assert(!busy);  // 边界释放
assert(done == (busy && (shadow == LATENCY - 1)));             // done 位置
```

**boot 计数器位宽**：`boot` 必须能表示 `RESET_CYCLES` 本身。若直接复用
`CNT_W = $clog2(LATENCY+1)`（本例 2 bit，最大 3），`boot >= RESET_CYCLES`
（4）永远为假，所有断言都会被门控掉，PDR 会显示 “frame 0 (trivial)” 的
假 PASS。模板用独立的 `BOOT_W = $clog2(RESET_CYCLES+1)`。看到大量
“Proved ... in frame 0 (trivial)” 时，先检查门控条件是否可达。

验证非空洞性：把 DUT 的 `cnt == LATENCY - 1` 改成 `LATENCY - 2`（提前一拍
释放），`sby` 应返回 `FAIL`；改回后返回 `PASS`。

要点：

- `prep` 会执行 `formalff -ff2anyinit`，所有未初始化触发器在形式视图中
  初始值任意；不能用单条 `initial assume(rst_n == 0)` 代替复位序列。
  模板用 `initial boot = 0` + 前 `RESET_CYCLES` 拍 `assume(rst_n == 0)`
  清空任意初值，之后 `assume(rst_n == 1)` 并仅在 `boot >= RESET_CYCLES`
  时检查断言。
- `[files]` 路径相对于 `-W` 工作区，不是相对于 `.sby` 文件所在目录；
  sby 会把文件复制到 `report/formal/<top>/`，所以 `[script]` 里的 `read`
  使用复制后的文件名（不含 `rtl/`、`formal/` 前缀）。
- 带异步复位的设计在 `prep` 后加 `clk2fflogic`；只有同步复位时可省略。
- 本模板用 `[engines] abc pdr`，因为技能自带的 quality-lite 不含
  `yosys-smtbmc`。`smtbmc` 的可用性与失败轨迹说明见
  `references/toolchain.md` 的「形式验证引擎与调试」。
