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
| demo 1 `uart_tx` | FAIL（A7、A12；其余 10 项通过） |
| demo 2 `rr_arbiter` | 未开始 |
| demo 3 `pwm_gen` | 未开始 |

demo 1 关键数据：sim `checks=4478 errors=0`；`--bug` rc=1（errors=1344）；
PPA 优化 79/18/9 → 54/15/6；LEC unproven=0；formal `abc pdr` 全部 proved。
判 FAIL 的两点见 D7（LEC 黑名单）与 D4/D5（阻塞级缺口）。

## 已修复

| ID | 级别 | 位置 | 问题 | 修复 |
|---|---|---|---|---|
| D1 | P1 | `scripts/setup.ps1:243` | `-Install` 在源==目标时先删目标再同路径 robocopy，把缓存工具链清成 0MB | `51c1ac3`：删除前 `GetFullPath` 比较，相同则跳过；并校验源含 `bin\iverilog.exe` |
| D2 | P3 | `docs/cleanroom_verify.md` | 「未 push」与「已按用户授权推送」矛盾 | 已改为「已按用户授权 push」 |
| D3 | P3 | `docs/cleanroom_verify.md` | v1.1.1 段写「尚未 push」与事实不符 | 已改为「已 push origin/main 与远端 tag v1.1.1（6b9b08e）」 |

D1 复验证据：缓存根已存在时重复 `-Install` → rc 0、打印「源与目标相同，跳过」、
1231 文件/87MB 前后不变；无效源 → rc 1、缓存不变；`doctor` 11 项 OK；
离线包内 `setup.ps1` 含同样守卫，`VERSION = "1.1.1"`。

## 待修复

| ID | 级别 | 位置 | 问题 |
|---|---|---|---|
| D4 | P1 | `scripts/rtlq.py:290-303` | `_find_iverilog` 只找 `<root>/bin`，不识别 `setup.ps1 -Install` 产出的 `<root>/iverilog/bin`；回退到含空格 PATH 后 iverilog 启动子进程失败（rc=255） |
| D5 | P1 | `references/toolchain.md:34` | quality-lite 缺 `yosys-smtbmc`，sby 默认 smtbmc 引擎必然 `DONE (ERROR, rc=16)`；文档未说明需自写 `[engines] abc pdr` |
| D6 | P3 | 多处 | `toolchain.md:56` 示例指向技能外路径；`gen_tb.py:80` 头注释写 `tools/`；`SKILL.md:59` 用 `-Top` 调 `rtlq.py`（只认 `--top`）；`workflow.md:70` 日志路径与实际不符；`SKILL.md:61` 未提 `-NoGui`；`gen_tb.py` 重生成丢 task 外状态；config JSON 无字段说明 |
| D7 | P2 | demo 侧 | demo 1 在 `quality_policy.json` 设 `lec.blacklist.default=["state_next"]`；清空后 `proven=19 unproven=0`，属多余掩盖项，验收按不通过处理，需重跑 |

D4 复现：

```
rtlq.py sim -W <workspace> --top uart_tx     # 不设 RTL_TOOLCHAIN
→ compile_rc=255，'D:\01' 不是内部或外部命令
同一命令改用 C:\rtl-toolchain\iverilog\bin\iverilog.exe → rc=0
```

D5 复现：删除 sby 的 `[engines]` 段后 `rtlq.py formal` → rc=1（sby rc=16）。

## 误报排除（复核后不成立，不修）

- sby `[files]` 路径语义：`references/toolchain.md:157` 已说明会复制到 `report/formal/<top>`。
- `_STATUS_RANK` 与 `_status_rank` 语义不一致：`_worst` 先过滤 SKIP，两者行为不冲突。

## 版本与备份

- `v1.1.0`（`7d791e8`）：D1 修复前的备份基线，已推送。
- `v1.1.1`（`51c1ac3`）：D1 修复，已推送；远端 annotated tag `6b9b08e`。
- 流程：确认问题点后先把当前状态打 tag 并 push，再执行修改；修复复验通过后打版本 tag 并 push。
