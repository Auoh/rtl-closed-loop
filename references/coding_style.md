# RTL 编码规范（rtl-closed-loop 通用）

> 适用范围：本技能生成/审查的所有 RTL 模块（`rtl/*.v`、`rtl/*.sv`）。
> 维护：后续任何新的编码要求，必须同步刷新本文件（见第 9 节），并在示例代码中落地后重跑一次完整回归，确认语义不变。
> 现行参考实现：`uart_demo/rtl/uart_top.v`（三段式 + 逐信号 always + 本规范全部条目）。

## 1. 状态机统一三段式
- F1：状态寄存器（时序）：`state <= state_next`
- F2：次态组合逻辑（`always @(*)`）：每个 case/if 分支显式赋值 `state_next`；
  保持分支写该状态的常量（如 `state_next = IDLE;`），`default` 也写常量。
  **不要**用块首 `state_next = state;` 兜底，也不要写 `else ;`（见第 13 节）
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
// F2: 次态组合逻辑（每个分支显式赋值，避免 latch 并保持 LEC 友好）
always @(*) begin
    case (state)
        IDLE: begin
            if (go) begin
                state_next = BUSY;
            end
            else begin
                state_next = IDLE;  // 显式保持
            end
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
- 组合逻辑的 `case`（如 F2 次态）：所有分支（含 `default`）都必须显式写出对输出的赋值，避免综合推断 latch。F2 的保持分支写该状态的**常量**（如 `state_next = IDLE;`），不要写 `state_next = state;` 或 `else ;`（原因见第 13 节）。
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
- 统一检查入口：`python scripts/rtlq.py lint --workdir <工作区> --top <module>`（R1-R10 + slang + Yosys 结构检查）。
- 违例按 `R1..R10` 对应本文件条目定位；R3（`!rst_n`）与 R4（空 default）需手动补改，自动修复不做语义推断。
- 外部提供的 RTL：并入工程前必须先跑一次带 `-Report` 的检查，报告随交付物归档到 `docs\`，并按建议修复后才能进入仿真流程。
## 11. 附：验证建议（TB 激励纪律）
- 同步接口信号（`tx_wr`/`tx_data`/`rx_rd`/`rst_n`）在 `@(posedge clk)` 上用**非阻塞赋值（NBA）**驱动，零延时提交；DUT 在同一沿采样到的是沿前值（上一拍驱动的值），符合真实时序逻辑语义。
- TB 在上升沿用**阻塞赋值捕获** DUT 实际采样的输入到 `*_cap`；负沿检查时，**寄存器输出**的参考模型用 `*_cap`（与 DUT 采样沿对齐），**组合输出**直接用当前输入（负沿时组合输出已反映本拍输入，`*_cap` 会落后一拍）。全程**不使用 `#1` 或任何延时**。
- 不要用"沿后 `#1` 偏移再阻塞赋值"驱动激励：它会在负沿制造人为跳变，违背"理想仿真、零延时"约定（见 `toolchain.md`「激励与时序约定」）。
- 同一拍多个任务不要对同一信号重复赋值；`gen_tb.py` 生成的模板已按上述约定实现，手工 TB 也照此执行。

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
  2FF 同步 + 相位预置锁相（SLOT_LOCK=3），寄存输出帧首通道号对齐 31.25M 上沿；全 posedge 触发、无时钟采样。）

## 13. LEC 友好的状态机写法

Yosys LEC（`equiv_opt ... synth`）逐线比较 RTL 与综合网表。三段式 FSM 若依赖
“块首默认赋值 + `else ;` 保持”，综合时 `opt_dff` 会把状态寄存器改写成带时钟
使能的 `$adffe`（DFFE）：网表里的 `state_next` 只在使能有效时才有意义，LEC 对
`state_next` 做组合比较就会失败（状态寄存器本身却可能是 proven）。按下面写法
通常可以让 `lec.blacklist` 保持为空：

1. 状态寄存器加 `(* fsm_encoding = "none" *)`，禁止 Yosys 对状态位重新编码：
   ```verilog
   (* fsm_encoding = "none" *) reg [1:0] state;
   ```
2. F2 的每个 case 分支、每条 if/else 路径都**显式赋值** `state_next`；保持分支
   必须写**该状态的常量**（如 `state_next = ST_IDLE;`），不要写
   `state_next = state;`，不要写 `else ;`，也不要只靠块首默认值兜底。
   反馈赋值 `state_next = state;` 在部分分支结构下仍会被 `opt_dff` 识别为
   “保持”，生成带时钟使能的 `$adffe`，导致 `state_next` unproven：
   ```verilog
   always @(*) begin
       case (state)
           ST_IDLE: begin
               if (go) begin
                   state_next = ST_BUSY;
               end
               else begin
                   state_next = ST_IDLE;  // 显式保持
               end
           end
           ST_BUSY: begin
               state_next = done ? ST_IDLE : ST_BUSY;
           end
           default: begin
               state_next = ST_IDLE;
           end
       endcase
   end
   ```
   这样 `state_next` 始终是 state 与输入的纯组合函数，综合网表不会把它改写成
   时钟使能形式，LEC 可直接比较。
3. F3 的输出用 `state == ST_*` 显式译码，不要挤进 F2。
4. 先按第 1、2 条修改。仍有个别 `state_next` / 状态位 unproven 时，先确认清空
   blacklist 后是否只剩该信号；只有确认差异来自工具重编码/DFFE 提取、且功能
   等价时，才允许把该信号加入 `config/quality_policy.json` 的 `lec.blacklist`。
   blacklist 不得用于掩盖真实的不等价。

注意：第 5 节“最后一个 else 写 `else ;` 表示保持”的简写**不适用于 F2 的
`state_next`**；次态必须显式写出保持状态的**常量**。验证方式：把
`rtl/ch_num_gen.v` 的 F2 按本节改写（每个保持分支写状态常量）后，空 blacklist
下 `lec` 从 2 个 unproven 变为 `unproven=0`（34/34 proven）。
