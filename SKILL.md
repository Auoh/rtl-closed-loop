---
name: rtl-closed-loop
description: >-
  RTL 小模块闭环开发与验证：需求规格化、RTL 编写/审查、自动生成自检测试台、
  基于 Icarus Verilog 的编译仿真回归、缺陷发现（错误注入演练）、GTKWave 波形调试与优化。
  当用户提供 Verilog/SystemVerilog 模块（.v/.sv 文件）与需求说明，并要求仿真、自检验证、
  看波形、错误注入或优化时使用。本技能自包含：指令+全部脚本在技能目录内，工具链由 setup.ps1 自动部署。
---

# RTL 闭环开发（rtl-closed-loop）

## 何时使用
用户给出 RTL 模块（.v/.sv）与需求说明，要求：仿真、自检验证、看波形、错误注入演练、优化。
只处理用户指定的模块；用户未要求的综合/后端/跨时钟域分析不要擅自开展。

## 结构与自包含（迁移只需拷贝本技能文件夹）
本技能 = 指令(SKILL.md) + 参考(references/) + 全部脚本(scripts/)。
- `scripts/run.ps1` / `wave.ps1` / `setup.ps1` / `gen_tb.py` / `run.sh`：工作区无关，
  用 `-W <工作区>`（默认当前目录）指向包含 `rtl/ tb/ docs/` 的模块工程。
- 二进制工具链（iverilog/vvp/GTKWave）不内置：`scripts/setup.ps1 -Install`
  首次自动部署到缓存根（默认 `$HOME\.codex\rtl-toolchain`，用户目录含中文时自动用
  纯 ASCII 根如 `C:\rtl-toolchain`），或直接检测系统 PATH。
- 迁移到新机：拷贝技能文件夹 → 运行 `setup.ps1 -Install`（或系统安装 iverilog）→ 即可用。
- 无网环境：导出机 `scripts/export.ps1 -Out <zip>` 打包「技能+工具链」；目标机解压技能后
  `scripts/setup.ps1 -Offline`（自动找工作区根目录的离线包）一键恢复工具链（详见 [toolchain.md](references/toolchain.md) 离线部署节）。
  离线包放在工作区根目录即可被自动发现：`run.ps1`/`wave.ps1` 缺工具时会自动部署。
- Linux/macOS：`scripts/run.sh [模块] [bug|wave] [工作区]`。

常用命令（<技能> = 本技能目录，如 `C:\Users\<你>\.agents\skills\rtl-closed-loop`）：
- 编译+仿真回归：`& '<技能>\scripts\run.ps1' -W <工作区> -Top <module>`（退出码 0=PASS）
- TB 骨架生成：`python '<技能>\scripts\gen_tb.py' -w <工作区> <接口JSON>`
- 波形：`& '<技能>\scripts\wave.ps1' -W <工作区> -Top <module>`
- 编码规范检查：`& '<技能>\scripts\format.ps1' -W <工作区> -Top <module>`
- 检查并生成报告（外部 RTL 必做）：`& '<技能>\scripts\format.ps1' -W <工作区> -Top <module> -Report docs\coding_report_<module>.md`
- 自动格式化：`& '<技能>\scripts\format.ps1' -W <工作区> -Top <module> -Fix`（verible 格式化 + 规范修复）
- `run.ps1` 编译前会自动执行格式调整（可用 `-NoFormat` 关闭）
- 离线包导出：`& '<技能>\scripts\export.ps1' -Out <zip>`（技能+工具链一个包）
- 无网恢复：`& '<技能>\scripts\setup.ps1' -Offline`（自动找工作区根目录离线包；或 `-Offline -Zip <zip>` 显式指定）
- 需求文档模板：工作区 `docs\demo_spec.md`
- 环境细节与已知坑：见 [toolchain.md](references/toolchain.md)

## 闭环工作流（每次完整走一遍）
1. **规格化**：把需求整理为可执行验收标准（接口表、边界行为、PASS/FAIL 判据），写入 `docs\`
2. **RTL**：编写或审查 `rtl\<module>.v`；外部提供的 RTL 先跑 `format.ps1 -Report` 生成规范报告并修复违例，再进入测试环境环节
3. **测试环境**：写接口 JSON → 技能 `gen_tb.py -w <工作区>` 生成骨架 → 在 `reference_model` 填写期望逻辑
   （参考模型必须独立于 DUT，禁止用被测逻辑验证被测逻辑）
4. **回归**：技能 `run.ps1 -W <工作区> -Top <module>` 必须 `RESULT: PASS` 且退出码 0
5. **负向演练**：对关键验收点做错误注入，确认 TB 能 FAIL（防止"测试没抓到任何东西"）
6. **波形确认**：技能 `wave.ps1 -W <工作区>` 打开 GTKWave 核对关键时序（实时加信号方法见 toolchain.md）
7. **优化**：按用户要求优化（时序/面积/风格）；改动后必须重跑 4-6
8. **交付**：需求文档 + RTL + TB + 仿真日志 + 结论（PASS/FAIL、覆盖点、遗留风险）

## 硬性约束
- 退出码即结论：0=PASS，非0=FAIL；TB 报 FAIL 时禁止宣称通过
- 每轮 RTL 改动后必须重跑完整回归
- RTL 编写/审查必须遵守编码规范 [coding_style.md](references/coding_style.md)；外部 RTL 必须先生成规范报告（`format.ps1 -Report`，归档 `docs\coding_report_<module>.md`）并按其建议修复；新增规范要求时同步刷新该文档
- 详细步骤模板见 [workflow.md](references/workflow.md)