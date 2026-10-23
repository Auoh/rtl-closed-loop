# 验收审查记录（2026-10-23）

本文件记录 `rtl-closed-loop` 的成果验收过程、已修复与待修复问题，随代码一起纳入版本管理。

## 验收方式

不只看代码，而是**实际调用技能**完成全新 demo，再按技能自己声明的效果逐项核对产物：

- demo 一：`uart_tx`（8N1 发送器），预算 320/40/25
- demo 二：`rr_arbiter`（3 路轮询仲裁），预算 120/8/15
- demo 三：`pwm_gen`（8 位 PWM），预算 200/50/25

每个 demo 走完 9 步闭环，按 A1-A12 判定（规格化、参考模型独立性、sim、负向演练、
lint、PPA 预算、LEC、formal、快照对比、优化迭代、交付、文档可独立走完）。
**连续 3 次通过**才算最终验收。评审不修改交付文件，缺陷以「文件:行号 + 复现命令 +
期望结果」发回修复。

## 当前进度

| 项目 | 状态 |
|---|---|
| streak | 0 / 3 |
| demo 1 `uart_tx`（v1.1.1） | FAIL（A7、A12；其余 10 项通过） |
| demo 1 `uart_tx`（v1.1.2 重跑） | FAIL（仅 A12；A1-A11 全过，空 blacklist 下 LEC 21/0） |
| demo 1 `uart_tx`（v1.1.3 重跑） | **PASS**（A1-A12 全过；streak 1/3） |
| demo 2 `rr_arbiter`（v1.1.4） | **PASS**（A1-A12 全过；streak 2/3） |
| demo 3 `pwm_gen` | 未开始 |

demo 1 关键数据（v1.1.2 重跑）：sim `checks=4000 errors=0`；`--bug` rc=1（errors=1440）；
PPA 优化 73/19/6 → 70/18/6；LEC `blacklist=[]`、proven=21；compare rc 0。
A12 未过的原因见 D8/D14（formal harness 与 LEC-FSM 文档缺口，已由 v1.1.3 补齐）。

demo 1 关键数据（v1.1.3 重跑，评审独立复跑）：全新工作区、未设环境变量；
`all` rc=0，sim `checks=4000 errors=0`，`--bug` rc=1（384 errors）；
PPA 63/18/5（预算 320/40/25）；LEC `blacklist=[]` proven=21 unproven=0；
formal `DONE (PASS)`、`engines=["abc pdr"]`；compare rc=0（70/18/8 → 63/18/5）。
评审额外核验：TB 能捕获位序反转（1761 errors）与 busy 提前释放（384 errors）；
形式化对「stop 位恒低」注入返回 FAIL，对恒假断言返回 FAIL（证明非空证明）；
用 `docs/uart_tx_baseline.v` 独立综合复现基线 70/18/8。
**A12 通过**：`gap_log.md` 无阻塞级缺口；其中 G5「R7 与 §13 冲突」经复核为误报
（`coding_style.md:192-194` 已明确 §13 优先）。

demo 2 关键数据（v1.1.4，评审独立复跑）：`all` rc=0；sim `checks=534 errors=0`；
`--bug` rc=1（151 errors）；PPA 54/3/12 → 30/2/10（预算 120/8/15）；
LEC `blacklist=[]` proven=11 unproven=0；formal `DONE (PASS)`、`engines=["abc pdr"]`；
compare rc=0（三项改善）。评审额外核验：TB 捕获多路同时授权（235 errors）；
把 `prio_mask` 固定为全 1（退化为固定优先级）后 formal rc=1（frame 13）；
`docs/rr_arbiter_baseline.v` 独立综合复现 54/3/12。gap_log 无阻塞项，A12 通过。

## 已修复

| ID | 级别 | 位置 | 问题 | 修复 |
|---|---|---|---|---|
| D1 | P1 | `scripts/setup.ps1:243` | `-Install` 在源==目标时先删目标再同路径 robocopy，把缓存工具链清成 0MB | `51c1ac3`：删除前 `GetFullPath` 比较，相同则跳过；并校验源含 `bin\iverilog.exe` |
| D2 | P3 | `docs/cleanroom_verify.md` | 「未 push」与「已按用户授权推送」矛盾 | 已改为「已按用户授权 push」 |
| D3 | P3 | `docs/cleanroom_verify.md` | v1.1.1 段写「尚未 push」与事实不符 | 已改为「已 push origin/main 与远端 tag v1.1.1（6b9b08e）」 |
| D4 | P1 | `scripts/rtlq.py` | `_find_iverilog` 不识别 `<root>/iverilog/bin`，回退到含空格 PATH 后 sim 失败（rc=255） | `dd3a5a1`：支持两种缓存布局；doctor 对含空格路径告警；sim 命令解析失败时自动改用缓存工具重试 |
| D5 | P1 | `scripts/rtlq.py` | quality-lite 无 `yosys-smtbmc`，sby 默认引擎必然 ERROR | `dd3a5a1`：运行前校验 `[engines]`；缺失或 smtbmc 时 ERROR 并提示 `[engines] abc pdr` |
| D6 | P3 | 多处 | 文档示例越界、头注释路径错、`-Top`/`--top` 不一致、日志路径不符、`-NoGui` 未提及、gen_tb 重生成丢状态、config 无字段说明 | `dd3a5a1`：示例移入 `references/examples/`；文档统一 `--top` 与 `report/logs/sim_<top>.log`；gen_tb 新增 `REF_DECLS_BEGIN/END` 保留区 |
| D7 | P2 | demo 侧 | 首轮 demo 自设 LEC 黑名单 | 重跑时 `blacklist=[]` 通过（21/0），非技能缺陷 |
| D8 | P2 | `references/examples/formal/` | sby prove 的 anyinit/复位假设写法无文档、无模板 | `be2c8f7`：新增 `demo_ctr` 全套模板（rtl/sby/fv/README），说明 `formalff -ff2anyinit` 与复位保持 |
| D9 | P2 | `references/coding_style.md:130` | TB 激励规范与 `toolchain.md` 矛盾（沿后 `#1` vs NBA 零延时） | `be2c8f7`：统一为 NBA 零延时，`#1` 列为反例 |
| D10 | P2 | `scripts/rtlq.py` | `formal.engines` 只保留首 token（`abc pdr` → `["abc"]`） | `be2c8f7`：保留整行 |
| D11 | P3 | quality-lite | 无 `yosys-witness`，失败无可读轨迹 | `be2c8f7`：文档说明限制与替代调试路径（logfile、`mode bmc` + `abc bmc3`、定向仿真） |
| D12 | P3 | `rtlq.py all` | `all` 退出码不反映内嵌 Baseline vs Current 的 PPA 回退 | `be2c8f7`：新增 `--fail-on-regression`，默认行为不变 |
| D13 | P3 | `toolchain.md` | sby `[files]` 相对基准不明确 | `be2c8f7`：明确相对 `-W` 工作区，并写入模板注释 |
| D14 | P2 | `coding_style.md §13` | 空黑名单下 FSM 的 LEC 写法无指导 | `be2c8f7`：`fsm_encoding="none"` + 全分支显式次态 |
| D15 | P2 | `scripts/rtlq.py:56` | 默认 `lec.blacklist=["state_next"]` 静默掩盖 unproven | `bfe9c45`：默认空；输出 `unproven_signals` 与 `[HINT]`（仅提示不排除）；显式空 `--blacklist` 不再被 `or` 回退 |
| D16 | P3 | `scripts/gen_tb.py:12` | docstring 时序描述与生成代码相反 | `bfe9c45`：改为「上升沿 NBA 驱动、负沿检查」 |
| D17 | P3 | `references/workflow.md:18-20` | 未说明 REF_DECLS 状态需 `initial` 初始化 | `bfe9c45`：补说明与 3 行示例，`toolchain.md:132` 同步 |
| D18 | P3 | `scripts/format.ps1:42,49,57,60` | 裸 `python`，Store 桩下失败 | `bfe9c45`：`rtl-tools.ps1` 新增 `Find-RtlPython`（跳过 exit 49 桩），format/run/wave 复用 |
| D19 | P3 | `references/examples/formal/` | 缺协议级多周期属性模板 | `bfe9c45`：新增 `pulse_stretch` rtl/sby/fv + README（影子计数器、boot 位宽坑） |
| D20 | P3 | `scripts/gen_tb.py:88-90,216-225` | 定向激励无保留区 | `bfe9c45`：新增 `DIRECTED_BEGIN/END`，重生成保留 |

D4 复验证据（v1.1.2，我的独立复现）：
- 无 `RTL_TOOLCHAIN`、工作区无 `tools/`：`doctor` rc 0，iverilog 指向 `C:\rtl-toolchain\iverilog\bin`；`sim` rc 0，`checks=4478 errors=0`。
- 强制 `RTL_TOOLCHAIN=D:/01 software/iverilog`：首次 `compile_rc=255`，自动重试缓存后 rc 0，`tool_retry.first_rc=255/retry_rc=0`；`doctor` 输出含空格 `[WARN]`。

D5 复验证据：删除 `[engines]` → rc 1「缺少可用的 [engines] 段」+ HINT；`[engines] smtbmc` → rc 1「未提供 yosys-smtbmc」+ HINT；`[engines] abc pdr` → rc 0，`DONE (PASS)`。

D6 复验证据：`gen_tb.py` 生成后写入 `REF_DECLS` 声明与参考模型逻辑，重新生成后两处均保留（`ref_cnt` 2 处、`REF_MARK` 1 处）；文档中已无技能外绝对路径。

D1 复验证据：缓存根已存在时重复 `-Install` → rc 0、打印「源与目标相同，跳过」、
1231 文件/87MB 前后不变；无效源 → rc 1、缓存不变；`doctor` 11 项 OK；
离线包内 `setup.ps1` 含同样守卫，`VERSION = "1.1.1"`。

D8-D14 复验证据（v1.1.3，我的独立复现）：
- D8/D10：清空临时工作区，按模板原样跑 `formal demo_ctr` → rc 0 `DONE (PASS)`，`report/formal.json` 的 `engines` 为 `["abc pdr"]`。
- D14：把交付版 `ch_num_gen.v` 复制到临时工作区、清空 blacklist → 2 个 `state_next` unproven；按 §13 加 `fsm_encoding="none"` 并把每个分支（含保持）显式赋值后 → `proven=34 unproven=0`。
- D12：`reg_adder` 临时副本加 1 位 keep 寄存器（48 cells/10 ff，预算内）：默认 `all` rc 0 但内嵌基线显示 `FAIL (cells, ff)`；加 `--fail-on-regression` → rc 1、`quality.json status=FAIL`。
- D9/D11/D13：`coding_style.md` 已无「沿后 #1」；`toolchain.md:57/68` 与 README 写明无 `yosys-witness`、`[files]` 相对 `-W` 工作区。

## 待修复（v1.1.4 demo 2 发现，2026-10-23）

| ID | 级别 | 位置 | 问题 | 期望修复 |
|---|---|---|---|---|
| D21 | P2 | `references/coding_style.md:162-163` | §13 正文要求保持分支写 `state_next = state;`，但反馈赋值正是 `opt_dff` 识别 DFFE 的形态；同节示例写的却是状态常量。实测按正文写法（if/else + `state_next = state`）→ 2 个 `state_next` unproven；改成每分支常量 → 11/0 | 正文改为「保持分支写该状态的常量（如 `state_next = ST_IDLE;`），不要写 `state_next = state;`」，并说明反馈赋值仍会生成 `$adffe`；示例与正文统一 |
| D22 | P3 | `scripts/gen_tb.py:254` | 生成 `$fatal(1, "TEST FAILED: %%0d ...")`，Icarus 原样打印 `%0d`。FAIL/rc 判定不受影响 | 模板改为 `%0d`（生成文件里应为单 `%`） |
| D23 | P3 | `scripts/gen_tb.py:98,241` | 注释统一要求参考模型用 `*_cap`；该约定只适用于寄存器输出。组合输出在 negedge 已对应新输入，用 `*_cap` 会落后一拍 | 注释区分：寄存器输出用 `*_cap`，组合输出用当前输入 |
| D24 | P3 | `scripts/rtlq.py:877,899-900` | `sim --wave` 与普通 sim 复用同一 vvp 与 `sim_<top>.log`，后跑覆盖前跑日志 | wave 的 vvp/日志加 `_wave` 后缀，或文档说明会覆盖 |

复现证据（D21，评审独立复现）：`rr_arbiter` 同一状态机：
- if/else + `else state_next = state;` → rc=1，proven=9 unproven=2（`unproven_signals=["state_next"]`）；
- 同一 if/else 结构改每分支常量（`= ST_P0/1/2`）→ rc=0，proven=11 unproven=0；
- 交付版 `case(state)` + 常量 → rc=0，11/0。

### D15-D20（v1.1.4 已修复，证据）

### D15-D20 原始问题（v1.1.3 重跑发现，已修复）

| ID | 级别 | 位置 | 问题 | 期望修复 |
|---|---|---|---|---|
| D15 | P2 | `scripts/rtlq.py:56` | `DEFAULT_POLICY` 的 `lec.blacklist.default = ["state_next"]`：用户未创建 `config/quality_policy.json` 时，LEC 静默排除 `state_next`，可能把真实 unproven 掩盖成 PASS | 默认改为 `[]`；仅在用户显式配置时排除。若确有工具重编码场景，可在 unproven 仅剩 `state_next` 时打印 HINT（指向 `coding_style.md §13`），但不得自动排除 |
| D16 | P3 | `scripts/gen_tb.py:12` | 模块 docstring 写「正沿采样、负沿驱动」，与生成代码（上升沿 NBA 驱动、负沿检查）及生成文件头注释矛盾 | 改为「上升沿 NBA 驱动、负沿检查」 |
| D17 | P3 | `references/workflow.md:18-20`、`references/toolchain.md:126-131` | 只说明跨拍状态放 `REF_DECLS`，未说明需要 `initial` 初始化；生成的 `ref_*` 默认为 X，首次比较会传播 X | 文档补充「REF_DECLS 状态需在 `initial` 中赋初值」，并给 3 行示例 |
| D18 | P3 | `scripts/format.ps1:42,49,57,60` | 调用裸 `python`，未复用 `rtlq.py` 的解释器探测；`python` 为 Store 桩时格式化直接失败 | 采用与 `rtlq.py` 相同的解释器探测（`py -3`/`python3` 回退） |
| D19 | P3 | `references/examples/formal/` | 仅有计数器模板，无协议级多周期属性示例（影子计数器/位边界），本次只能自行设计 | 增加一个「单拍脉冲 + 多拍输出」的最小协议模板（DUT + sby + fv），说明影子计数器写法 |
| D20 | P3 | `scripts/gen_tb.py:88-90,216-225` | 生成的主循环会覆盖手工定向激励，且无保留区；规格要求补充定向边界用例时无处安放 | 在生成模板中增加 `DIRECTED_BEGIN/END` 保留区（或保留的 `initial` 段），文档同步说明 |

复现证据（D15，评审独立复现）：同一份 `ch_num_gen.v`：
- 空 blacklist：`rtlq.py lec` → rc=1，`Found a total of 2 unproven $equiv cells`；
- 删除 `config/quality_policy.json`（走默认）：rc=0，`[PASS] proven=32 unproven=0`，
  `report/logs/lec_blacklist_ch_num_gen.txt` 为 `state_next`。

误报排除（本轮复核后不成立，不修）：
- G5「`coding_style.md` 第 5 节 `else ;` 与第 13 节显式保持冲突」：同文件 192-194 行
  已明确 §13 对 F2 `state_next` 优先，属阅读顺序问题。
- G6「`--bug` 只有一个 `INJECT_BUG` 宏、无法选择注入点」：技能契约只要求负向演练
  至少一次并可检出；多注入点属增强需求，不是缺陷。

### v1.1.4 复验证据（评审独立复现，`bfe9c45`）

- D15：`ch_num_gen.v` + 无策略文件 → rc=1，`proven=32 unproven=2`，`blacklist=[]`，
  `unproven_signals=["state_next"]`，打印 HINT；`--blacklist`（空参数）→ rc=1；
  显式 `{"ch_num_gen":["state_next"]}` → rc=0。
- D16：docstring 已为「上升沿 NBA 驱动、负沿检查」。
- D17：`workflow.md:18-30` 与 `toolchain.md:132` 均含 `initial` 赋初值说明与示例。
- D18：PATH 前置 `python.bat`/`python3.bat`（均 exit 49）→ `format.ps1` rc=0、
  `FORMAT OK`，探测回退到 `py`。
- D19：模板原样 `formal pulse_stretch` → rc=0 `DONE (PASS)`、engines `["abc pdr"]`；
  把 `cnt == LATENCY-1` 改早一拍 → rc=1 `DONE (FAIL)`。
- D20：生成后在 `DIRECTED_BEGIN/END` 内写入标记，重生成后标记仍在；TB 用 iverilog 编译通过。
- 回归：`reg_adder` 在 v1.1.4 下 `all` rc=0（47/9/15，lec 9/0）；`py_compile` 通过。

D4/D5 原始复现命令（已修复，保留供回归）：

```
rtlq.py sim -W <workspace> --top uart_tx     # 不设 RTL_TOOLCHAIN
→ 修复前：compile_rc=255，'D:\01' 不是内部或外部命令
删除 sby 的 [engines] 段后 rtlq.py formal   # 修复前：sby rc=16
```

## 误报排除（复核后不成立，不修）

- sby `[files]` 路径语义：`references/toolchain.md:157` 已说明会复制到 `report/formal/<top>`。
- `_STATUS_RANK` 与 `_status_rank` 语义不一致：`_worst` 先过滤 SKIP，两者行为不冲突。

## 版本与备份

- `v1.1.0`（`7d791e8`）：D1 修复前的备份基线，已推送。
- `v1.1.1`（`51c1ac3`）：D1 修复，已推送；远端 annotated tag `6b9b08e`。
- `v1.1.2`（`dd3a5a1`）：D4/D5/D6 修复 + README，已推送。
- `v1.1.3`（`be2c8f7`）：D8-D14 修复（formal 模板、FSM/LEC 文档、engines 字段、回归门禁），已推送。
- `v1.1.4`（`bfe9c45`）：D15-D20 修复（LEC 默认 blacklist、TB 定向区、Python 探测、协议级 formal 模板），已推送。
- 流程：确认问题点后先把当前状态打 tag 并 push，再执行修改；修复复验通过后打版本 tag 并 push。
