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
| streak | 3 / 3 — **验收通过**（v1.1.6，无未修复 P1/P2） |
| demo 1 `uart_tx`（v1.1.1） | FAIL（A7、A12；其余 10 项通过） |
| demo 1 `uart_tx`（v1.1.2 重跑） | FAIL（仅 A12；A1-A11 全过，空 blacklist 下 LEC 21/0） |
| demo 1 `uart_tx`（v1.1.3 重跑） | **PASS**（A1-A12 全过；streak 1/3） |
| demo 2 `rr_arbiter`（v1.1.4） | **PASS**（A1-A12 全过；streak 2/3） |
| demo 3 `pwm_gen`（v1.1.5） | **PASS**（A1-A12 全过；streak 3/3） |

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

demo 3 关键数据（v1.1.5，评审独立复跑）：`all` rc=0；lint style=0 / slang 0 告警；
sim `checks=1666 errors=0`；`--bug` rc=1（27 errors，定向 B2/B6/B7/B8 捕获 duty 差一）；
PPA 117/8/11 → 109/8/11（预算 200/50/25，compare rc=0，cells 改善）；
LEC `blacklist=[]` proven=9 unproven=0；formal `DONE (PASS)`、`engines=["abc pdr"]`。
评审额外核验：把 `cnt <= duty` 改为 `<` 后 formal rc=1 `DONE (FAIL)`（非空证明）；
用 `gen_tb.py` 重新生成 TB 仅空白差异，参考模型不例化 DUT、`REF_DECLS` 已 `initial`；
基线快照（10:04）先于优化快照（10:08），`optimization_iteration.md` 记录四种变体与退出码。
gap_log 10 项无阻塞（A12 通过），其中 G2 经评审独立复现升级为 D25（P2），G3 判定为误报。

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
| D21 | P2 | `references/coding_style.md:6-7,106,164-168` | §1/§7/§13 正文要求保持分支写 `state_next = state;`（反馈赋值仍生成 `$adffe`），与示例的常量写法矛盾 | `26e4f6d`：统一为每分支（含保持/`default`）写状态常量，明确禁止 `state_next = state;` 与块首兜底；`README.md`、`workflow.md`、LEC `[HINT]`、`CHANGELOG` 同步 |
| D22 | P3 | `scripts/gen_tb.py:256` | 生成的 `$fatal` 格式串写成 `%%0d`，Icarus 原样打印 `%0d` | `26e4f6d`：改为 `%0d`，失败时输出真实错误数 |
| D23 | P3 | `scripts/gen_tb.py:13,97-98,142,188,242` | 注释一律要求参考模型用 `*_cap`，对组合输出会落后一拍 | `26e4f6d`：注释区分寄存器输出（用 `*_cap`）与组合输出（用当前输入）；`coding_style.md §11`、`toolchain.md` 同步 |
| D24 | P3 | `scripts/rtlq.py:872,894-895,910-911,939-941` | `sim --wave` 复用同一 vvp 与 `sim_<top>.log`，覆盖普通 sim 产物 | `26e4f6d`：wave 运行使用 `_wave` 后缀的 vvp/编译日志/运行日志；`toolchain.md` 记录产物命名 |
| D25 | P2 | `scripts/rtlq.py:1316-1318,184-214` | formal 超时残留 `yosys-abc.exe` 锁目录，下次 `shutil.rmtree` 抛未捕获 `PermissionError` | `f3f4549`：Popen + 进程树终止（`taskkill /T /F` / `killpg`），`rmtree` 重试后转 ERROR+HINT，超时结果附清理提示 |
| D26 | P3 | `references/examples/formal/README.md` | 数值/计数型不变式无证明策略（G1） | `f3f4549`：新增逐拍参考等式 + 代表性常量配置 + pdr 局限 |
| D27 | P3 | `references/examples/formal/README.md` | 无配置输入保持写法（G4） | `f3f4549`：新增 `*_hold` 捕获 + `assume` 保持模式 |
| D28 | P3 | `references/workflow.md:29-34`、`scripts/gen_tb.py` | 未说明 `reference_model` 每周期调用一次（G5） | `f3f4549`：workflow §3 与 gen_tb 头/定向区注释补充 |
| D29 | P3 | `scripts/gen_tb.py:41-45,108-113` | 端口声明缩进不一致（G6） | `f3f4549`：统一 4 空格，重新生成验证 |
| D30 | P3 | `SKILL.md:60`、`scripts/rtlq.py:1366,1709` | negative 阶段触发条件未文档化（G7） | `f3f4549`：SKILL/workflow/README 写明 `INJECT_BUG` 触发与 SKIP 语义 |
| D31 | P3 | `references/toolchain.md:59-61` | `depth` 在 prove 下不是帧上界（G8） | `f3f4549`：README/toolchain 说明 depth 仅约束 bmc |
| D32 | P3 | `references/examples/formal/README.md:55-57`、`scripts/rtlq.py:1678` | 变异证据无归档位（G9） | `f3f4549`：约定 `report/mutation/<top>/`，summary 自动列出 |
| D33 | P3 | `references/workflow.md:56,71-73` | 无 baseline vs 优化后 RTL 等价流程（G10） | `f3f4549`：workflow §8.1 新增 `equiv_make/async2sync/equiv_induct` recipe |

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

### D21-D24 原始问题（v1.1.4 demo 2 发现，已由 v1.1.5 修复）

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

### D21-D24 复验证据（v1.1.5，评审独立复现，`26e4f6d`）

- D21：用 v1.1.5 重跑上述对照 —— 反馈保持版 `rtlq.py lec` rc=1，proven=9 unproven=2，
  `unproven_signals=["state_next"]`，`[HINT]` 已改为「`else ;` 或块首 `state_next = state;`
  兜底保持……每个分支显式赋值状态常量」；常量版 rc=0 proven=11 unproven=0。
  文档核对：`coding_style.md` §1/§7/§13、`README.md` §7.2、`workflow.md` 均改为
  「保持分支写该状态的常量」，§13 示例（`ST_IDLE`/`ST_BUSY`）与正文一致。
  补充观察：并非所有反馈写法都会触发 DFFE（逐状态嵌套 `else state_next = state;`
  实测 9/0），新文档「部分分支结构下」的措辞与此相符。
- D22：重新生成 `tb_rr_arbiter.v`，`$fatal` 行为
  `$fatal(1, "TEST FAILED: %0d error(s) found", errors);`；`sim --bug` rc=1，
  日志输出 `TEST FAILED: 151 error(s) found`，无字面 `%0d`。
- D23：生成 TB 头部/捕获区/参考模型处均含新措辞（寄存器输出 `*_cap`、组合输出用当前输入）；
  `coding_style.md §11` 与 `toolchain.md`「激励与时序约定」同步；重生成后手写
  `reference_model` 与 `DIRECTED` 区保留，`sim` 仍 `checks=534 errors=0`。
- D24：普通 `sim` 后跑 `sim --wave`：`sim/rr_arbiter.vvp` 与
  `report/logs/sim_rr_arbiter.log` 保留，新增 `rr_arbiter_wave.vvp`、
  `sim_compile_rr_arbiter_wave.log`、`sim_rr_arbiter_wave.log`，`sim/wave.vcd` 非空；
  两次运行均 rc=0、checks=534。
- 回归（v1.1.5，评审独立复跑 `rtlq.py all`）：`rr_arbiter` rc=0
  （534/0，negative PASS，30/2/10，LEC 11/0，formal PASS）；`uart_tx` rc=0
  （4000/0，63/18/5，LEC 21/0，formal PASS）。`py_compile` 通过。

## D25-D33 原始问题（v1.1.5 demo 3 发现，已由 v1.1.6 修复）

| ID | 级别 | 位置 | 问题 | 期望修复 |
|---|---|---|---|---|
| D25 | P2 | `scripts/rtlq.py:1316-1318,184-214` | formal 超时只杀 sby 子进程，残留 `yosys-abc.exe` 持有 `report/formal/<top>`；下一次 `formal`/`all` 在 `shutil.rmtree` 抛未捕获 `PermissionError`（WinError 32） | 超时杀整个进程树；`rmtree` 捕获 `PermissionError` 并给出残留 PID/清理提示；文档注明 |
| D26 | P3 | `references/examples/formal/README.md` | 无数值/计数型不变式的证明策略（G1）；abc pdr 对一般累加不变式不可解 | 补“逐拍参考等式 + 代表性常量计数”策略与 pdr 局限说明 |
| D27 | P3 | `references/examples/formal/README.md` | 无“保持配置输入恒定”的 formal 写法（G4） | 补 reset 窗口捕获 + `assume` 保持模式 |
| D28 | P3 | `references/workflow.md:18-30`、`scripts/gen_tb.py` | 未说明 `reference_model` 必须每检查周期调用一次（G5） | 补充说明与失败症状 |
| D29 | P3 | `scripts/gen_tb.py:41-45,108-113` | 生成端口声明缩进不一致（G6，纯观感） | 统一缩进 |
| D30 | P3 | `SKILL.md:60`、`scripts/rtlq.py:1366,1709` | `all` 的 negative 阶段仅在顶层 RTL 含 `INJECT_BUG` 时运行，未文档化（G7） | 文档写明触发条件与 SKIP 原因 |
| D31 | P3 | `references/toolchain.md:59-61` | prove + abc pdr 下 `depth` 不是帧上界（G8） | 说明 `depth` 仅约束 bmc |
| D32 | P3 | `references/examples/formal/README.md:55-57`、`scripts/rtlq.py:1678` | 变异证据无受支持的归档位置（G9） | 约定 `report/mutation/` 并由文档引用 |
| D33 | P3 | `references/workflow.md:56,71-73` | 无 baseline RTL vs 优化后 RTL 的等价性流程（G10） | 补 `equiv_make/async2sync/equiv_induct` 可复制命令或脚本 |

D25 复现证据（评审独立复现）：副本工作区把 `formal.timeout_s` 设为 5 →
`rtlq.py formal` 5 s 超时；`Get-CimInstance Win32_Process -Filter "name='yosys-abc.exe'"`
显示残留进程持有 `report/formal/pwm_gen`；再次 `rtlq.py formal` → rc=1，
`PermissionError: [WinError 32]` traceback；残留进程退出后 `rmtree` 恢复正常。

### D25-D33 复验证据（v1.1.6，评审独立复现，`f3f4549`）

- D25（主路径）：副本工作区 `formal.timeout_s=5` → 第一次 `formal` rc=1，日志含
  `[rtlq] TIMEOUT after 5 s; killed process tree: taskkill /T /F /PID <pid>`，
  立即检查无残留 `yosys-abc.exe`；第二次 `formal` rc=1，日志无 `Traceback`，
  干净超时；恢复 `timeout_s=300` → rc=0 `DONE (PASS)`，仍无残留进程。
- D25（清理失败路径）：用独立进程保持 `report/formal/pwm_gen/engine_0/logfile.txt`
  打开，再跑 `formal` → rc=1，输出 `[ERROR] 无法清理上一次的形式验证目录
  （PermissionError: [WinError 32] ...）` 与 `[HINT]`，无 Traceback。
- D26/D27/D31：`references/examples/formal/README.md` 新增「数值/计数型不变式的
  证明策略」「保持配置输入恒定」「depth 与 prove 的关系」「变异证据归档」四节；
  `toolchain.md` 同步 depth、残留进程、单 task 三点。
- D28：`workflow.md` §3 与 `gen_tb.py` 头/定向区注释要求每周期调用
  `reference_model; check_outputs;`。
- D29：重新生成 TB，`clk`/`period`/`duty`/`pwm_out`/`rst_n` 声明均为 4 空格。
- D30：`SKILL.md:60-63`、`workflow.md` §5、README 第 6 节写明 negative 仅在顶层
  RTL 含 `INJECT_BUG` 时运行，否则 SKIP 并注明原因。
- D32：在副本放入 `report/mutation/pwm_gen/offbyone.log` 后运行
  `rtlq.py report`，`summary.md` 出现「变异/反例证据」并列出该文件。
- D33：按 `workflow.md` §8.1 的 `equiv.ys` 对 `docs/rtl_baseline/pwm_gen.v` 与
  优化后 `rtl/pwm_gen.v` 运行 quality-lite Yosys → rc=0，
  `9 are proven and 0 are unproven`，`Equivalence successfully proven!`。
- 回归（v1.1.6，评审独立复跑 `rtlq.py all`）：`pwm_gen` rc=0（1666/0、109/8/11、
  LEC 9/0、formal PASS）；`rr_arbiter` rc=0（534/0、30/2/10、LEC 11/0）；
  `uart_tx` rc=0（4000/0、63/18/5、LEC 21/0）；`py_compile` 通过。

误报排除（run3 gap）：G3「多任务 sby 被误判 PASS」——sby 在 rtlq 传 `-d` 时直接拒绝
多任务（`Exactly one task is required when workdir is specified`），rtlq 返回 FAIL，
误判路径不可达；`toolchain.md` 已注明 rtlq 只支持单 task。

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
- `pre-fix-20261023-0928-D21`（`9a787a5`）：D21-D24 修复前备份，已推送。
- `v1.1.5`（`26e4f6d`）：D21-D24 修复（F2 保持分支文档、`$fatal` 格式、`*_cap` 适用性、wave 产物命名），已推送。
- `pre-fix-20261023-1018-D25`（`bc6328f`）：D25-D33 修复前备份（代码同 v1.1.5），已推送。
- `v1.1.6`（`f3f4549`）：D25-D33 修复（formal 超时进程树清理、清理失败 ERROR+HINT、数值型 formal 策略、配置保持、TB 调用纪律、缩进、negative 触发、depth 语义、变异归档、优化等价 recipe），已推送。
- 流程：确认问题点后先把当前状态打 tag 并 push，再执行修改；修复复验通过后打版本 tag 并 push。

## 最终结论（2026-10-23）

连续 3 个独立 demo（`uart_tx` v1.1.3、`rr_arbiter` v1.1.4、`pwm_gen` v1.1.5）
均按 A1-A12 通过，streak = 3/3；v1.1.5 发现的 D25（P2）与 D26-D33（P3）
已由 v1.1.6 修复并通过评审独立复验。截至 `v1.1.6`（`f3f4549`），无未修复
P1/P2，**验收通过**。

## 方法论补强（2026-10-23 起）

验收结束后用户提出三项方法论问题：需求→测试点的分解与完备性、比对与时序正确性
的保证边界、综合与 PPA 数据的可信度。按 T1 > T2 > T3 逐项核查，每轮只推进一项。

### D34（P2）缺少“测试点分解与完备性评审”环节（T1）

**现象**：流程从规格直接跳到测试环境，没有先把需求拆成可验证的测试点、论证完备性，
再设计用例；需求、测试点、用例之间没有追溯关系。

**证据**：
- `references/workflow.md:7-10`（§1 规格化）→ `:12-14`（§2 RTL）→ `:16-36`
  （§3 测试环境），中间无测试点步骤。
- `SKILL.md:55-67` 六步工作流同样从“规格化”直接到“测试环境”；`:83` 交付仅笼统
  写“覆盖点”。
- `references/workflow.md:136-145` 交付清单无测试计划文件。
- 全仓检索零命中：
  `grep -rniE "测试点|test ?point|testplan|traceab|追溯|覆盖矩阵" <skill>` → 无输出。
- 实测 run3 `docs/demo_spec.md`：有 B1–B9 边界表与 PASS 判据，但没有“需求 →
  测试点 → 用例/断言 → 结果”映射，无法机械判定 B5/B6 等条目是否覆盖了全部需求
  分支，完备性只能靠人临场判断。

**期望**：
1. 新增测试计划模板 `references/templates/testplan.md`（产物
   `docs/testplan_<module>.md`），列：需求 ID、测试点 ID、类别（功能/边界/异常与
   非法配置/复位/接口时序/性能约束）、完备性判据、用例载体（DIRECTED 段、随机段、
   negative 注入点、formal 属性名）、结果。
2. `references/workflow.md` 在 §2 与 §3 之间新增「§2.5 测试点分解与完备性评审」，
   规定因果顺序：规格条目 → 测试点 → 完备性检查 → 用例设计 → 执行。完备性至少
   要求：每条需求 ≥1 测试点；每个测试点 ≥1 用例或断言；非法/边界配置逐条显式；
   复位与接口时序单独成点。
3. `SKILL.md` 工作流插入该步；交付清单（`workflow.md:136-145`、`SKILL.md:83`）
   增加 `docs\testplan_<module>.md`，“覆盖点”改为引用该追溯矩阵。
4. 验收方式：用一个新 demo（如 fifo）按新流程产出 testplan，逐条核对无孤儿需求。
   工具级强检查暂不做（静态匹配 TB 易误报），可后续评估 `plan-check` 软告警。

**状态**：2026-10-23 22:50 已发 rtl-expert-54，待修复。

### 备份与追踪

- `pre-fix-20261023-2245-D34`（`e13cc1f`，annotated `d67ab9a`）：D34 修复前
  备份，已推送并 `git ls-remote` 确认。
- 议题追踪：`D:/tmp/rtl-acceptance/topics.md`（T1/T2/T3）。

### D35（P2）比对/时序保证只存在于约定中，文档未写边界，`!=` 可静默漏报 X（T2）

**现象**：用户问“工具在比对上怎么保证、怎么保证时序正确”。实测表明：保证来自
TB 约定而非工具检查；且文档从未说明比较必须用 `!==`，手写 TB 用 `!=` 时全 X 的
DUT 会 0 报错、打印 PASS。

**实验**（`D:/tmp/rtl-acceptance/t2-timing`，Icarus Verilog，零延时单时钟）：

| 变体 | 约定 | DUT | checks | errors | 结果 |
|------|------|-----|--------|--------|------|
| V1 | 负沿比较 + `*_cap` + 当前输入 + `!==` | 正确 | 22 | 0 | PASS |
| V2 | 改为**上升沿比较** | 正确 | 23 | 44 | FAIL（误报） |
| V3 | 组合输出改用 `*_cap` | 正确 | 22 | 18 | FAIL（误报） |
| V4 | 负沿比较但用 **`!=`** | 全 X | 22 | 0 | **PASS（静默假通过）** |
| V5 | 负沿比较 + `!==` | 全 X | 22 | 44 | FAIL（正确） |
| V6 | 负沿比较 + `!==` | `q<=q+d+1` | 22 | 44 | FAIL（正确） |

**证据（文档/代码）**：
- `references/coding_style.md:130-132` 只写驱动/捕获与 `*_cap` 用法，全文无 `!==`。
- 全仓 `!==` 仅出现在 `scripts/gen_tb.py:203`；文档零解释。
- `scripts/rtlq.py:994-1001`：`sim` 状态只取 stdout 的 `RESULT: PASS/FAIL`
  字面量与退出码；不检查比较运算符、检查次数或输出覆盖率。
- 无“保证/不保证”小节（现有“不覆盖”仅指历史快照）。

**期望**：
1. `references/toolchain.md` 新增「比对与时序：保证与不保证」：放入上表；明确
   ① 比较必须 `!==`/`===`，`!=` 遇 X/Z 为 X、`if` 视为假 → 静默通过；
   ② 检查必须在负沿（沿后稳定）进行，上升沿同拍比较看到 NBA 前的旧值；
   ③ 寄存器输出用 `*_cap`，组合输出用当前输入；
   ④ `rtlq.py` 只认 `RESULT:` 字面量与退出码，不验证 TB 有效性，negative 注入
   是唯一自动发现“TB 失效”的手段；
   ⑤ 不覆盖门级/延迟/STA、CDC、异步毛刺、多时钟、组合环。
2. `references/workflow.md` §3 增加硬性检查项：TB 每一处输出比较使用 `!==`。
3. 不改判定逻辑；如需工具提示，只做软 WARN（`!=` 在 TB 中普遍存在于计数器比较，
   强检查误报率高），本轮不要求。

**状态**：2026-10-23 22:55 已发 rtl-expert-54，待修复。

### D36（P2）PPA 跨版本比较无校验，synth 快照不记录工具版本（T3）

**现象**：`compare` 只比较阶段状态与 cells/ff/depth，从不检查两个快照的 Yosys
版本；跨版本比较静默 PASS，把工具差异当成设计 delta。`synth` 快照本身也不含
工具版本。

**实验**（`D:/tmp/rtl-acceptance/t3-ppa`，pwm_gen）：
- 同版本连跑三次 `synth`：cells=109 ff=8 depth=11 三次一致；`stat -json` 与
  `ltp -noff` 输出逐字节相同（sha256 相同）。
- `all` 快照 `20261023_225456_793841.json` 含 `tools.yosys = Yosys 0.66 ...`；
  复制后篡改 `tools.yosys = "Yosys 0.9 (FAKE)"`，再
  `rtlq.py compare --baseline baseline_fake_version.json`：
  六阶段全 `same`、delta 全 0、`RESULT: PASS`、rc=0，**无任何版本提示**。

**代码证据**：
- `scripts/rtlq.py:1622-1705` `_compare_snapshots` 不读 `tools`。
- `scripts/rtlq.py:1532-1545` `_snapshot_payload` 不透传版本；只有
  `rtlq.py:1862` 的 `all` 结果带 `tools: ctx.versions()`，`synth` 快照没有。
- `scripts/rtlq.py:1071-1139` 综合脚本与指标定义。

**期望**：
1. `_snapshot_payload` 对所有命令统一写入 `tools: ctx.versions()`（至少 yosys；
   建议 yosys/slang/iverilog），旧快照缺该字段时视为“不可判定”而非报错。
2. `_compare_snapshots` 增加版本比对：两边都有 `tools.yosys` 且规范化首行不同时，
   返回 `tool_mismatch` 字段并在 CLI 打印警告；默认状态 `WARN`（rc 0，不破坏现有
   流水线），新增 `--fail-on-tool-mismatch` 时置 `FAIL`；输出中带上两边版本。
3. `references/toolchain.md` 增加「PPA 语义与可比性」：cells/ff/depth 的定义
   （generic 映射、depth 不含 FF 与线延迟）、同版本同脚本同 RTL 的确定性实测、
   跨版本/跨工艺不可比、不是签核 STA。
4. 预算门禁逻辑保持不变。

**状态**：2026-10-23 22:57 已发 rtl-expert-54，待修复。

### D34/D35 独立复验（2026-10-23 23:05，通过）

用 `git archive 4ac9d78` 导出的只读副本独立复跑，不采信 peer 工作区产物。

**D34（T1）**
- 模板：`references/templates/testplan.md` 含主表 7 列、6 类固定类别、5 种载体
  命名、10 项完备性勾选、结果回填与评审结论。
- 流程：`workflow.md:16-34` §2.5 固定“规格条目 → 测试点 → 完备性检查 →
  用例设计 → 执行”，最低完备性 4 条；`SKILL.md:56-62` 插入第 3 步；
  `workflow.md:158-159` 与 SKILL 交付清单加入 `docs\testplan_<module>.md`。
- demo `d34-fifo`：在全新副本 `verify-d34/fifo` 跑
  `rtlq.py all --top sync_fifo` → **PASS rc0**：lint 0/0；sim checks=1050
  errors=0；negative expected=FAIL actual=FAIL；synth 97/39/6；lec 51/0；
  formal DONE (PASS)。与 peer 上报数字一致。
- 追溯：spec R1-R11、边界 B1-B11；testplan 21 行、21 个唯一 TP；每条需求 ≥1 点，
  每个点均有载体与结果；B1-B11 全部被引用（最少 2 次）。载体可定位：TB
  `DIRECTED_BEGIN` 下 B1-B11 注释齐全；formal P1-P10 断言存在；
  `NEG:full_guard` 注入点在 RTL `ifdef INJECT_BUG` 内，`sim_bug` 在 B4
  报 count/full/dout 失配；随机段种子 `32'h1234_5678`、1000 拍，日志统计
  full=141 empty=115 wr_full=70 rd_empty=60 simul=222，与 TP11.2 一致。

**D35（T2）**
- `toolchain.md:243-292` 新增「比对与时序：保证与不保证」，V1-V6 表与实测一致
  （V2 为 23/44），5 条保证 + 不保证清单 + 手写 TB 复核方法。
- `workflow.md:38` 硬性检查项、`SKILL.md:93` 硬性约束均已加入。
- `scripts/gen_tb.py:203` 仍是唯一比较点且用 `!==`；无单 `!=`。
- 复跑 V1-V6：22/0 PASS、22/44 FAIL、22/44 FAIL、22/0 PASS（`!=` 漏 X）、
  23/44 FAIL、22/18 FAIL，与文档逐项吻合。

**版本**：`v1.1.7`（annotated `562f9ea`）指向 `77e30e2`，已推送；remote main
`1ca0c89`。D36（PPA 版本校验）仍在 peer 工作区进行，未验收。

### D36 独立复验（2026-10-23 23:10，通过）+ D37（P3）

用 `git archive 2d0fe2a` 的只读副本在全新工作区复验，不采信 peer 产物。

| 验收点 | 命令 | 结果 |
|---|---|---|
| 快照含 tools | `synth` ×2 | 两个快照均含 iverilog/yosys/slang/verible/python |
| 字节确定性 | 连续 2 次 synth | stat sha `42a4bbcb…`、ltp sha `c7725b13…`，与 v1.1.7 前一致 |
| 同版本 compare | 默认 | `RESULT: PASS`，rc0，无 WARN |
| 版本不一致（默认） | `compare --baseline fake` | `RESULT: WARN (tool_version)`，rc0，打印两边版本 |
| 版本不一致（严格） | 同上 + `--fail-on-tool-mismatch` | `RESULT: FAIL (tool_version)`，**rc1** |
| 旧快照无 tools | `--baseline old` | 「不可判定（旧快照缺 tools）」，`RESULT: PASS`，rc0 |
| all 默认 | `all --baseline fake` | `PASS` rc0，内嵌 compare `WARN` + 告警行 |
| all + fail-on-regression | 同上 | `PASS` rc0（WARN 不再误伤） |
| all + fail-on-tool-mismatch | 同上 | `FAIL (tool_version)`，rc1 |
| 真回归仍被拦截 | 基线 cells=50 | `FAIL (cells)`，rc1 |
| 回归 | pwm_gen / sync_fifo / rr_arbiter | 全部 rc0：1666/0 109/8/11、1050/0 97/39/6、534/0 30/2/10，LEC 9/0、51/0、11/0，formal 全 PASS |
| 文档 | `toolchain.md:282-323` | PPA 指标定义、字节确定性、版本记录/比对、不可比场景齐全 |

**补充语义校准**（`t3-semantics/`，已知结构 RTL）：`ff_test`（3×8bit 流水）
24/24/0；`depth_test`（5 级组合链）7/0/6；`mixed_test`（计数器+比较树）27/8/7。
证明 `ff` 精确、depth 不含 FF；且 depth 是全设计最长组合路径（mixed 的 7 级来自
`cnt+1` 加法链、终点为 `cnt[7]` 的 D 端），不只是输出端口逻辑。

### D37（P3）严格模式下仍打印 `[WARN] ... 默认 WARN`，与实际 FAIL 矛盾

**复现**：
```
rtlq.py compare -W <ws> --top pwm_gen --baseline fake.json --fail-on-tool-mismatch
→ RESULT: FAIL (regressions: tool_version)   （但上文打印 [WARN] ... 默认 WARN）
rtlq.py all ... --fail-on-tool-mismatch
→ == rtlq all: FAIL ==                        （但打印 [WARN] ... 默认 WARN）
rtlq.py synth ... --fail-on-tool-mismatch
→ [PASS] synth ... 后打印 [WARN] ...，退出码 1
```
**位置**：`scripts/rtlq.py` 的 `cmd_synth`（约 1160-1166）、`cmd_all`（约
2024-2029）、`cmd_compare`（约 2056-2061）无条件打印 `[WARN]` 文案。
**期望**：按实际模式输出（严格模式 `[FAIL] tool version mismatch`，默认
`[WARN]`），或统一用中性 `[TOOL]`；`synth` 在严格门禁触发时补一行
`RESULT: FAIL (tool_version)`，避免 `[PASS]` 与 rc1 并存的歧义。
**级别**：P3（判定与退出码正确，仅提示文案误导）。
**状态**：2026-10-23 23:12 已发 rtl-expert-54。

**版本**：`v1.1.8`（annotated `51d524e`）指向 `2d0fe2a`，已推送；remote main
`2d0fe2a`。

### D37 独立复验（2026-10-23 23:20，通过，v1.1.9）

`git archive 2782941` 只读副本复验：
- `compare` 篡改版本：默认 `[WARN]` + `RESULT: WARN` rc0；`--fail-on-tool-mismatch`
  `[FAIL]` + `RESULT: FAIL (regressions: tool_version)` rc1。
- 同版本 `RESULT: PASS` rc0；旧快照无 tools 无提示、rc0。
- `all`：默认 `[WARN]` + PASS rc0；严格 `[FAIL]` + `== rtlq all: FAIL ==` rc1。
- `synth`：默认 `[WARN]` rc0；严格 `[FAIL]` + `RESULT: FAIL (tool_version)` rc1，
  不再有 `[PASS]` 与 rc1 并存的歧义。
- 回归：sync_fifo 1050/0、97/39/6、51/0；rr_arbiter 534/0、30/2/10、11/0；全 rc0。

**版本**：`v1.1.9`（annotated `fcbfdeb`）指向 `2782941`，已推送。

### D38（P2）多模块 LEC 未展平导致 `$paramod` 无 SAT model（2026-10-24）

**复现**：在多模块、含 `$paramod` 子模块的验收用例上运行 `rtlq.py all`：
lint/sim/negative/synth 通过，LEC 阶段失败：
`ERROR: No SAT model available for cell ... ($paramod...)`。

**位置**：`scripts/rtlq.py` 的 `do_lec` 生成的 Yosys 脚本：
`read_verilog -sv ...; hierarchy -check -top ...; proc; memory; opt_clean;
equiv_opt -multiclock -assert synth`。

**根因**：`equiv_opt` 在层次化设计上直接构造等价 miter；参数化子模块
（`$paramod`）没有独立的 SAT model，miter 无法求解，LEC 无法给出证明。

**修复**：在 `proc/memory/opt_clean` 之后、`equiv_opt` 之前插入 `flatten`。
单模块设计该步骤为无操作；多模块参数化设计先展平再生成 miter。

**验证结论（2026-10-24）**：修复后同一用例 LEC 通过（`unproven=0`），
`all` 六阶段 PASS、rc0；单模块回归结果无变化。原始交付物、波形与审计证据
保存在内部验收工作区，不随公开文档发布。

**版本**：`v1.1.10`（本提交）。按当前约定未由实现方 push/tag；由 peer 独立
复验后推送并打 tag。

### D38 独立复验与多模块验收（2026-10-24，已脱敏）

- 独立只读快照复现：修复前 LEC 失败（`No SAT model`），修复后通过
  （`unproven=0`），与根因一致。
- 多模块验收连续两轮独立审计均通过；行为项以独立 TB 产生的 VCD 时间戳判定，
  未发现交付缺陷。
- 单模块回归在修复前后无变化。
- 原始交付物、RTL/TB、波形、检查脚本与逐项证据保存在内部验收工作区，
  不在本公开记录中附带。

**版本**：`v1.1.10`（annotated `0708037`）指向 `b86fc07`，已推送。
