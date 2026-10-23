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
- 迁移到新机：拷贝技能文件夹 → 运行 `setup.ps1 -Install`（或系统安装 iverilog）→ 即可用。
- 无网环境：导出机 `scripts/export.ps1 -Out <zip>` 打包「技能+iverilog+verible+quality-lite」；
  目标机解压技能后 `scripts/setup.ps1 -Offline`（自动找工作区根目录离线包）一键恢复
  （详见 [toolchain.md](references/toolchain.md) 离线部署节）。
- Linux/macOS：`scripts/run.sh [模块] [bug|wave] [工作区]`；质量命令用 `scripts/rtlq`。

常用命令（<技能> = 本技能目录，如 `C:\Users\<你>\.agents\skills\rtl-closed-loop`）：
- 环境自检：`& '<技能>\scripts\rtlq.ps1' doctor`
- 全流程质量门禁：`& '<技能>\scripts\rtlq.ps1' all -W <工作区> -Top <module>`（lint→sim→负向→synth→LEC→formal）
- 基线对比：`& '<技能>\scripts\rtlq.ps1' compare -W <工作区> -Top <module>`（默认对比最近两次快照；有回归/超预算退出码 1）
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

## 闭环工作流（每次完整走一遍）
1. **规格化**：把需求整理为可执行验收标准（接口表、边界行为、PASS/FAIL 判据），写入 `docs\`
2. **RTL**：编写或审查 `rtl\<module>.v`；外部提供的 RTL 先跑 `format.ps1 -Report` 生成规范报告并修复违例，再进入测试环境环节
3. **测试环境**：写接口 JSON → 技能 `gen_tb.py -w <工作区>` 生成骨架 → 在 `reference_model` 填写期望逻辑
   （参考模型必须独立于 DUT，禁止用被测逻辑验证被测逻辑）
4. **回归**：技能 `rtlq.py sim -W <工作区> --top <module>`（或 `run.ps1 -Top`）必须 `RESULT: PASS` 且退出码 0
5. **负向演练**：`rtlq.py sim --bug` 对关键验收点做错误注入，期望 FAIL 且 `rtlq.py all` 的 negative 阶段为 PASS
6. **波形确认**：技能 `wave.ps1 -W <工作区>` 打开 GTKWave 核对关键时序（实时加信号方法见 toolchain.md）
7. **质量门禁**：`rtlq.py all -W <工作区> --top <module>`，逐项确认
   - lint：style 0 违例、slang 无 error/warning、Yosys 无 latch/组合环
   - synth：generic cell / FF / 逻辑深度不超过 `config\ppa_budget.json` 预算
   - lec：Yosys 等价性证明 unproven=0
   - formal：`formal\<module>.sby` 的 sby prove 通过（无 sby 时该阶段 SKIP，需在交付物中说明）；
     quality-lite 不含 `yosys-smtbmc`，`.sby` 必须显式写 `[engines]` 且用 `abc pdr`
     （缺失或写 smtbmc 时 formal 直接 ERROR 并提示，见 toolchain.md）。
     最小可运行模板见 `references\examples\formal\`：`initial boot = 0` + 复位窗口内
     多拍 `assume(rst_n == 0)` 清除 anyinit，断言用 `boot >= RESET_CYCLES` 门控；
     `[files]` 路径相对 `-W` 工作区，不是相对 `.sby` 目录。
   - PPA 指标是 Yosys generic 映射后的相对量，用于回归对比，不等同于签核 STA
8. **优化（记录→改动→复测→对比）**：
   a. 改动前先跑 `rtlq.py all` 记录基线快照（或明确用 `--baseline <文件>` 指定更早基线）；
   b. 修改 RTL，重跑 4-7（`all` 会生成新快照）；
   c. 跑 `rtlq.py compare -W <工作区> --top <module>`，确认六阶段状态无回归、
      cells/FF/depth 未超预算；退出码非 0 必须回退或修复；
   d. 在 `docs\optimization_iteration.md` 记录优化理由、前后数据与命令退出码；
   注意 `synth`/`all` 的基线在写当前快照**之前**解析，旧基线不会被覆盖。
9. **交付**：需求文档 + RTL + TB + 仿真/质量日志 + `report\summary.md` + 基线对比结论（PASS/FAIL、覆盖点、PPA、遗留风险）

## 硬性约束
- 退出码即结论：0=PASS，非0=FAIL；TB 报 FAIL 或 `rtlq all` 非 PASS 时禁止宣称通过
- 每轮 RTL 改动后必须重跑完整回归与质量门禁（至少 sim + lint + synth + lec）
- RTL 编写/审查必须遵守编码规范 [coding_style.md](references/coding_style.md)；外部 RTL 必须先生成规范报告（`format.ps1 -Report`，归档 `docs\coding_report_<module>.md`）并按其建议修复；新增规范要求时同步刷新该文档
- 质量策略（超时/开关/blacklist）放 `config\quality_policy.json`，PPA 预算放 `config\ppa_budget.json`；预算调整必须在交付说明中记录理由
- LEC 的 blacklist 只允许用于工具无法匹配的等价状态编码（如 `state_next`），不得掩盖真实不等价；优先按 [coding_style.md](references/coding_style.md) 第 13 节的 LEC 友好 FSM 写法（`(* fsm_encoding = "none" *)` + F2 每个分支显式赋值 `state_next`）保持 blacklist 为空
- 详细步骤模板见 [workflow.md](references/workflow.md)