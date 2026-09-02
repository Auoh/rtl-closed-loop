# 工具链与环境（本机）

## 命令速查（<技能> = rtl-closed-loop 技能目录，<工作区> = 含 rtl/ tb/ 的工程根）
| 命令 | 作用 |
|---|---|
| `& '<技能>\scripts\run.ps1' -W <工作区> -Top <module>` | 编译+回归；退出码 0=PASS，非0=FAIL |
| `... -Bug` | 注入 `INJECT_BUG`（仅含该 ifdef 的演示 RTL 有效） |
| `... -Wave` | 生成 `<工作区>\sim\wave.vcd` |
| `python '<技能>\scripts\gen_tb.py' -w <工作区> <iface.json>` | 生成 TB 骨架（输出 `<工作区>\tb\`） |
| `& '<技能>\scripts\wave.ps1' -W <工作区> -Top <module>` | 后台仿真 + 打开 GTKWave |
| `& '<技能>\scripts\setup.ps1' -Install` | 部署便携工具链到 `$HOME\.codex\rtl-toolchain` |
| `& '<技能>\scripts\export.ps1' -Out <zip>` | 导出离线包（技能+工具链），供无网环境部署 |
| `& '<技能>\scripts\setup.ps1' -Offline` | 无网恢复：自动找工作区根目录的离线包（`-Offline -Zip <路径>` 显式指定） |

## Verible 格式化（verible-verilog-format）
- 工具位置：`C:\rtl-toolchain\verible\bin\verible-verilog-format.exe`（与 iverilog 同级，由 export.ps1 纳入离线包 `toolchain\verible`，`setup.ps1 -Offline` 自动恢复）。
- 固定参数：`--indentation_spaces=4 --wrap_end_else_clauses`（4 空格缩进、end/else 分行，符合编码规范）。
- 使用：`format.ps1 -W <工作区> -Top <module> [-Fix]`；`run.ps1` 每次编译前自动格式化（`-NoFormat` 关闭）。

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
- `setup.ps1 -Install`：把便携工具链部署到缓存根（约 84MB，含 GTKWave）。
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
- 可选：GTKWave（看波形，约 56MB）；Python 3（仅 gen_tb.py 生成器需要）
目标机验证：`setup.ps1`（-Check）报告 4 项依赖 → 任一工作区跑 `run.ps1 -W <工作区>`。
Linux/macOS 用 `scripts/run.sh [模块] [bug|wave] [工作区]`。
## 离线部署（无网环境）
导出机（有网/已装好工具链）：
- `export.ps1 -Out <zip>`：把「技能 + 便携工具链」打成一个 zip（约 32MB 压缩包）。
  默认输出当前目录 `rtl-closed-loop-offline.zip`；`-NoToolchain` 只打技能；
  `-ToolchainSource <目录>` 可指定工具链来源（需含 `bin\iverilog.exe`）。
目标机（完全无网）：
1. 拷贝技能文件夹（或解压 zip 中的 `skill\rtl-closed-loop`）到本机 skills 目录
2. `setup.ps1 -Offline`（自动找工作区根目录的离线包；或 `-Offline -Zip <路径>` 显式指定）：从 zip 解压 `toolchain\iverilog` 到缓存根
   （与 `-Install` 同一位置，中文用户名同样自动落纯 ASCII 根；`-Target` 可覆盖）
3. `setup.ps1 -Check` 确认 4 项依赖齐全 → 任一工作区跑 `run.ps1 -W <工作区>` 回归
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
- 完全离线时无 Python 也可仿真/看波形（仅 `gen_tb.py` 生成器需要 Python 3）。

## 更新已部署环境
已成功迁移的环境要升级到新版技能/工具链：
1. **技能更新**：用新版技能文件夹整体覆盖旧目录（保留原路径，如 `%USERPROFILE%\.agents\skills\rtl-closed-loop`）。
   - 推荐镜像覆盖：`robocopy <新技能目录> <目标技能目录> /E /MIR`（自动删除旧脚本，避免新旧混用）
   - 或先删除旧目录再拷贝新版。
2. **工具链更新**（仅当新离线包内含工具链变更时需要；纯脚本/文档更新可跳过）：
   - `& '<技能>\scripts\setup.ps1' -Offline -Zip <新离线包.zip>`：删除旧缓存重新解压，iverilog 与 verible 一并刷新。
3. **验证**：
   - `& '<技能>\scripts\setup.ps1' -Check` → 5 项依赖全部 `[OK]`
   - 任一工作区跑 `run.ps1 -W <工作区> -Top <module>` → `RESULT: PASS`
说明：
- 判断是否需要第 2 步：`setup.ps1 -Check` 全绿且新 zip 未变更工具链二进制时可跳过；拿不准就重跑一次 `-Offline`（幂等，仅刷新缓存）。
- 显式 `-Offline` 与自动恢复（run.ps1/wave.ps1 缺工具时触发）行为一致：都会同时恢复 iverilog + verible。
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

## GTKWave 实时加观测信号
- 路径：`D:\01 software\iverilog\gtkwave\bin\gtkwave.exe`（iverilog 自带，无需另装）
- 仿真运行期间：`File -> Enable Live View` 开启实时刷新
- 左下角信号搜索框输入任意信号（如 `dut.wptr`）回车并拖入波形区，无需重启仿真
- VCD 已 dump 全层级信号（46 个），含 DUT 内部