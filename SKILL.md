---
name: rtl-closed-loop
description: >-
  RTL 小模块闭环开发与验证：需求规格化、RTL 编写/审查、自动生成自检测试台、
  基于 Icarus Verilog 的编译仿真回归、缺陷发现（错误注入演练）、GTKWave 波形调试与优化；
  并提供 Yosys/slang/sby 质量门禁（lint、结构检查、PPA-lite、LEC 等价性、形式验证）。
  当用户提供 Verilog/SystemVerilog 模块（.v/.sv 文件）与需求说明，并要求仿真、自检验证、
  看波形、错误注入、综合/PPA 评估或优化时使用。本技能自包含：指令+全部脚本在技能目录内，
  工具链由 setup.ps1 自动部署。
---

# RTL 闭环开发（rtl-closed-loop）

## 何时使用
用户给出 RTL 模块（.v/.sv）与需求说明，要求：仿真、自检验证、看波形、错误注入演练、
综合/PPA 评估、形式验证或优化。只处理用户指定的模块；默认质量门禁覆盖 lint、仿真、
负向演练、Yosys 综合 PPA-lite、LEC 与 sby 形式验证；不做布局布线/签核 STA/后端实现。

## 结构与自包含（迁移只需拷贝本技能文件夹）
本技能 = 指令(SKILL.md) + 参考(references/) + 全部脚本(scripts/)。
- `scripts/rtlq.py`：统一质量 CLI（doctor/manifest/lint/sim/synth/lec/formal/all/compare/report），
  仅用 Python 标准库；`scripts/rtlq.ps1` / `scripts/rtlq` 为平台入口。
- `scripts/run.ps1` / `wave.ps1` / `setup.ps1` / `gen_tb.py` / `run.sh`：工作区无关，
  用 `-W <工作区>`（默认当前目录）指向包含 `rtl/ tb/ docs/` 的模块工程。
- 二进制工具链不内置：基础仿真用 iverilog/vvp/GTKWave；质量门禁用
  `tools/quality-lite`（Yosys 0.66 + slang 12 + SymbiYosys，约 91MB）。
  `scripts/setup.ps1 -Install` 部署到缓存根（默认 `$HOME\.codex\rtl-toolchain`，
  用户目录含中文时自动用纯 ASCII 根如 `C:\rtl-toolchain`），或直接检测系统 PATH。
- `references/runbook.md`：**逐步执行手册**（面向执行能力较弱的模型）。每一步给出
  命令、期望输出、失败处理与完成判据；不确定怎么做时以它为准。
- 迁移到新机：拷贝技能文件夹 → 运行 `setup.ps1 -Install`（或系统安装 iverilog）→ 即可用。
- 无网环境：导出机 `scripts/export.ps1 -Out <zip>` 打包「技能+iverilog+verible+quality-lite」；
  目标机解压技能后 `scripts/setup.ps1 -Offline`（自动找工作区根目录离线包）一键恢复
  （详见 [toolchain.md](references/toolchain.md) 离线部署节）。
- Linux/macOS：`scripts/run.sh [模块] [bug|wave] [工作区]`；质量命令用 `scripts/rtlq`。

常用命令（<技能> = 本技能目录，如 `C:\Users\<你>\.agents\skills\rtl-closed-loop`）：
- 环境自检：`& '<技能>\scripts\rtlq.ps1' doctor`
- 全流程质量门禁：`& '<技能>\scripts\rtlq.ps1' all -W <工作区> -Top <module>`（lint→sim→负向→synth→LEC→formal）
- 基线对比：`& '<技能>\scripts\rtlq.ps1' compare -W <工作区> -Top <module>`（默认对比最近两次快照；有回归/超预算退出码 1；Yosys 版本不一致默认 WARN，加 `--fail-on-tool-mismatch` 判 FAIL）
- 单项：`rtlq.ps1 lint|sim|synth|lec|formal -W <工作区> -Top <module>`
- 每次 `synth`/`all` 自动追加快照 `report\history\<module>\<timestamp>.json`，不覆盖旧快照；
  `all` 的 `summary_<module>.md` 自动包含「Baseline vs Current」小节
- 编译+仿真回归：`& '<技能>\scripts\run.ps1' -W <工作区> -Top <module>`（退出码 0=PASS）
- TB 骨架生成：`python '<技能>\scripts\gen_tb.py' -w <工作区> <接口JSON>`
- 波形：`& '<技能>\scripts\wave.ps1' -W <工作区> -Top <module>`（无 GUI 环境加 `-NoGui`，仅生成波形文件）
- 编码规范检查：`& '<技能>\scripts\format.ps1' -W <工作区> -Top <module>`
- 检查并生成报告（外部 RTL 必做）：`& '<技能>\scripts\format.ps1' -W <工作区> -Top <module> -Report docs\coding_report_<module>.md`
- 自动格式化：`& '<技能>\scripts\format.ps1' -W <工作区> -Top <module> -Fix`（verible 格式化 + 规范修复）
- `run.ps1` 默认**不修改** RTL；需要自动格式化时显式加 `-FixFormat`
- 离线包导出：`& '<技能>\scripts\export.ps1' -Out <zip>`（技能+全部工具链一个包）
- 无网恢复：`& '<技能>\scripts\setup.ps1' -Offline`（自动找工作区根目录离线包；或 `-Offline -Zip <zip>` 显式指定）
- 需求文档模板：工作区 `docs\demo_spec.md`
- 环境细节与已知坑：见 [toolchain.md](references/toolchain.md)

## 执行协议（开始前必读，按顺序照做）

不确定某一步怎么做、做到什么程度算完成时，打开 [runbook.md](references/runbook.md)，
按编号执行。以下规则优先级高于“把流程走完”：

1. **先读懂再动手**：先读需求与 [runbook.md](references/runbook.md)，再按
   规格 → RTL → 测试点 → TB → 仿真 → 负向 → 波形 → 门禁 → 交付 的顺序执行；
   测试点必须在写 TB **之前**完成，不得从需求直接跳到写 TB，也不得先写 TB
   再补测试点。
2. **每步都要有证据**：命令 + 退出码 + 关键输出，日志落在 `report\logs\`。
   没运行过的命令不得写“通过”，没看到的数字不得写进报告。
3. **状态机式推进**：只有拿到该步的期望输出（如 `RESULT: PASS` 且 `rc=0`）
   才进入下一步；`FAIL`/`ERROR` 必须修复后重跑，不能跳过；`SKIP` 不是 `PASS`，
   必须在交付说明中写明原因与补偿措施。
4. **判据不可动**：不得删除/放宽测试点、期望值或断言来消除失败，也不得为过
   门禁而调高 PPA 预算或把真实不等价信号加入 LEC blacklist。判据只能因需求
   变更而改，并同步更新 spec/testplan。
5. **行为结论只看波形**：功能、边界、复位、接口时序必须用独立 TB 产生的 VCD
   时间戳判定（流程见 runbook §8）；代码走读只能用来设计检查，不能当结论。
6. **一轮改动 = 一轮全跑**：每轮 RTL/TB 改动后重跑 sim + negative + `all`，
   并用同一份日志回填 testplan 结果列。

## 闭环工作流（每次完整走一遍）
1. **规格化**：把需求整理为可执行验收标准（接口表、边界行为、PASS/FAIL 判据），写入 `docs\`
2. **RTL**：编写或审查 `rtl\<module>.v`；外部提供的 RTL 先跑 `format.ps1 -Report` 生成规范报告并修复违例，再进入测试环境环节
3. **测试点分解**：按 `references\templates\testplan.md` 写 `docs\testplan_<module>.md`，
   完成“需求 → 测试点 → 用例/断言”追溯；每条需求 ≥1 个测试点、每个测试点 ≥1 个载体，
   边界与非法配置逐条显式，复位与接口时序单独成点。评审通过（无孤儿需求、无无主测试点）
   后才允许写 TB
4. **测试环境**：写接口 JSON → 技能 `gen_tb.py -w <工作区>` 生成骨架 → 在 `reference_model` 填写期望逻辑
   （参考模型必须独立于 DUT，禁止用被测逻辑验证被测逻辑）
5. **回归**：技能 `rtlq.py sim --workdir <工作区> --top <module>`（或 `run.ps1 -Top`）必须 `RESULT: PASS` 且退出码 0
6. **负向演练**：`rtlq.py sim --bug` 对关键验收点做错误注入，期望 FAIL 且 `rtlq.py all` 的 negative 阶段为 PASS。
   `all` 只在顶层 RTL（文件名 stem 等于 `--top`）文本含 `INJECT_BUG` 时自动运行
   negative；RTL 没写该分支时该阶段记 SKIP 并注明原因（不是失败），此时需手工
   完成 `sim --bug` 演练并把日志归档，或在 RTL 中补注入分支。**SKIP 不等于通过**，
   交付结论中不得写“负向演练通过”
7. **波形确认**：`rtlq.py sim --wave`（或 `wave.ps1 -NoGui`）生成 `sim\wave.vcd`，
   按 [runbook.md](references/runbook.md) §8 解析时间戳并记录检查结果；GTKWave
   只用于辅助观察，不能只用“看起来对”作为结论。实时加信号方法见 toolchain.md
8. **质量门禁**：`rtlq.py all --workdir <工作区> --top <module>`，逐项确认
   - lint：style 0 违例、slang 无 error/warning、Yosys 无 latch/组合环
   - synth：generic cell / FF / 逻辑深度不超过 `config\ppa_budget.json` 预算
   - lec：Yosys 等价性证明 unproven=0。v1.1.10 起 `lec` 在 `equiv_opt` 前自动
     `flatten`；多模块/`$paramod` 设计手工复现 LEC 时也必须加 `flatten`，否则报
     `No SAT model available for cell ...`
   - formal：`formal\<module>.sby` 的 sby prove 通过（无 sby 时该阶段 SKIP，需在交付物中说明，
     且不得声称“形式验证通过”）；
     quality-lite 不含 `yosys-smtbmc`，`.sby` 必须显式写 `[engines]` 且用 `abc pdr`
     （缺失或写 smtbmc 时 formal 直接 ERROR 并提示，见 toolchain.md）。
     最小可运行模板见 `references\examples\formal\`：`initial boot = 0` + 复位窗口内
     多拍 `assume(rst_n == 0)` 清除 anyinit，断言用 `boot >= RESET_CYCLES` 门控；
     `[files]` 路径相对 `-W` 工作区，不是相对 `.sby` 目录。
   - PPA 指标是 Yosys generic 映射后的相对量，用于回归对比，不等同于签核 STA
9. **优化（记录→改动→复测→对比）**：
   a. 改动前先跑 `rtlq.py all` 记录基线快照（或明确用 `--baseline <文件>` 指定更早基线）；
   b. 修改 RTL，重跑 5-8（`all` 会生成新快照）；
   c. 跑 `rtlq.py compare --workdir <工作区> --top <module>`，确认六阶段状态无回归、
      cells/FF/depth 未超预算；退出码非 0 必须回退或修复；
   d. 在 `docs\optimization_iteration.md` 记录优化理由、前后数据与命令退出码；
   注意 `synth`/`all` 的基线在写当前快照**之前**解析，旧基线不会被覆盖。
10. **交付**：需求文档 + 测试计划（`docs\testplan_<module>.md`，含追溯矩阵与结果）
    + RTL + TB + 仿真/质量日志 + `report\summary.md` + 基线对比结论
    （PASS/FAIL、测试点覆盖结论、PPA、遗留风险）

## 硬性约束
- 退出码即结论：0=PASS，非0=FAIL；TB 报 FAIL 或 `rtlq all` 非 PASS 时禁止宣称通过
- TB 每一处输出比较必须用 `!==`/`===`；`!=` 遇 X/Z 得 X，`if (X)` 按假处理会静默漏报。
  检查在负沿做，寄存器输出用 `*_cap`、组合输出用当前输入（见 toolchain.md「比对与时序：保证与不保证」）
- 每轮 RTL 改动后必须重跑完整回归与质量门禁（至少 sim + lint + synth + lec）
- RTL 编写/审查必须遵守编码规范 [coding_style.md](references/coding_style.md)；外部 RTL 必须先生成规范报告（`format.ps1 -Report`，归档 `docs\coding_report_<module>.md`）并按其建议修复；新增规范要求时同步刷新该文档
- 质量策略（超时/开关/blacklist）放 `config\quality_policy.json`，PPA 预算放 `config\ppa_budget.json`；预算调整必须在交付说明中记录理由
- LEC 的 blacklist 只允许用于工具无法匹配的等价状态编码（如 `state_next`），不得掩盖真实不等价；优先按 [coding_style.md](references/coding_style.md) 第 13 节的 LEC 友好 FSM 写法（`(* fsm_encoding = "none" *)` + F2 每个分支显式赋值 `state_next`）保持 blacklist 为空
- 禁止伪造结果：不得编造命令输出、日志、时间戳或验收数字；`rc` 非 0、`RESULT: FAIL`、`ERROR` 均不得宣称通过；`SKIP` 不得计为 `PASS`
- 完整逐步命令、失败处理表与最终自检清单见 [runbook.md](references/runbook.md)；
  流程细节见 [workflow.md](references/workflow.md)