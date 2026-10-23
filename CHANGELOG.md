# Changelog

rtl-closed-loop 技能的版本变更记录。版本号遵循语义化版本（SemVer）。

## [v1.1.1] - 2026-10-23

### Fixed

- `setup.ps1 -Install/-Bundle`：源与目标相同（缓存根已在 PATH 上）时会先删除
  目标再对同一路径 robocopy，导致工具链被清空。现在删除前先做
  `GetFullPath` 大小写不敏感比较，相同则跳过并打印提示。
- `setup.ps1` 部署 iverilog 前校验源目录包含 `bin\iverilog.exe`，源无效时
  直接退出，不再删除目标。

## [v1.1.0] - 2026-10-23

### Added

- `scripts/rtlq.py`（v1.1.0）：轻量统一质量 CLI，仅用 Python 标准库，提供
  `doctor / manifest / lint / sim / synth / lec / formal / all / compare / report`。
  - `lint`：R1-R10 风格检查 + slang（`--std 1800-2017`）+ Yosys 结构检查（latch/组合环）。
  - `sim`：多文件 RTL、`-g2012`、缺陷注入、波形（VCD/FST）、超时与 PASS/FAIL 解析。
  - `synth`：Yosys 综合 + PPA-lite（generic cells / FF / 逻辑深度）+ 预算判定。
  - `lec`：Yosys `equiv_opt` RTL vs 综合网表，多时钟、blacklist、proven/unproven 统计。
  - `formal`：SymbiYosys `mode prove`，自动定位 `formal/<top>.sby`，显式 `--yosys/--abc`。
  - `all`：lint→sim→负向→synth→LEC→formal，生成 `report/quality.json`、
    `report/summary.md` 与按模块留档的 `report/summary_<top>.md`。
  - 迭代历史：每次 `synth`/`all` 追加 `report/history/<top>/<timestamp>.json`，
    写前解析基线，旧快照不覆盖；`--baseline` 可指定文件/时间戳/目录。
  - `compare`：对比基线与当前快照的六阶段状态及 cells/FF/depth 增量，
    有阶段回归、PPA 回退或预算超限时退出码 1；`--json` 输出结构化结果。
  - `all`/`synth` 控制台打印基线对比行；`summary_<top>.md` 自动生成
    「Baseline vs Current」小节（无基线时跳过）。
- `doctor` 增加 Python 解释器版本行（共 11 行：10 项工具 + Python）。
- `scripts/rtlq.ps1` / `scripts/rtlq`：Windows 与 Linux/macOS 入口包装器。
- quality-lite 轻量工具链集成（Yosys 0.66 + slang 12.0.0 + SymbiYosys 0.70，约 91MB）：
  `rtl-tools.ps1` 新增 `Get-RtlQualityRoot` / `Find-RtlQualityTool`；
  `setup.ps1` 新增 `-QualitySource`，检测/`-Install`/`-Bundle`/`-Offline` 均覆盖 quality-lite；
  `export.ps1` 新增 `-QualityLiteSource`，打包 `toolchain/quality-lite` 与 `toolchain/manifest.json`。
- `rtlq.py manifest`：记录工具版本与关键文件 SHA256 到 `tools/manifest.json`。
- `format_check.py` 新增 R9：只允许 `posedge` 触发，`negedge` 仅允许复位信号；
  非上沿事件/电平敏感时钟报错。`RULE_ADVICE` 同步补充建议。
- `gen_tb.py` 生成模板新增 `DUMP_WAVE` VCD 块，配合 `--wave` 使用。
- `wave.ps1` 支持 `-NoGui` / `-Fst`，仿真后强制校验非空波形文件。
- `run.ps1` 支持多文件、`-g2012`、`-Bug`、`-Wave`、`-Files`、`-Timeout`，默认不修改 RTL。

### Changed

- `run.ps1` 默认不再自动执行格式化/修改 RTL；需要时显式 `-FixFormat`（旧 `-NoFormat` 保留为 no-op）。
- `run.sh` 改为优先调用 `rtlq.py sim`，无 Python 时回退直接 iverilog（`-g2012`、多文件）。
- `setup.ps1` 检测项从 4 项扩展到 7 项（新增 Yosys/slang/sby，Verible 标为可选）。
- `export.ps1` 的 `-NoToolchain` 现在也会跳过 verible 与 quality-lite，与帮助文本一致。
- `export.ps1` 打包技能时排除 `.git`、`__pycache__`、`*.pyc`，避免离线包携带仓库历史/缓存。

### Fixed

- R3：`!rst_n` 复位检测正则失效（旧写法无法回溯匹配 `rst_n`）。
- R4：`case/casez/casex` 全覆盖。
- R7：单行 `else begin ; end` 空块检测。
- R8：`endcase` 被误判为 `end` 导致多信号 always 漏报；LHS 误把 `if (a <= b)` 当赋值。
- `rtlq all` 负向阶段误扫其他 RTL 的 `INJECT_BUG`（如 reg_adder 继承 sync_fifo）。
- `export.ps1` 压缩阶段偶发被杀毒软件短暂占用 `slang.exe` 导致失败，且 `-Force`
  会先删除旧包；改为写临时 zip、失败重试 5 次、成功后再替换目标文件。
- bash 入口（`run.sh`/`rtlq`）会选中 Windows Store 的 `python3` 桩（无输出、rc=49）；
  现在逐个探测并跳过不可用的解释器。
- `rtlq.ps1` 直接调用 `python`，在 Windows Store 的 python 桩环境下同样会失败；
  改为与 bash 入口一致的候选探测（`python`/`python3`/`py -3.12`/`py -3`）。
- `rtlq` 的 verible 查找未覆盖离线部署的「iverilog 同级 verible」布局；
  `RTL_TOOLCHAIN` 指向 iverilog 目录时会漏检，现已补充该查找路径。
- LEC blacklist 路径带引号导致 Yosys 打不开文件；结果统计解析改为
  `Of those cells X are proven and Y are unproven`。
- 控制台/重定向中文乱码（stdout/stderr 统一 UTF-8）。
- `rtlq all` / `summary.md` 中 LEC、formal、negative 摘要为空或不直观。
- `compare` 把「本次快照未执行某阶段」（如 `synth` 对 `all` 基线）误判为
  阶段回归；现标记为 `n/a`，只有两快照都有的阶段才比较状态。

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