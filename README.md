# rtl-closed-loop — RTL 小模块闭环开发与验证技能

给 AI 编码助手（Claude Code 等）使用的一套 Verilog/SystemVerilog 小模块开发流程：
从需求规格化、RTL 编写、自检测试台、仿真回归、错误注入，到 lint、综合 PPA、LEC 等价性
和 sby 形式验证，全部由技能内的脚本驱动，退出码即结论。

面向的对象是**单个可综合小模块**（计数器、FIFO、仲裁器、UART、PWM 等），
不做布局布线、签核 STA 和后端实现。

---

## 1. 环境要求

| 组件 | 用途 | 是否必需 |
|---|---|---|
| Python 3.8+ | `rtlq.py`、`gen_tb.py`、sby | 必需 |
| Icarus Verilog 12 + vvp | 编译与仿真 | 必需 |
| Yosys 0.66 | 综合、结构检查、LEC | 质量门禁必需 |
| slang 12 | SystemVerilog lint | 质量门禁必需 |
| SymbiYosys (sby) | 形式验证 | 质量门禁必需 |
| GTKWave | 看波形 | 可选 |
| Verible | 代码规范检查/格式化 | 可选 |

前四项由技能自带的 `quality-lite` 便携包提供（约 91MB），不需要分别安装。

## 2. 安装

### 2.1 放置技能

把本仓库整个目录放到你的 Agent 客户端的技能目录，例如：

- Windows：`C:\Users\<用户名>\.agents\skills\rtl-closed-loop`
- Linux/macOS：`~/.agents/skills/rtl-closed-loop`

具体路径以客户端为准；技能自带 `SKILL.md`，放在技能根目录即可被识别。

### 2.2 部署工具链

Windows（PowerShell）：

```powershell
# 部署便携工具链到缓存根（默认 C:\rtl-toolchain 或 $HOME\.codex\rtl-toolchain）
& '<技能>\scripts\setup.ps1' -Install

# 已有系统安装的 iverilog 时，也可以只检测
& '<技能>\scripts\rtlq.ps1' doctor
```

Linux/macOS：

```bash
sudo apt install iverilog gtkwave     # 或 brew install icarus-verilog gtkwave
python3 <技能>/scripts/rtlq.py doctor
```

`doctor` 输出 11 项工具状态；全部 `[OK]` 或仅 `[WARN]`（如路径含空格）即表示可用。
`[MISS]` 表示质量门禁缺工具，仿真仍可跑，但 `all` 会失败。

> 用户目录含中文时，`setup.ps1 -Install` 会自动使用纯 ASCII 缓存根（如 `C:\rtl-toolchain`），
> 避免 sby/Yosys 在中文路径下出问题。

## 3. 快速开始

在一个新工作区里：

```bash
mkdir -p my_mod/{rtl,tb,docs,config,formal}
```

**1）写规格** → `docs/demo_spec.md`：接口表、边界行为、PASS/FAIL 判据。

**2）写 RTL** → `rtl/my_mod.v`（遵守 `references/coding_style.md`）。

**3）生成测试台骨架**

```powershell
python '<技能>\scripts\gen_tb.py' -w . config\my_mod_iface.json
```

接口 JSON 示例见 `references/examples/iface_reg_adder.json`，字段说明见
`references/toolchain.md` 的「gen_tb.py 接口 JSON 格式」。

生成后在 `tb/tb_my_mod.v` 里只改两处：

- `task reference_model`：填期望逻辑（必须独立于 DUT，禁止例化或复制 DUT 表达式）；
- `REF_DECLS_BEGIN/END` 之间：声明跨拍状态（重新生成时会保留这一区和模型逻辑）。

**4）跑回归**

```powershell
python '<技能>\scripts\rtlq.py' sim -W . --top my_mod      # 期望 RESULT: PASS，rc=0
python '<技能>\scripts\rtlq.py' sim -W . --top my_mod --bug # 期望 FAIL，rc=1（负向演练）
```

**5）跑完整质量门禁**

```powershell
python '<技能>\scripts\rtlq.py' all -W . --top my_mod       # 六阶段全 PASS 时 rc=0
```

**6）看报告**：`report\summary.md`、`report\summary_my_mod.md`、`report\quality.json`。

## 4. 工作区结构

```
my_mod/
├─ rtl/            RTL 源文件（.v/.sv）
├─ tb/             自检测试台 tb_<top>.v
├─ docs/           规格、优化记录、编码报告
├─ config/         ppa_budget.json、quality_policy.json、接口 JSON
├─ formal/         <top>.sby 与 _fv.sv（形式验证）
├─ sim/            仿真中间产物、wave.vcd
└─ report/         质量报告、日志、history 快照
```

## 5. 常用命令

Windows 用 `scripts\rtlq.ps1`，Linux/macOS 用 `scripts/rtlq`；也可直接 `python scripts/rtlq.py`。
注意：PowerShell 包装器接受 `-Top`/`-W`，`rtlq.py` 本体只接受 `--top`/`--workdir`。

| 目的 | 命令 |
|---|---|
| 环境自检 | `rtlq.ps1 doctor` |
| 全流程门禁 | `rtlq.ps1 all -W <工作区> -Top <模块>` |
| 单项 | `rtlq.ps1 lint｜sim｜synth｜lec｜formal -W <工作区> -Top <模块>` |
| 负向演练 | `rtlq.ps1 sim -W <工作区> -Top <模块> -Bug` |
| 基线对比 | `rtlq.ps1 compare -W <工作区> -Top <模块>` |
| 编译+仿真回归 | `run.ps1 -W <工作区> -Top <模块>` |
| 波形 | `wave.ps1 -W <工作区> -Top <模块>`（加 `-NoGui` 只生成 VCD） |
| 规范检查 | `format.ps1 -W <工作区> -Top <模块> -Report docs\coding_report_<模块>.md` |
| 自动格式化 | `format.ps1 -W <工作区> -Top <模块> -Fix` |
| TB 骨架 | `python scripts/gen_tb.py -w <工作区> <接口JSON>` |
| 导出离线包 | `export.ps1 -Out <zip>` |
| 离线恢复 | `setup.ps1 -Offline -Zip <zip>` |

## 6. 闭环流程

1. 规格化（docs）
2. RTL 编写/审查（外部 RTL 先 `format.ps1 -Report`）
3. 测试台：`gen_tb.py` 生成 → 填独立参考模型
4. 回归：`sim` 必须 PASS
5. 负向演练：`--bug` 必须 FAIL，且 `all` 的 negative 阶段 PASS
6. 波形确认（可选但建议）
7. 质量门禁：`all` 六阶段全 PASS
8. 优化迭代：**记录基线 → 改动 → 重测 → compare → 记录文档**
9. 交付：spec + RTL + TB + 日志 + summary + 结论

退出码就是结论：`0=PASS`，非 0 不允许宣称通过。

## 7. 质量门禁判据

| 阶段 | 通过条件 |
|---|---|
| lint | verible 风格 0 违例；slang 0 error/0 warning；Yosys 无 latch、无组合环 |
| sim | TB 打印 `RESULT: PASS`，退出码 0 |
| negative | 注入缺陷后仿真必须 FAIL |
| synth | cells / FF / 逻辑深度不超 `config/ppa_budget.json` 预算 |
| lec | Yosys 等价性 `unproven=0` |
| formal | `formal/<top>.sby` 的 prove 为 `DONE (PASS)` |

PPA 是 Yosys generic 映射后的相对值，用于回归对比，不等同于签核 STA。

### 7.1 PPA 预算与基线

`config/ppa_budget.json`：

```json
{
  "version": 1,
  "default": {},
  "tops": {
    "my_mod": { "max_cells": 200, "max_ff": 40, "max_depth": 20 }
  }
}
```

每次 `synth`/`all` 会在 `report/history/<top>/` 追加快照，不覆盖旧快照。
`compare` 默认对比最近两次；也可 `--baseline <文件|时间戳|目录>` 指定更早的基线。
出现阶段回归或超预算时退出码为 1。

### 7.2 质量策略

`config/quality_policy.json` 控制超时、阶段开关和 LEC blacklist：

```json
{
  "lint": { "strict_warnings": false, "yosys_structural": true },
  "sim":  { "grammar": "2012", "timeout_s": 120 },
  "synth": { "timeout_s": 300 },
  "lec":  { "timeout_s": 300, "blacklist": { "default": [], "my_mod": [] } },
  "formal": { "timeout_s": 180 },
  "all": { "negative": true, "synth": true, "lec": true, "formal": true, "fail_on_ppa": true }
}
```

LEC blacklist 只能用于工具无法匹配的等价状态编码，**不得用来掩盖真实不等价**；
放进去之前先确认清空后仍 `unproven=0`。

## 8. 形式验证（sby）

`formal/<top>.sby` 最小示例：

```
[options]
mode prove
depth 50

[engines]
abc pdr

[script]
read -formal <top>.v
read -formal -sv <top>_fv.sv
prep -top <top>_fv

[files]
rtl/<top>.v
formal/<top>_fv.sv
```

注意：本技能附带的 quality-lite **不包含 `yosys-smtbmc`**，因此必须写 `[engines] abc pdr`；
写 `smtbmc` 或省略 `[engines]` 时 `rtlq.py formal` 会直接报错并给出提示。

`[files]` 中的路径相对于 `-W` 工作区，sby 会把它们复制到 `report/formal/<top>/`。

## 9. 离线部署

在能联网、工具齐全的机器上导出（技能 + iverilog + verible + quality-lite 打成一个包）：

```powershell
& '<技能>\scripts\export.ps1' -Out rtl-closed-loop-offline.zip
```

在目标机器上：

```powershell
Expand-Archive rtl-closed-loop-offline.zip -DestinationPath .
& '<解压后的技能>\scripts\setup.ps1' -Offline -Zip <zip路径>
```

恢复后 `doctor` 应为 11 项 OK。

## 10. 常见问题

**sim 报 `'D:\01' 不是内部或外部命令`**
iverilog 安装在含空格的路径下，它内部启动 `ivlpp` 时不会加引号。
`setup.ps1 -Install` 会装到 `C:\rtl-toolchain`（无空格），`rtlq.py` 会优先使用缓存版本；
若首次编译仍解析失败，会自动改用缓存工具重试并在输出中说明。`doctor` 会对含空格路径给 `[WARN]`。

**doctor 找不到 yosys/slang/sby**
quality-lite 未部署。运行 `setup.ps1 -Install`，或设置环境变量
`RTL_QUALITY_LITE=<quality-lite 根目录>`。

**formal 报 `lacking engine configuration`**
sby 文件缺少 `[engines]` 段，补上 `[engines] abc pdr`。

**Windows 上 sby 报 Python 错误**
sby 对 Python 3.14 alpha 不稳定，技能会优先用 `py -3.12`；也可设置
`RTL_SBY_PYTHON=<python.exe>`。

**中文用户名**
`setup.ps1 -Install` 自动改用 ASCII 缓存根；若仍异常，设置
`RTL_TOOLCHAIN=C:\rtl-toolchain\iverilog`、`RTL_QUALITY_LITE=C:\rtl-toolchain\quality-lite`。

## 11. 目录说明

```
rtl-closed-loop/
├─ SKILL.md              技能入口（给 Agent 读的指令）
├─ README.md             本文件
├─ CHANGELOG.md          版本变更
├─ references/           工作流、编码规范、工具链、接口示例
├─ scripts/              rtlq.py / gen_tb.py / run.ps1 / wave.ps1 / setup.ps1 / export.ps1 ...
├─ agents/               Agent 配置
└─ docs/review-log.md    验收审查记录（已修复/待修复问题）
```

## 12. 版本

当前版本见 `CHANGELOG.md`。语义化版本：修复 → patch，新增能力 → minor。
卸载/升级只需替换技能目录并重新运行 `setup.ps1 -Install`（同源部署会跳过拷贝，不会破坏缓存）。

---

问题反馈：在本仓库提 Issue，附上 `rtlq.py doctor` 输出、失败阶段的完整日志和退出码。
