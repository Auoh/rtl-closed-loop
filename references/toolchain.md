# 工具链与环境（本机）

## 命令速查（<技能> = rtl-closed-loop 技能目录，<工作区> = 含 rtl/ tb/ 的工程根）
| 命令 | 作用 |
|---|---|
| `& '<技能>\scripts\rtlq.ps1' doctor -W <工作区>` | 质量工具链自检（iverilog/yosys/slang/sby/verible） |
| `& '<技能>\scripts\rtlq.ps1' lint -W <工作区> -Top <module>` | 风格 R1-R10 + slang + Yosys 结构检查（latch/组合环） |
| `& '<技能>\scripts\rtlq.ps1' sim -W <工作区> -Top <module>` | 编译+仿真；`--bug` 负向、`--wave` 出波形 |
| `& '<技能>\scripts\rtlq.ps1' synth -W <工作区> -Top <module>` | Yosys 综合 + PPA-lite（cells/FF/depth）+ 预算判定 |
| `& '<技能>\scripts\rtlq.ps1' lec -W <工作区> -Top <module>` | Yosys 等价性（RTL vs 综合网表） |
| `& '<技能>\scripts\rtlq.ps1' formal -W <工作区> -Top <module>` | sby prove（读 `formal\<module>.sby`） |
| `& '<技能>\scripts\rtlq.ps1' all -W <工作区> -Top <module>` | 全流程门禁 + `report\quality.json`/`summary.md` + 历史快照 |
| `& '<技能>\scripts\rtlq.ps1' compare -W <工作区> -Top <module>` | 对比最近两次快照（或 `--baseline <文件>`）；有回归/超预算退出码 1 |
| `& '<技能>\scripts\run.ps1' -W <工作区> -Top <module>` | 兼容入口：等价于 `rtlq sim`；退出码 0=PASS |
| `... -Bug` / `... -Wave` | 注入 `INJECT_BUG` / 生成 `<工作区>\sim\wave.vcd` |
| `python '<技能>\scripts\gen_tb.py' -w <工作区> <iface.json>` | 生成 TB 骨架（输出 `<工作区>\tb\`） |
| `& '<技能>\scripts\wave.ps1' -W <工作区> -Top <module>` | 后台仿真 + 打开 GTKWave |
| `& '<技能>\scripts\setup.ps1' -Install` | 部署便携工具链（iverilog + quality-lite） |
| `& '<技能>\scripts\export.ps1' -Out <zip>` | 导出离线包（技能+全部工具链），供无网环境部署 |
| `& '<技能>\scripts\setup.ps1' -Offline` | 无网恢复：自动找工作区根目录的离线包（`-Offline -Zip <路径>` 显式指定） |

## Verible 格式化（verible-verilog-format）
- 工具位置：`C:\rtl-toolchain\verible\bin\verible-verilog-format.exe`（与 iverilog 同级，由 export.ps1 纳入离线包 `toolchain\verible`，`setup.ps1 -Offline` 自动恢复）。
- 固定参数：`--indentation_spaces=4 --wrap_end_else_clauses`（4 空格缩进、end/else 分行，符合编码规范）。
- 使用：`format.ps1 -W <工作区> -Top <module> [-Fix]`；`run.ps1` 默认**不修改** RTL，需要自动格式化时显式加 `-FixFormat`。

## quality-lite（Yosys + slang + sby）
- 位置优先级：`RTL_QUALITY_LITE` 环境变量 → `<工作区>\tools\quality-lite` →
  `<技能>\tools\quality-lite` → iverilog 缓存根同级 `quality-lite` → 盘符根
  （`C:\rtl-toolchain\quality-lite`、`D:\...`、`E:\...`、`F:\...`）。
- 组成：
  - `yosys\bin\yosys.exe` + `yosys-abc.exe`：综合、结构检查、PPA-lite、LEC
  - `slang\bin\slang.exe`：SystemVerilog/Verilog lint（`--lint-only --std 1800-2017`）
  - `sby\sbysrc\sby.py`：SymbiYosys 形式验证入口（依赖 Python 3）
- 安装/部署：
  - `setup.ps1 -Install`：iverilog 装到缓存根，quality-lite 装到其同级目录
  - `setup.ps1 -Bundle -W <工作区>`：quality-lite 装到 `<工作区>\tools\quality-lite`
  - `setup.ps1 -Install -QualitySource <目录>`：显式指定 quality-lite 来源
  - `export.ps1` 默认把 quality-lite 打进 `toolchain\quality-lite`；`-NoToolchain` 跳过
- 版本与哈希：`rtlq.py manifest -W <工作区>` 写 `<工作区>\tools\manifest.json`。
  离线包内的 `toolchain\manifest.json` 记录的是导出机路径；到目标机后如需刷新
  `root`/哈希，重跑一次 `rtlq.py manifest` 即可。
- Windows 注意事项：
  - Yosys 需要 `D:/...` 正斜杠路径；rtlq 已统一转换
  - sby 在 Windows 下用 `py -3.12`（避免 3.14 alpha），并显式传 `--yosys`/`--abc`；
    rtlq 已处理，手工调用时需自行指定
  - sby 会复制 `[files]` 到工作目录，路径含中文可以，但建议工作区为 ASCII
- PPA-lite 口径：Yosys `synth` 后的 generic cell 数、DFF 类单元数、`ltp` 最长逻辑级数；
  用于同一工艺无关映射下的回归对比，不是签核 STA，也不含布线/时钟树。
- 迭代快照：`synth`/`all` 每次追加 `report\history\<module>\<UTC时间戳>.json`，
  不覆盖历史；`compare` 默认取最近两次，也可 `--baseline <文件|时间戳|目录>`；
  `all` 的 `summary_<module>.md` 会附带基线对比表。历史目录可随时归档/清理，
  但删除后无法再对比对应版本。

## gen_tb.py 接口 JSON 格式
参考示例：`D:\codex\rtl_expert\tools\iface_reg_adder.json`

字段：
- `module`：模块名；`clock`（默认 clk）；`clock_period_ns`（默认 10）
- `reset`：`{name, active_low}`，`assert_cycles`
- `params`：例化参数 `{NAME: value}`
- `inputs`：`[{name, width, prob?}]`（prob 仅 1bit，驱动概率 0~1）
- `outputs`：`[{name, width}]`
- `cycles`：随机周期数；`seed`：随机种子

注意：重新生成 TB 会自动保留已填写的 `reference_model`，但生成后仍需人工确认
参考模型与接口一致（位宽、时序）。


## 迁移 / 换机部署
技能自包含：指令 + 全部脚本都在技能文件夹内，**拷贝技能文件夹即可迁移**。
二进制工具链不在技能内（平台相关、体积大），首次使用时自动部署：
- `setup.ps1 -Install`：把便携工具链部署到缓存根（iverilog+GTKWave 约 84MB，
  quality-lite 约 91MB）。质量门禁需要 quality-lite，缺少时对应阶段会报工具缺失。
  默认 `$HOME\.codex\rtl-toolchain`；**用户目录含非 ASCII 字符（如中文用户名）时**
  自动改用纯 ASCII 根（`C:\rtl-toolchain`、`D:\rtl-toolchain`…），因为 iverilog
  内部子进程无法解析中文路径。可用环境变量 `RTL_TOOLCHAIN` 或 `-Target` 覆盖。
  来源 = 系统已装 iverilog 或 `-Source` 指定目录。
- 或安装系统版（Windows 安装包 / `scoop install iverilog gtkwave`；
  Linux `apt install iverilog gtkwave`；macOS `brew install icarus-verilog gtkwave`），
  脚本自动检测 PATH。
- `setup.ps1 -Auto`：一条命令自动部署——缺工具时依次尝试 `scoop`/`choco` 安装，
  都没有则给出官方安装指引（需要网络；scoop/choco 不可用时仍须手动安装）。
- 查找顺序：缓存根（`Get-RtlToolchainRoot`）→ 工作区 `tools\iverilog` → PATH。
依赖清单：
- 必需：iverilog + vvp（编译+仿真，约 25MB）
- 必需（质量门禁）：Yosys + slang + sby（`quality-lite`，约 91MB）
- 可选：GTKWave（看波形，约 56MB）；Verible（格式化）；Python 3（生成器、rtlq、sby）
目标机验证：`setup.ps1`（-Check）报告 7 项依赖 → 任一工作区跑 `rtlq.ps1 all -W <工作区> -Top <module>`。
Linux/macOS 用 `scripts/run.sh [模块] [bug|wave] [工作区]`。
## 离线部署（无网环境）
导出机（有网/已装好工具链）：
- `export.ps1 -Out <zip>`：把「技能 + iverilog + verible + quality-lite」打成一个 zip。
  默认输出当前目录 `rtl-closed-loop-offline.zip`；`-NoToolchain` 只打技能；
  `-ToolchainSource <目录>` 指定 iverilog 来源（需含 `bin\iverilog.exe`）；
  `-QualityLiteSource <目录>` 指定 Yosys/slang/sby 来源。
- 打包内容：`toolchain\iverilog`、`toolchain\verible`、`toolchain\quality-lite`、
  `toolchain\manifest.json`（若工作区 `tools\manifest.json` 存在）。
目标机（完全无网）：
1. 拷贝技能文件夹（或解压 zip 中的 `skill\rtl-closed-loop`）到本机 skills 目录
2. `setup.ps1 -Offline`（自动找工作区根目录的离线包；或 `-Offline -Zip <路径>` 显式指定）：
   从 zip 解压 `toolchain\iverilog` 到缓存根、`toolchain\quality-lite` 到缓存根同级
   （中文用户名同样自动落纯 ASCII 根；`-Target` 可覆盖）；`toolchain\manifest.json`
   仅在目标工作区缺少 `tools\manifest.json` 时恢复
3. `setup.ps1 -Check` 确认 7 项依赖齐全 → 任一工作区跑 `rtlq.ps1 all -W <工作区> -Top <module>`
自动发现（推荐做法）：
- 把 `rtl-closed-loop-offline.zip` 放到工作区根目录，之后无需手动指定路径：
  - `run.ps1` / `wave.ps1` 检测到工具缺失时，自动在工作区根（及 `tools\`、技能目录旁）寻找离线包并部署工具链
  - `setup.ps1 -Offline` 不带参数自动找工作区根目录的离线包（显式指定用 `-Offline -Zip <路径>`）
- 查找顺序：工作区根 → 工作区 `tools\` → 技能目录旁
执行前提（新装 Windows 的 PowerShell 默认 Restricted，不允许直接跑脚本）：
- 用 `powershell -NoProfile -ExecutionPolicy Bypass -File <技能>\scripts\setup.ps1 -Offline`（自动找工作区离线包；显式指定加 `-Zip <zip>`）
- 或先执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 一次
- 沙箱环境下写缓存根（如 `C:\rtl-toolchain`）会触发授权确认，批准后脚本继续
注意：
- zip 内工具链是导出机平台的二进制（Windows 便携包），跨平台需在对应平台重新导出。
- 完全离线时无 Python 可用 `run.sh` 的 iverilog 回退路径仿真/看波形；`rtlq`、`gen_tb.py`
  和 sby 形式验证需要 Python 3。Windows 上 sby 建议 Python 3.12（rtlq 自动用 `py -3.12`）。

## 更新已部署环境
已成功迁移的环境要升级到新版技能/工具链：
1. **技能更新**：用新版技能文件夹整体覆盖旧目录（保留原路径，如 `%USERPROFILE%\.agents\skills\rtl-closed-loop`）。
   - 推荐镜像覆盖：`robocopy <新技能目录> <目标技能目录> /E /MIR`（自动删除旧脚本，避免新旧混用）
   - 或先删除旧目录再拷贝新版。
2. **工具链更新**（仅当新离线包内含工具链变更时需要；纯脚本/文档更新可跳过）：
   - `& '<技能>\scripts\setup.ps1' -Offline -Zip <新离线包.zip>`：删除旧缓存重新解压，
     iverilog、verible、quality-lite 一并刷新；已有 `tools\manifest.json` 不被覆盖。
3. **验证**：
   - `& '<技能>\scripts\setup.ps1' -Check` → 7 项依赖全部 `[OK]`（Verible 缺失只显示 `[OPT]`）
   - 任一工作区跑 `rtlq.ps1 all -W <工作区> -Top <module>` → 结论 `PASS`
说明：
- 判断是否需要第 2 步：`setup.ps1 -Check` 全绿且新 zip 未变更工具链二进制时可跳过；拿不准就重跑一次 `-Offline`（幂等，仅刷新缓存）。
- 显式 `-Offline` 与自动恢复（run.ps1/wave.ps1 缺工具时触发）行为一致：都会恢复 iverilog + verible + quality-lite。
## 激励与时序约定（理想仿真、零延时）
- 激励（wr_en/rd_en/wr_data 等）用 **NBA 在上升沿驱动**，零延时提交；
  DUT 在上升沿采样"沿前值"（上一拍驱动的值），完全符合时序逻辑语义。
- TB 在上升沿用阻塞读捕获 DUT 实际采样的输入（`*_cap`），参考模型在负沿
  使用捕获值计算期望（负沿时 DUT 输出已稳定，**不需要任何 #1 延时**）。
- 波形表现：所有信号（激励与输出）都在上升沿变化，无中间沿跳变。
- 反例（不要再用）：负沿驱动 + #1 会产生"下沿跳变"的人为时序痕迹，
  且违背"理想仿真不应有延时信息"的语义。
## 已知坑（必须遵守）
1. iverilog 装在含空格路径 `D:\01 software\...`，直接调用其内部子进程（ivlpp）会失败；
   必须经 junction `D:\codex\rtl_expert\tools\iverilog` 调用（run.ps1/wave.ps1 已自动处理）。
2. 本机为 Windows PowerShell 5.1：修改任何 .ps1 后必须保存为 **UTF-8 with BOM**，
   否则中文注释会导致脚本解析错位（报错行号偏移、变量变空）。
3. iverilog 不支持 `$srandom`；随机种子用标准 `$random(seed)`。
4. iverilog 要求 function 至少一个输入端口，如
   `function [31:0] urand; input dummy; ... endfunction`。
5. VCD 不 dump 内存数组（如 FIFO 的 `mem`），需要观测时加探针总线。
6. SVA 断言支持弱：用"每拍 if 检查 + 错误计数"替代 `assert property`。
7. 数值位宽陷阱：Verilog 表达式宽度取最大操作数宽度，加法需显式加宽
   （如 `exp_sum = {1'b0, a_cap} + {1'b0, b_cap};`）。
8. Yosys 在 Windows 上要求正斜杠路径（`D:/codex/...`）；rtlq 已统一转换，手工脚本需注意。
9. sby 必须显式传 `--yosys <yosys.exe>` / `--abc <yosys-abc.exe>`，并设
   `PYTHONUTF8=1`；本机默认 Python 是 3.14 alpha，sby 用 `py -3.12` 更稳。
10. sby 的 `[files]` 会把源文件复制到工作目录（`report/formal/<top>`），
    修改 RTL 后必须重跑；rtlq 每次运行前会清理旧工作目录。
11. Yosys `equiv_opt -blacklist` 的文件名不能带 shell 引号（rtlq 已按裸路径传入）。
12. Verible `--rules` 与项目 R1-R10 规则不是一一对应；以 `format_check.py`
    的 R1-R10 为准，Verible 仅做格式化和补充 lint。

## GTKWave 实时加观测信号
- 路径：`D:\01 software\iverilog\gtkwave\bin\gtkwave.exe`（iverilog 自带，无需另装）
- 仿真运行期间：`File -> Enable Live View` 开启实时刷新
- 左下角信号搜索框输入任意信号（如 `dut.wptr`）回车并拖入波形区，无需重启仿真
- VCD 已 dump 全层级信号（46 个），含 DUT 内部