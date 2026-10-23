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
| demo 1 `uart_tx`（v1.1.3 重跑） | 待启动 |
| demo 2 `rr_arbiter` | 未开始 |
| demo 3 `pwm_gen` | 未开始 |

demo 1 关键数据（v1.1.2 重跑）：sim `checks=4000 errors=0`；`--bug` rc=1（errors=1440）；
PPA 优化 73/19/6 → 70/18/6；LEC `blacklist=[]`、proven=21；compare rc 0。
A12 未过的原因见 D8/D14（formal harness 与 LEC-FSM 文档缺口，已由 v1.1.3 补齐）。

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

## 待修复

无。当前所有已确认缺陷均已修复并由评审独立复验。

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
- 流程：确认问题点后先把当前状态打 tag 并 push，再执行修改；修复复验通过后打版本 tag 并 push。
