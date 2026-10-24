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
python scripts/rtlq.py formal --workdir <工作区> --top demo_ctr
python scripts/rtlq.py formal --workdir <工作区> --top pulse_stretch
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

## 数值/计数型不变式的证明策略

`abc pdr` 是位级归纳引擎。对“输出频率等于 `clk / (period+1)`”“8 位累加器
始终满足某算术关系”这类一般化的数值不变式，PDR 往往无法闭合（尤其当
`period`/`duty` 是每拍自由的 8 位输入时，状态空间实际不可枚举）。推荐顺序：

1. **优先证明逐拍参考等式**：在 wrapper 里用独立影子计数器/移位寄存器复现
   期望行为，断言每个 `posedge` 的 `pwm_out == ref_out`（或
   `grant == ref_grant`）。这类属性是逐拍等式，归纳友好，PDR 通常能收敛，
   而且能抓住“自洽但错误”的实现（影子逻辑不复用 DUT 内部状态）。
2. **计数/边界属性用代表性常量配置**：固定 `PERIOD`、`DUTY`（例如
   `PERIOD=8`、`DUTY=1/3/7`），证明若干拍后的行为与边界；不要试图让一次
   prove 覆盖符号化的全部 8 位配置组合。需要覆盖更多配置时，用多个 `.sby`
   任务或多个 wrapper 实例，而不是把配置当自由输入。
3. **短反例先用 bmc**：临时 `mode bmc` + `[engines] abc bmc3` 找最短失败帧，
   再回到 `prove`。`abc pdr` 只允许 `prove` 模式。
4. 若逐拍等式仍需很深的归纳，检查是否把 DUT 内部计数器直接抄进了参考逻辑；
   影子逻辑应与 DUT 实现方式不同（例如用移位寄存器而非计数器），否则证明
   会退化为同构比较。

## 保持配置输入恒定

如果 DUT 有 `period`、`duty` 这类自由配置输入，形式环境中它们每拍都可以任意
变化，此时“固定频率/占空比”属性没有意义（DUT 每拍都可能被重新配置）。验证
固定配置下的行为时，在复位窗口捕获配置并全程约束：

```systemverilog
reg [7:0] period_hold, duty_hold;
always @(posedge clk) begin
    if (boot == 0) begin
        period_hold <= period;
        duty_hold   <= duty;
    end
end
always @(posedge clk) begin
    if (boot >= RESET_CYCLES)
        assume(period == period_hold && duty == duty_hold);
end
```

捕获窗口用 `boot == 0`（或首个复位拍）即可，之后每拍 `assume` 相等。务必在
`boot >= RESET_CYCLES` 后再施加约束，避免复位期间 X 进入 hold 寄存器。若要
验证“运行中修改配置”的行为，另建任务和影子模型，不要与固定配置属性混在
同一个 prove 里。

## depth 与 prove 的关系

`.sby` 的 `depth` 只约束 `mode bmc` 的帧数；`mode prove` 下 `abc pdr` 会自行
迭代到证明完成、发现反例或超时，**不受 depth 限制**（实测 `.sby` 写
`depth 50`，证明在 frame 63 才完成）。因此：

- 估算 prove 规模/运行时看 `formal.timeout_s`，不要看 `depth`；
- 需要限定证明资源时调小 `timeout_s`（超时后 rtlq 会终止整个进程树），
  而不是调小 `depth`；
- 只有切到 `mode bmc` 时 `depth` 才是有界的搜索深度。

## 变异证据归档

技能要求做变异检查（改坏 RTL 后 `sby`/`formal` 必须 FAIL），但 `summary.md`
由 `quality.json` 重生成，无法保留临时变异运行的输出。约定把证据放到
**`report/mutation/<top>/`**：

- 每个变异一份日志（如 `release_early.log`、`mutant_notes.md`），记录改动的
  文件:行号、命令、退出码、`DONE (FAIL)` 或 `DONE (PASS)` 结论；
- `rtlq.py all` / `rtlq.py report` 生成 `summary.md` 时会列出该目录下已存在的
  文件，便于评审定位；
- 变异证据不影响 `all` 的退出码（变异是手工/脚本步骤），但交付说明和 A12
  检查应引用该目录。

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
