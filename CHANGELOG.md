# Changelog

rtl-closed-loop 技能的版本变更记录。版本号遵循语义化版本（SemVer）。

## [v1.1.8] - 2026-10-23

### Added

- **D36（P1，PPA 可比性）** PPA 跨版本对比补齐版本记录与告警：
  - `_snapshot_payload` 对所有命令统一写顶层 `tools`（`iverilog` / `yosys` /
    `slang` / `verible` / `python`，取各工具版本输出首行）；旧快照没有该字段
    视为「不可判定」，不报错。
  - `_compare_snapshots` 比较两边 `tools.yosys` 的规范化首行并输出两边版本：
    同时存在且不同 → `tool_mismatch`，默认 `RESULT: WARN`、退出码 0（不破坏
    已有流水线）；新增 `--fail-on-tool-mismatch`（`synth` / `all` / `compare`
    均支持）后置 `FAIL`、退出码 1。缺字段或单边缺失 → `not_comparable`，
    不告警。
  - `all --fail-on-regression` 的判定从「对比状态不是 PASS」收紧为
    「对比状态是 FAIL」，因此工具版本不一致的默认 WARN 不会误伤门禁；
    `all --fail-on-tool-mismatch` 可单独让版本不一致卡住整体结论。
  - `_comparison_md` 的 Baseline vs Current 增加工具版本表与不可比说明；
    `compare`/`synth`/`all` 控制台均打印 baseline/current 的 Yosys 版本。
  - 预算门禁语义不变：始终按当前 `config/ppa_budget.json` 校验当前快照。

### Docs

- `references/toolchain.md` 新增「PPA 语义与可比性」：明确 cells =
  `stat -json` 的 `design.num_cells`、ff = DFF 计数、depth = `ltp -noff`
  的组合级数；给出连续三次 `synth` 的 stat/ltp SHA-256 字节一致证据；
  说明跨 Yosys 版本/跨综合脚本/跨映射流程不可比，且 PPA-lite 不是签核 STA。
- `README.md`、`references/workflow.md`、`SKILL.md` 同步 compare 的
  PASS/WARN/FAIL 退出码与 `--fail-on-tool-mismatch` 用法。

### Acceptance

- ① `t3-ppa/pwm_gen` 连续三次 `synth`：`pwm_gen_stat.json` 与
  `pwm_gen_ltp.txt` 的 SHA-256 三次一致（`42a4bbcb…` / `c7725b13…`）。
- ② 篡改快照 `tools.yosys`：默认 `compare` → `WARN`，rc=0；加
  `--fail-on-tool-mismatch` → `FAIL`，rc=1；`all --fail-on-regression`
  仍 rc=0（WARN 不误伤），`all --fail-on-tool-mismatch` rc=1。
- ③ 同版本 `compare` → `RESULT: PASS`，无告警，rc=0；旧快照缺 `tools`
  → 「不可判定」，rc=0。
- ④ 新 `synth` 快照含 `tools.iverilog/yosys/slang/verible/python`。
- ⑤ 三模块 `all` 回归均 rc=0：`pwm_gen`（sim 1666/0、synth 109/8/11）、
  `sync_fifo`（1050/0、97/39/6）、`rr_arbiter`（534/0、30/2/10）。

## [v1.1.7] - 2026-10-23

### Added

- **D34（P2，方法论缺口 T1）** 闭环新增「需求 → 测试点 → 用例」的分解与完备性环节：
  - `references/templates/testplan.md`：`docs\testplan_<module>.md` 模板。主表列为
    需求 ID / 需求摘要 / 测试点 ID / 类别 / 完备性判据 / 用例载体 / 结果；类别固定为
    功能、边界、异常与非法配置、复位、接口时序、性能约束；载体必须落到
    `DIRECTED` 段、随机段、`INJECT_BUG` 注入点或 formal 属性名。
  - `references/workflow.md` 新增 §2.5「测试点分解与完备性评审」，固定
    规格条目 → 测试点 → 完备性检查 → 用例设计 → 执行的顺序，并规定最低完备性：
    每条需求 ≥1 测试点、每个测试点 ≥1 用例/断言、边界与非法配置逐条显式、
    复位与接口时序单独成点；testplan 评审通过后才允许写 TB。
  - `SKILL.md`、`README.md` 工作流插入该步骤；交付清单增加
    `docs\testplan_<module>.md`，覆盖结论改为引用追溯矩阵。
- **D35（P2，T2）** `toolchain.md` 新增「比对与时序：保证与不保证」：给出
  V1–V6 实测矩阵（负沿/上升沿比较、`*_cap` 误用、`!=` 与 `!==`、真缺陷），
  明确输出比较必须用 `!==`/`===`（`!=` 遇 X/Z 静默漏报）、检查必须在负沿、
  寄存器输出用 `*_cap`、组合输出用当前输入；并写明 `rtlq` 只认 `RESULT`
  字面量与退出码，negative 注入是唯一自动发现 TB 失效的手段。`workflow.md`
  §3 增加对应的硬性检查项。
- 本次不引入工具级静态强检查（静态匹配 TB 易误报），后续如需只做软告警。

## [v1.1.6] - 2026-10-23

### Fixed

- **D25（P2）** `formal` 超时只杀 sby 子进程，孙进程 `yosys-abc.exe` 继续持有
  `report/formal/<top>`；下一次 `formal`/`all` 在 `shutil.rmtree` 抛出未捕获的
  `PermissionError [WinError 32]`，工作区卡死。现在：
  - `_run` 用 `Popen` + 进程树终止（Windows `taskkill /T /F`，POSIX
    `start_new_session` + `killpg`），日志写明终止方式与超时秒数；
  - 清理 formal 工作目录增加 5×0.3s 重试；仍失败时返回 ERROR + 可操作
    `[HINT]`（列出残留 `yosys-abc.exe` PID、`taskkill` 命令），不再抛
    Traceback；
  - `formal` 超时结果本身也带清理提示；
  - `toolchain.md` 增加「formal 超时与残留进程」「`depth` 与 prove」
    「sby 单 task」说明。

### Added

- `rtlq.py all`/`report` 生成的 `summary.md` 会列出 `report/mutation/<top>/`
  下的变异/反例证据文件；约定与写法见
  `references/examples/formal/README.md`「变异证据归档」。
- `references/workflow.md` 新增 8.1 节「优化前后 RTL 等价性」：给出可直接
  复制运行的 `equiv.ys`（`equiv_make` + `async2sync` + `equiv_simple` +
  `equiv_induct` + `equiv_status -assert`），并用 `cnt+1`→`cnt+2` 实测
  不等价时返回非 0。

### Changed

- `references/examples/formal/README.md` 补充：数值/计数型不变式的证明策略
  （逐拍参考等式、代表性常量配置、pdr 对符号化 8 位累加的局限）、保持配置
  输入恒定的 `*_hold` + `assume` 写法、`depth` 只约束 bmc、变异证据归档。
- `scripts/gen_tb.py`：端口声明统一 4 空格缩进；注释明确 `reference_model`
  每个检查周期调用一次（含定向段），跳过 negedge 会与 DUT 跨拍状态失步。
- `references/workflow.md`、`SKILL.md`、`README.md` 说明 `all` 的 negative
  阶段仅在顶层 RTL 文本含 `INJECT_BUG` 时运行，否则 SKIP 并注明原因。

## [v1.1.5] - 2026-10-23

### Fixed

- `references/coding_style.md` 第 1/7/13 节的 F2“保持分支”写法自相矛盾：正文
  要求写 `state_next = state;`，同节示例却写状态常量。反馈赋值在“块首默认 +
  case 只写跳转”的结构下仍会被 `opt_dff` 识别为保持并综合成带时钟使能的
  `$adffe`，导致 `state_next` unproven（实测 LEC proven=9 / unproven=2）。
  现统一为：每个分支（含保持和 `default`）显式写**该状态的常量**，不要写
  `state_next = state;`，也不要用块首兜底；`rtlq.py` 的 LEC `[HINT]` 同步
  指出这两种写法。`README.md` 同步更新。
- `gen_tb.py` 生成失败分支的 `$fatal` 误用 `%%0d`（该行不做 Python 格式化），
  Icarus 原样打印 `%0d`；改为 `%0d`，失败时输出真实错误数
  （如 `TEST FAILED: 19 error(s) found`）。
- `gen_tb.py` 的时序注释/文档把 `*_cap` 说成参考模型通用取值：负沿检查时
  `*_cap` 对组合输出已落后一拍。注释与 `coding_style.md` 第 11 节、
  `toolchain.md`「激励与时序约定」现区分：寄存器输出用 `*_cap`，组合输出用
  当前输入。
- `sim --wave` 与普通 `sim` 复用同一 `sim/<top>.vvp` 和
  `report/logs/sim_<top>.log`，后跑覆盖前跑。波形运行现使用 `_wave` 后缀
  （`sim/<top>[_bug]_wave.vvp`、`report/logs/sim_<top>[_bug]_wave.log`），
  普通回归产物保留；`toolchain.md` 补充产物命名说明。

## [v1.1.4] - 2026-10-23

### Fixed

- LEC 默认 blacklist 改为空：`DEFAULT_POLICY["lec"]["blacklist"]["default"]`
  原为 `["state_next"]`，未创建 `config/quality_policy.json` 时会静默排除
  `state_next`，把真实 unproven 掩盖成 PASS。现在默认不排除任何信号；项目仍可
  在配置中按模块显式 opt-in。当 unproven 仅剩 `state_next` 且 blacklist 为空时，
  `lec` / `all` 打印 `[HINT]` 指向 `coding_style.md` §13，但绝不自动排除；
  JSON 增加 `unproven_signals` 便于脚本判断。
- `gen_tb.py` 模块 docstring 的时序说明改为「上升沿 NBA 驱动、负沿检查」，
  与生成代码和生成文件头注释一致。
- `format.ps1` 不再裸调用 `python`：复用 `rtl-tools.ps1` 新增的
  `Find-RtlPython`（依次探测 `python`/`python3`/`py -3.12`/`py -3`，跳过
  Windows Store 桩），与 `rtlq.py` 的解释器探测行为一致；`run.ps1`、
  `wave.ps1` 的同类调用也一并复用该探测。

### Added

- `references/examples/formal/` 新增协议级多周期模板：`pulse_stretch`
  （单拍 `req` 拉伸为固定 `LATENCY` 拍 `busy`，`done` 在最后一拍）+
  `pulse_stretch.sby` + `pulse_stretch_fv.sv`。wrapper 用独立影子计数器
  `shadow` 和 `past_*` 历史寄存器检查起拍、早退、边界释放、`done` 位置；
  README 说明影子寄存器写法，以及 boot 计数器位宽不足导致门控永假、
  PDR 报 “frame 0 (trivial)” 假 PASS 的陷阱。
- `gen_tb.py` 新增 `DIRECTED_BEGIN/END` 定向激励保留区（位于 `do_reset`
  之后、随机循环之前）；重新生成时与 `reference_model`、`REF_DECLS` 一并保留。
- `workflow.md` / `toolchain.md` 补充 `REF_DECLS` 状态必须 `initial` 赋初值
  （3 行示例），并说明定向激励的上沿 NBA 驱动需再等一拍才能检查上一拍数据。

## [v1.1.3] - 2026-10-23

### Fixed

- `formal` 结果中的 `engines` 现在保留 `[engines]` 整行（如 `["abc pdr"]`），
  不再只保留首个 token（`["abc"]`），报告可看出实际引擎/选项；smtbmc 可用性
  检查改为按首 token 判断，兼容 `[engines prove]` 等带模式头的写法。
- `all` 新增 `--fail-on-regression`：内嵌 Baseline vs Current 有阶段回归、PPA
  回退或预算超限时整体判 FAIL。默认仍只写报告、不改变退出码，避免记录实验
  基线时把有意改动误判为失败。

### Added

- `references/examples/formal/`：最小可运行 sby 模板（`demo_ctr.sby` +
  `demo_ctr_fv.sv` + 示例 DUT），演示 anyinit（`formalff -ff2anyinit`）、
  多拍复位 `assume`、断言 `boot >= RESET_CYCLES` 门控、异步复位后的
  `clk2fflogic`，以及 `[files]` 相对 `-W` 工作区的路径规则。
- 形式验证调试文档：quality-lite 无 `yosys-witness` 时不会生成可读 witness/VCD，
  给出 logfile、`mode bmc` + `abc bmc3`、定向仿真和完整 Yosys 的替代定位方法。

### Changed

- `references/coding_style.md` 第 11 节 TB 激励统一为 **NBA 零延时**：上升沿
  NBA 驱动激励、`*_cap` 阻塞捕获、负沿参考模型检查，全程无 `#1`；删除“沿后
  `#1` 偏移再阻塞赋值”的旧写法，与 `gen_tb.py`、`toolchain.md` 一致。
- 新增第 13 节「LEC 友好的状态机写法」：状态寄存器加
  `(* fsm_encoding = "none" *)`，F2 的每个 case/if 分支显式赋值 `state_next`
  （保持分支写该状态的常量，不要 `else ;`；v1.1.5 修正：不要写
  `state_next = state;`，反馈赋值仍可能被识别为保持），避免 `opt_dff` 把状态
  寄存器综合成 DFFE 导致 `state_next` unproven；同步更新 §1/§7 示例及
  `SKILL.md`、`workflow.md`、`README.md`。
- README 更新 formal/LEC 小节：anyinit 模板、`[files]` 基准目录、无 witness
  限制、`all --fail-on-regression` 语义。

## [v1.1.2] - 2026-10-23

### Fixed

- `rtlq.py` iverilog/GTKWave 查找补齐 `setup.ps1 -Install` 的命名子目录布局：
  `<root>\iverilog\bin`、`<root>\iverilog\gtkwave\bin`（原先只找
  `<root>\bin`、`<root>\gtkwave\bin`，工作区无 `tools\` 时会漏掉缓存回退到
  PATH 中含空格的安装，导致 ivlpp 解析失败）。
- `doctor` 对「iverilog 位于含空格路径」输出 `[WARN]` 并提示 `setup.ps1 -Install`；
  JSON 增加 `warnings` 数组，状态为 `WARN`（退出码仍为 0）。
- `sim` 编译失败且首行是命令解析错误（Windows 本地化“不是内部或外部命令”/
  “is not recognized…”，含 GBK 输出被 UTF-8 解码的情况）时，自动改用缓存中
  无空格的 iverilog/vvp 重试一次；控制台打印来源，JSON 记录 `tool_retry`。
  无缓存可重试时给出部署提示。
- `formal` 在运行 sby 前检查 `[engines]`：缺失/为空，或使用 `smtbmc` 而
  quality-lite 未提供 `yosys-smtbmc` 时，直接返回 `ERROR` 并提示改为
  `[engines] abc pdr`（此前要等 sby 深层报错，信息不直观）。

### Changed

- `gen_tb.py` 新增 `REF_DECLS_BEGIN/END` 声明保留区：重新生成时除
  `reference_model` 任务体外，也保留跨拍状态/辅助声明；头部注明其他手工代码
  会被模板覆盖。生成头部的脚本路径改为 `scripts/gen_tb.py`。
- 文档修正：`rtlq.py` 调用统一用 `--top`（`-Top` 仅适用于 PowerShell 包装器）；
  补充 `wave.ps1 -NoGui`、仿真日志真实路径（`report\logs\sim_<top>.log`）、
  `quality_policy.json` / `ppa_budget.json` 字段说明、formal 引擎限制；
  `gen_tb` 示例 JSON 移入技能内 `references\examples\`，移除外部绝对路径。

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