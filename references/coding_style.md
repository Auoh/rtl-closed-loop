# RTL 编码规范（rtl-closed-loop 通用）

> 适用范围：本技能生成/审查的所有 RTL 模块（`rtl/*.v`、`rtl/*.sv`）。
> 维护：后续任何新的编码要求，必须同步刷新本文件（见第 9 节），并在示例代码中落地后重跑一次完整回归，确认语义不变。
> 现行参考实现：`uart_demo/rtl/uart_top.v`（三段式 + 逐信号 always + 本规范全部条目）。

## 1. 状态机统一三段式
- F1：状态寄存器（时序）：`state <= state_next`
- F2：次态组合逻辑（`always @(*)`）：开头写默认 `state_next = state;`，再用 case 覆盖
- F3：数据通路/标志（时序）：逐信号 always 块
- 禁止把次态计算与状态寄存器写进同一个 always 块。

```verilog
// F1: 状态寄存器
always @(posedge clk or negedge rst_n) begin
    if (rst_n == 1'b0) begin
        state <= IDLE;
    end
    else begin
        state <= state_next;
    end
end
// F2: 次态组合逻辑（default 显式赋值，避免 latch）
always @(*) begin
    state_next = state;
    case (state)
        IDLE: begin
            if (go) begin
                state_next = BUSY;
            end
            else ;  // hold
        end
        default: begin
            state_next = IDLE;
        end
    endcase
end
```

## 2. 一个 always 块只允许对一个信号赋值
- 时序逻辑逐信号拆分：每个 always 块只驱动一个 reg（或一个数组元素）。
- 组合逻辑块同样每个只驱动一个信号（如 `state_next`）。
- 同一信号的多路条件赋值写在同一块内，属于"一个信号"，合法。

## 3. 信号定义集中放在模块最前
- 所有 `localparam` / `reg` / `wire` 声明集中在模块头部（端口列表之后、逻辑之前），禁止散落在各功能段中间。
- `localparam` 与信号声明分两个区块，`localparam` 区块更靠前。
- 端口声明：input 不需要类型关键字（默认就是 wire），写 `input clk`；output 保留 `output wire` 显式声明。

```verilog
// localparam 区块（最前）
localparam S_CLK   = CLK_DIV / 16;
localparam TX_IDLE = 2'd0;
localparam TX_BUSY = 2'd1;
// 信号声明区块（其后）
reg  [$clog2(S_CLK)-1:0] s_cnt;
reg  s_tick;
reg  [1:0] state;
wire       full;
```

## 4. 低电平复位条件写全
- 一律写 `rst_n == 1'b0`，禁止 `!rst_n`（显式化，避免低/高电平复位混淆）。

```verilog
always @(posedge clk or negedge rst_n) begin
    if (rst_n == 1'b0) begin
        cnt <= 0;
    end
    else begin
        cnt <= cnt + 1'b1;
    end
end
```

## 5. if / else 分支写全
- 所有 if / else-if 链必须以 `else` 结尾，禁止省略最后一个 else。
- 最后一个 else 表示"信号保持"：直接写 `else ;`，不需要 begin/end。
- 有赋值的分支必须带 begin/end（排版见第 6 节）。

```verilog
if (a) begin
    sig <= 1'b1;
end
else if (b) begin
    sig <= 1'b0;
end
else ;  // hold
```

## 6. 排版：begin / end 与 else 分行
- `begin` 与 `if`/`else if`/`else` 条件同一行；赋值内容换行缩进；`end` 单独一行。
- `end` 不与下一个 `else` 写在同一行：`else` 单独起行（`else begin` 同行）。
- 条件较长可换行，`begin` 放在条件最后一行的行尾。

```verilog
if (cond_a && cond_b &&
    cond_c) begin
    sig <= 1'b1;
end
else ;  // hold
```

## 7. case / default
- 每个 `case` 必须写出 `default` 分支，禁止省略；`default` 必须显式写出对信号的赋值，禁止空语句或空 begin-end。
- 组合逻辑的 `case`（如 F2 次态）：所有分支（含 `default`）都必须显式写出对输出的赋值，避免综合推断 latch；建议块首用默认赋值兜底。
- 时序逻辑 `case` 的 `default` 表示保持：写显式自赋值，如 `default: cnt <= cnt;`（不要写 `default: ;`）。

## 8. 不使用 function
- 模块内禁止定义 `function`；小规模组合逻辑用 `wire` + `assign` 表达。
- 示例：3-of-3 多数表决原为 function `maj3`，改为
  `assign rx_maj = (a & b) | (a & c) | (b & c);`

## 9. 文档维护
- 出现新的编码要求时：在本文件追加或修订对应条目，并把参考实现（如 `uart_top.v`）同步改造。
- 每次规范变更后必须：跑完整回归（`RESULT: PASS`）与负向演练（`-Bug` 必须 FAIL），确认风格重构不改变语义。

## 10. 格式检查、自动格式化与报告
- 检查：`scripts/format.ps1 -W <工作区> -Top <module>`（或 `-File <rtl.v>`），退出码 0 = FORMAT OK。
- 报告：`scripts/format.ps1 -W <工作区> -Top <module> -Report docs\coding_report_<module>.md`，生成 Markdown 报告（违例明细表：行号/规则/问题/修改建议 + 规则总览）；无违例也输出 PASS 报告。
- 自动格式化：`scripts/format.ps1 -Fix` 调用 verible-verilog-format（`--indentation_spaces=4 --wrap_end_else_clauses`）后追加安全规范修复（R5 input 去 wire、R7 保持 else 收成 `else;`），再做第二次 verible 对齐并复查（可同时带 `-Report` 出报告）。
- 回归入口 `run.ps1` 默认**不修改** RTL；需要自动格式化时显式加 `-FixFormat`。
- 统一检查入口：`scripts/rtlq.py lint -W <工作区> -Top <module>`（R1-R10 + slang + Yosys 结构检查）。
- 违例按 `R1..R10` 对应本文件条目定位；R3（`!rst_n`）与 R4（空 default）需手动补改，自动修复不做语义推断。
- 外部提供的 RTL：并入工程前必须先跑一次带 `-Report` 的检查，报告随交付物归档到 `docs\`，并按建议修复后才能进入仿真流程。
## 11. 附：验证建议（TB 激励纪律）
- 同步接口信号（`tx_wr`/`tx_data`/`rx_rd`/`rst_n`）禁止在 `@(posedge clk)` 后用阻塞赋值驱动（会在时钟沿 active 区与 DUT 各 always 块竞争采样，拆分 always 块后会导致 mem/指针错位）。
- 统一采用"沿后 `#1` 偏移再阻塞赋值"；不要用同一拍多个任务对同一信号做非阻塞赋值（背靠背调用会撞 NBA 区）。

## 12. 时钟纪律（R9 / R10）
- R9：时钟只允许上沿触发。时序逻辑统一 `always @(posedge clk ...)`；禁止
  `always @(negedge clk ...)`、双沿/组合沿采样，禁止把时钟用于数据通路。
  异步复位例外（复位不是时钟）：仍按第 4 条写
  `always @(posedge clk or negedge rst_n)`。
- R10：时钟信号不得当数据使用。禁止把 clk 输入寄存、打拍、采样或作为判断
  条件（反例：用 250M 时钟对 31.25M 时钟采样判沿；把慢时钟当门控/数据）。
  跨时钟只传数据：慢时钟域只产生“数据”信息（如帧标记 FF），经 2 级触发器
  同步到快时钟域后使用；时钟本身永远只作时钟。
- 整数比同源时钟（如 250M 与 31.25M = 8:1）的帧对齐在快时钟域实现：慢域帧
  标记数据经 2FF 得到帧脉冲，锁相时把槽计数预置到与慢时钟上沿周期对应的相位，
  此后按整周期自由回绕，使寄存输出的帧首通道号（槽0）在慢时钟上沿所在快时钟周期呈现
  （槽0 判定位于上沿前 1 拍，以补偿 1 拍输出寄存流水；相位细节以参考实现注释为准）；
  不靠采样慢时钟、也不把对齐责任交给“复位在帧边界释放”。
- 现行参考实现：`rtl/ch_num_gen.v`（clk_31m25 仅作时钟驱动慢域帧标记 FF +
  2FF 同步 + 相位预置锁相（SLOT_LOCK=3），寄存输出帧首通道号对齐 31.25M 上沿；全 posedge 触发、无时钟采样。
