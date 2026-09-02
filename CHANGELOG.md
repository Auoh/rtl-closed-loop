# Changelog

rtl-closed-loop 技能的版本变更记录。版本号遵循语义化版本（SemVer）。

## [v1.0.0] - 2026-09-03

### Added

- SKILL.md：技能定义。RTL 小模块闭环开发与验证流程——需求规格化、RTL 编写/审查、自动生成自检测试台、基于 Icarus Verilog 的编译仿真回归、缺陷发现（错误注入演练）、GTKWave 波形调试与优化。
- agents/openai.yaml：默认子代理配置。
- references/coding_style.md：RTL 代码风格规范。
- references/toolchain.md：工具链（iverilog / vvp / GTKWave / Verible）部署、查找与离线恢复规则。
- references/workflow.md：闭环工作流说明。
- scripts/setup.ps1：工具链检测、便携部署与离线包恢复。
- scripts/export.ps1：导出「技能 + 工具链」离线包。
- scripts/run.ps1、scripts/run.sh：编译仿真运行入口。
- scripts/wave.ps1：GTKWave 波形查看入口。
- scripts/gen_tb.py：自动生成自检测试台。
- scripts/format.ps1、scripts/format_check.py：代码格式化与格式检查。
- scripts/rtl-tools.ps1：公共函数库（工作区定位、工具链查找、离线自动恢复）。