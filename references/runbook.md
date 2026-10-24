# 逐步执行手册（runbook）

本文件面向**执行能力较弱的模型**：把 `SKILL.md` 的闭环流程拆成可照做的步骤，
每一步都给出命令、期望输出和“不通过怎么办”。开始任何 RTL 工作前先读完本文件，
然后严格按 §1 → §10 的顺序执行；不要跳步，不要凭印象补结果。

## 0. 三条总规则

1. **没运行过的命令，不得写“通过”**；没看到的数字，不得写进报告或总结。
2. **退出码与 `RESULT:` 是唯一结论**。`SKIP` 不是 `PASS`；`WARN` 需要解释。
3. **不得为了让测试通过而改判据**：不删测试点、不放宽比较、不改期望值、
   不屏蔽断言、不调高 PPA 预算来“消掉”失败。判据只能因需求变更而改，并留记录。

## 1. 开工前（Preflight）

### 1.1 固定两个变量

Windows PowerShell（后续命令都用这两个变量）：

```powershell
$SKILL = 'C:\Users\<用户名>\.agents\skills\rtl-closed-loop'   # 换成实际技能目录
$WS    = 'D:\work\my_mod'                                      # 换成实际工作区
$top   = 'my_mod'                                              # 换成 DUT 顶层模块名
```

> `rtlq.ps1` 包装器用 `-W` / `-Top`；直接调用 `python rtlq.py` 时只能用
> `--workdir` / `--top`。两种写法不要混用。
>
> Linux/macOS 等价写法：`SKILL=...; WS=...; top=...`，用
> `python3 "$SKILL/scripts/rtlq.py" sim --workdir "$WS" --top "$top"`，
> 建目录用 `mkdir -p "$WS"/{rtl,tb,docs,config,formal,report/logs}`。

### 1.2 建工作区

```powershell
New-Item -ItemType Directory -Force "$WS\rtl","$WS\tb","$WS\docs","$WS\config","$WS\formal","$WS\report\logs" | Out-Null
```

目录约定：`rtl\<top>.v`、`tb\tb_<top>.v`、`docs\<top>_spec.md`、
`docs\testplan_<top>.md`、`formal\<top>.sby`、`config\ppa_budget.json`。

### 1.3 环境自检（必做，结果归档）

```powershell
& "$SKILL\scripts\rtlq.ps1" doctor 2>&1 | Tee-Object "$WS\report\logs\doctor.txt"
```

- 期望：11 项全部 `[OK]`，或仅有路径含空格的 `[WARN]`。
- 出现 `[MISS]`：先运行 `& "$SKILL\scripts\setup.ps1" -Install`，再重跑 `doctor`；
  仍缺失就把 `doctor` 输出原样报告给用户，**不要**跳过质量门禁继续。
- `doctor` 不是装饰：`all` 阶段缺工具会直接 FAIL。

### 1.4 输入检查

- 需求里必须能回答：端口表（方向/位宽/时钟复位）、每条功能行为、
  边界与非法配置、复位行为、接口时序、验收判据。
- 缺关键信息时：在 `docs\<top>_spec.md` 的「假设」一节写明假设并向用户确认一次；
  不得自行发明端口或把“未说明”当成“随便实现”。

## 2. 规格化（产物：`docs\<top>_spec.md`）

必须包含四块，缺一不可：

1. 接口表：信号 / 方向 / 位宽 / 时钟域 / 复位值 / 有效条件；
2. 行为要求：每条一个编号 `R1..Rn`，写成可判定语句（“当 X 且 Y 时，下一拍 Z=1”）；
3. 边界与非法配置：`B1..Bn`，逐条写期望行为（拒绝 / 饱和 / 保持 / 报错）；
4. 验收标准：每条要求的 PASS/FAIL 判据，以及需要波形测量的时间参数。

**完成判据**：接口表行数与 RTL 端口一一对应；每条 `R*`/`B*` 都有判据。
不满足就不要开始写 RTL。

## 3. RTL（产物：`rtl\<top>.v`）

1. 按 `references/coding_style.md` 写；状态机优先用第 13 节的 LEC 友好写法；
2. 外部提供的 RTL 先跑规范报告并修复：

```powershell
& "$SKILL\scripts\format.ps1" -W $WS -Top $top -Report "$WS\docs\coding_report_$top.md"
```

3. 再跑结构检查：

```powershell
& "$SKILL\scripts\rtlq.ps1" lint -W $WS -Top $top
"rc=$LASTEXITCODE"
```

**完成判据**：`lint` 输出 `PASS`、`rc=0`；规范报告无未处理违例。
`-Fix` 只修格式类问题；R3/R4 等语义项要手工改。

## 4. 测试点分解（产物：`docs\testplan_<top>.md`，必须在写 TB 之前）

复制 `references\templates\testplan.md`，把 `<...>` 全部替换。顺序固定：

```text
需求 R*/B* → 测试点 TPx.y → 完备性检查 → 用例/断言载体 → 执行 → 回填结果
```

最低要求：

- 每条需求 ≥1 个测试点；每个测试点 ≥1 个载体（`DIRECTED:` / `RANDOM:` /
  `NEG:` / `FORMAL:` / `TB:`），且载体真实存在、能定位；
- 边界、非法配置、复位、接口时序各自单独成点，不得用“随机覆盖”代替；
- 表格单元格里出现字面量 `|` 必须写成 `\|`，否则 Markdown 表格错列。

**完成判据**：模板 §4 的勾选项全部勾上；没有孤儿需求，没有无主测试点。
评审没通过就写 TB，属于跳步。

## 5. 测试台（产物：`tb\tb_<top>.v`）

### 5.1 写接口 JSON

参考 `references\examples\iface_reg_adder.json`，字段见 `toolchain.md`
「gen_tb.py 接口 JSON 格式」。至少要有 `module`、`clock`、`reset`、
`inputs`、`outputs`、`cycles`、`seed`。

### 5.2 生成骨架

```powershell
python "$SKILL\scripts\gen_tb.py" -w $WS "$WS\config\<top>_iface.json"
```

期望：生成 `tb\tb_<top>.v`，退出码 0。报错就修 JSON，不要手写整个 TB 绕过生成器
（生成器已处理激励时序约定）。

### 5.3 只改三处（重新生成会保留）

1. `task reference_model` 内部：按需求语义写期望值；
2. `REF_DECLS_BEGIN/END`：声明跨拍 `ref_*` 状态，并用 `initial` 赋初值；
3. `DIRECTED_BEGIN/END`：写满/空/溢出/下溢/复位/背靠背等定向激励。

硬性要求：

- 参考模型**不得**例化 DUT、不得复制 DUT 表达式、不得读 DUT 输出；
- 每个检查周期调用一次 `reference_model; check_outputs;`（定向段也逐拍调用）；
- 每一处输出比较必须用 `!==` / `===`，禁止 `!=`；
- 检查在 `negedge` 做；寄存器输出用 `*_cap`，组合输出用当前输入；
- 不要用 `#1` 或任何延时。

生成后自检：

```powershell
# 1) 不应出现裸 !=（应全部写成 !==）
Select-String -Path "$WS\tb\tb_$top.v" -Pattern '(?<!!)!=(?!=)'
# 2) 参考模型里不应例化 DUT（顶层模块名出现在语句开头 + 实例名 + 括号）
Select-String -Path "$WS\tb\tb_$top.v" -Pattern "^\s*$top\s+\w+\s*\("
```

两条命令都期望**没有输出**；有输出就回到 TB 修正。

**完成判据**：TB 能编译；参考模型独立；比较全部用 `!==`；定向段覆盖
testplan 中标记为 `DIRECTED` 的测试点。

## 6. 回归（产物：`report\logs\sim_<top>.log`）

```powershell
& "$SKILL\scripts\rtlq.ps1" sim -W $WS -Top $top
"rc=$LASTEXITCODE"
```

**通过条件（三个同时满足）**：

- stdout 出现 `RESULT: PASS`；
- `rc=0`；
- 检查统计合理：`checks > 0`、`errors = 0`（`checks` 恒为 0 等于没测）。

失败处理顺序：

1. 先看编译错误：修 RTL/TB 的语法与端口，不要改判据；
2. 再看首个 mismatch 的时间与信号：区分 DUT 错还是参考模型错；
3. 参考模型错就改参考模型；DUT 错就改 RTL；
4. **禁止**通过删除检查、放宽期望、跳过定向段来变 PASS。

## 7. 负向演练（验证 TB 真的能抓错）

```powershell
& "$SKILL\scripts\rtlq.ps1" sim -W $WS -Top $top -Bug
"rc=$LASTEXITCODE"
```

**通过条件**：`RESULT: FAIL` 且 `rc=1`（注入缺陷必须被抓到）。

- 若仍 `PASS`：TB 不敏感，回到 §5.3 加强定向检查；不得移除 `INJECT_BUG` 分支；
- `all` 的 negative 阶段只在**顶层 RTL 文件**含 `INJECT_BUG` 时自动执行；
  没有该分支时记为 `SKIP`，必须在交付说明中写原因，并手工跑一次 `-Bug`
  把日志归档到 `report\logs\sim_<top>_bug.log`；
- `SKIP` 不是通过：最终结论里不能写“负向演练通过”。

## 8. 波形判读（行为结论的唯一依据）

代码走读只能用来设计检查，**不能**作为“时序正确/行为正确”的结论。
每个行为类测试点都要落到“信号 = 值 @ 时间戳”。

### 8.1 生成 VCD

```powershell
& "$SKILL\scripts\rtlq.ps1" sim -W $WS -Top $top -Wave
```

产物：`sim\wave.vcd`（无 GUI 也能生成）。TB 中 dump 范围建议只覆盖 TB 顶层
（`$dumpvars(1, tb_<top>);`），避免不同层次复用同一 VCD id。

### 8.2 必须回答的问题

- 复位：复位期间输出是否为确定值？释放后第一拍是否符合规格？
- 首笔事务：从请求到响应几拍？数据/标志在哪一拍有效？
- 握手/反压：`valid`/`ready` 是否保持到握手？同拍读写语义？
- 边界：满/空/溢出/下溢各发生了几次？计数与指针是否回绕正确？
- 时序参数：周期、占空比、setup/hold 等，用**跳变时间戳之差**计算；
- 背靠背：两次事务之间的最小间隔是多少？

> VCD 不 dump 存储阵列（如 FIFO 的 `mem`），内部计数器也不一定在顶层。需要观测时，
> 在 TB 顶层加探针（如 `cap_count <= dut.count;`）并把探针 dump 出来；否则只
> 根据接口信号判定，不要假装看到了内部值。

### 8.3 解析规则（否则会得出错误结论）

1. **同一时间戳可能有多次 delta 变化**：同一 `(时间戳, 信号)` 只保留最后一次；
2. **id 别名**：VCD 的 id 只在 scope 内唯一，不同层次可能复用。按完整层次名
   建索引；发现同一 id 出现在多个 scope 时，缩小 dump 范围重新仿真；
3. **边界采样**：检查“沿前值”用严格小于该时间戳的最后一次变化；检查“沿后值”
   用小于等于该时间戳的最后一次变化。不要用同一个函数既查 setup 又查输出；
4. **时间单位**：先看 VCD 头部的 `$timescale`（如 `1ns` / `1ps`），换算成统一
   单位再比较；不同 TB 的 timescale 可能不同；
5. `x`/`z` 是真实结果，不要当 0 处理；复位前/未初始化信号出现 `x` 要单独判定。

### 8.4 最小解析脚本（Python 标准库，可直接改用）

```python
import sys, bisect
from collections import defaultdict

def parse(path):
    scope, ids, ev, t = [], {}, defaultdict(list), 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("$scope"):
                scope.append(s.split()[2])
            elif s.startswith("$upscope"):
                scope.pop()
            elif s.startswith("$var"):
                p = s.split()                       # $var wire 8 ! name $end
                full = ".".join(scope + [p[4]])
                ids.setdefault(p[3], []).append(full)
            elif s.startswith("#"):
                t = int(s[1:])
            elif s[0] in "bB":
                p = s.split()
                if len(p) < 2:
                    continue
                update(ev, ids, p[1], p[0][1:], t)
            elif s[0] in "01xzXZ":
                update(ev, ids, s[1:], s[0].lower(), t)
    for cid, fulls in ids.items():
        scopes = {f.rsplit(".", 1)[0] for f in fulls}
        if len(scopes) > 1:
            raise SystemExit("id %s 跨 scope 复用：只 dump 一个 scope 后重跑" % cid)
    return ev

def update(ev, ids, cid, val, t):
    for full in ids.get(cid, []):
        e = ev[full]
        if e and e[-1][0] == t:                     # 同时间戳 delta：保留最后一次
            e[-1] = (t, val)
        else:
            e.append((t, val))

def at(ev, name, t):        # 含 t：用于沿后输出
    e = ev[name]; i = bisect.bisect_right([x[0] for x in e], t) - 1
    return e[i][1] if i >= 0 else None

def before(ev, name, t):    # 严格早于 t：用于沿前 setup
    e = ev[name]; i = bisect.bisect_left([x[0] for x in e], t) - 1
    return e[i][1] if i >= 0 else None

def edges(ev, name):        # [(时间戳, 旧值, 新值)]
    e = ev[name]; out, prev = [], None
    for t, v in e:
        out.append((t, prev, v)); prev = v
    return out
```

用法示例（完整可直接运行）：

```python
ev = parse("sim/wave.vcd")
print(at(ev, "tb_my_mod.cs_n", 15000))          # 15000 时刻（含）的值
print(before(ev, "tb_my_mod.mosi", 80000))      # 严格早于 80000 的值
for t, old, new in edges(ev, "tb_my_mod.sclk"):
    print(t, old, "->", new)
```

> 完整层次名 = scope 栈用 `.` 连接 + 信号名，例如 `tb_my_mod.dut.wptr`。
> `before`/`at` 的区分是正确性的关键，不要合并成一个函数。
> 返回值是 VCD 原始字符串（`"0"`、`"1010"`）；要比较数值时用 `int(v, 2)`，
> 先判断 `v is not None` 且不含 `x`/`z`。

### 8.5 证据记录格式

每条检查写一行，归档到 `report\wave_checks_<top>.txt`：

```text
PASS | 复位释放后首拍 cs_n=1 | cs_n=1 @ 15000 ps | 复位窗口后 1 拍内释放
PASS | SCLK 半周期 DIV=4 | 40000 ps（两次上升沿差） | 40000 ps ± 0
FAIL | 溢出时 RX_LEVEL | 15 @ 91200000 ps | 期望 16
```

**完成判据**：testplan 中每个“功能/边界/复位/接口时序”测试点都有一行带时间戳的
证据；没有时间戳的结论视为未验证。

## 9. 六阶段质量门禁

```powershell
& "$SKILL\scripts\rtlq.ps1" all -W $WS -Top $top 2>&1 | Tee-Object "$WS\report\logs\all_$top.log"
"rc=$LASTEXITCODE"
```

### 9.1 输出怎么读

正常结尾形如：

```text
== rtlq all: PASS ==
  lint     PASS  ...
  sim      PASS  checks=<n> errors=0 ...
  negative PASS  expected=FAIL actual=FAIL
  synth    PASS  cells=<n> ff=<n> depth=<n>
  lec      PASS  proven=<n> unproven=0
  formal   PASS  DONE (PASS, rc=0)
RC=0
```

**通过条件**：`== rtlq all: PASS ==` 且 `rc=0`，六行状态逐项确认。
任一 `FAIL`/`ERROR` 都不得宣称通过；`SKIP` 要写原因。

### 9.2 各阶段失败处理

| 阶段 | 典型现象 | 先做什么 |
|---|---|---|
| lint | 风格违例 / slang warning / latch | `format.ps1 -Fix` 后重跑；语义违例手工改；不要关掉 `strict` 或结构检查 |
| sim | 编译错 / mismatch | 修 RTL 或参考模型；保留检查，禁止删判据 |
| negative | 注入后仍 PASS | TB 不敏感 → 加定向检查；不得移除注入分支 |
| synth | 超预算 / latch / 组合环 | 优化 RTL，或在交付说明记录超预算理由；不得静默改预算 |
| lec | `unproven>0` / `No SAT model` | 状态机按 coding_style §13；多模块见 §9.3 |
| formal | ERROR / FAIL / SKIP | 检查 `[engines] abc pdr`；FAIL 先找反例；SKIP 需补 `.sby` 或书面说明 |

### 9.3 LEC 与层次（D38）

`rtlq.py` v1.1.10 起，`lec` 在 `proc/memory/opt_clean` 之后、`equiv_opt` 之前
自动执行 `flatten`。多模块或 `$paramod` 设计若手工复现 LEC 流程，**必须**同样
加 `flatten`，否则会报 `No SAT model available for cell ...`。
单模块设计行为不变。blacklist 只允许用于工具无法匹配的等价状态编码，
不得掩盖真实不等价。

### 9.4 formal 的特殊约束

- quality-lite 不含 `yosys-smtbmc` / `yosys-witness`，`.sby` 必须显式写
  `[engines] abc pdr`；写 `smtbmc` 或省略 `[engines]` 会直接 ERROR；
- `[files]` 相对 `-W` 工作区，不是 `.sby` 所在目录；
- `prep` 会把未初始化触发器变成任意初值：用 `initial boot = 0` + 复位窗口内
  `assume(rst_n == 0)`，断言用 `boot >= RESET_CYCLES` 门控；
- 看到大量 `frame 0 (trivial)` 先检查门控是否可达（boot 位宽是否够）；
- `.sby` 的 `depth` 只限制 `mode bmc`；prove 的规模由 `timeout_s` 控制。

## 10. 报告与交付

### 10.1 必交文件

```text
docs\<top>_spec.md
docs\testplan_<top>.md          # 结果列已回填
docs\coding_report_<top>.md     # 外部 RTL 必须有
rtl\<top>.v
tb\tb_<top>.v
formal\<top>.sby + <top>_fv.sv  # 有则交；没有要在交付说明写原因
config\ppa_budget.json
config\quality_policy.json
report\quality.json
report\summary.md
report\summary_<top>.md         # 含 Baseline vs Current 小节
report\logs\                    # doctor / sim / sim_bug / all / formal
report\wave_checks_<top>.txt    # 波形证据
```

### 10.2 结论模板

```text
结论：PASS / FAIL
覆盖：需求 N 条 / 测试点 M 个 / 载体 K 个（引用 testplan 追溯矩阵）
仿真：RESULT: PASS，checks=<n>，errors=0，rc=0
负向：RESULT: FAIL，rc=1（或 SKIP + 原因 + 手工日志路径）
门禁：all PASS，rc=0；lint style=0；synth cells/ff/depth=...；lec unproven=0；
      formal DONE (PASS)
波形：X 条带时间戳证据（report\wave_checks_<top>.txt）
遗留风险：...
```

### 10.3 最终自检（逐条打勾，附证据路径）

- [ ] `doctor` 全 OK/WARN，日志已归档；
- [ ] spec 的接口表与 RTL 端口一致；
- [ ] testplan 无孤儿需求、无无主测试点，结果列已回填；
- [ ] TB 无 `!=`，参考模型独立，每拍调用检查；
- [ ] `sim` PASS、`checks>0`、`errors=0`、rc0；
- [ ] `sim -Bug` FAIL、rc1；
- [ ] 每个行为测试点有 VCD 时间戳证据；
- [ ] `all` 六阶段 PASS、rc0，日志归档；
- [ ] `summary_<top>.md` 是最后一次运行后生成的（数字与日志一致）；
- [ ] 交付说明列出所有 `SKIP` 及原因。

## 11. 常见失败速查

| 现象 | 常见原因 | 处理 |
|---|---|---|
| `RESULT: PASS` 但 `checks=0` | TB 没调用检查任务 | 每个 negedge 调用 `reference_model; check_outputs;` |
| 全 X 的 DUT 也 PASS | 用了 `!=` | 改成 `!==`，重跑 |
| 正确 DUT 报大量 FAIL | 在上升沿比较 / 组合输出用了 `*_cap` | 负沿比较；寄存器用 `*_cap`，组合用当前输入 |
| 参考模型与 DUT 同步偏移 | 某些周期漏调参考模型 | 定向段也逐拍调用，不只在末尾检查 |
| `-Bug` 仍然 PASS | TB 没覆盖注入的缺陷 | 加对应定向检查；不要移除注入 |
| `all` negative SKIP | 顶层 RTL 无 `INJECT_BUG` | 补分支，或手工 `-Bug` 并归档日志 |
| sby `lacking engine configuration` | `.sby` 缺 `[engines]` | 加 `[engines] abc pdr` |
| sby `FileNotFoundError` | `[files]` 写成相对 `.sby` 的路径 | 改成相对 `-W` 工作区 |
| LEC `No SAT model` | 多模块/`$paramod` 未 flatten | 用 v1.1.10+ 的 `rtlq lec`；手工流程加 `flatten` |
| `unproven` 只剩 `state_next` | FSM 保持分支写法触发 DFFE | 按 coding_style §13 显式写状态常量 |
| formal `frame 0 (trivial)` | 断言门控永假 / boot 位宽不够 | 检查 `boot >= RESET_CYCLES` 是否可达 |
| PPA 与上次差异巨大 | Yosys 版本或综合脚本变了 | 看快照 `tools`；版本不一致时 delta 不可解释 |

## 12. 禁止行为清单

- 伪造命令输出、日志、时间戳或验收数字；
- 在 `rc≠0`、`RESULT: FAIL` 或存在 `ERROR` 时宣称通过；
- 把 `SKIP` 当成 `PASS`（尤其是 negative 与 formal）；
- 删除/放宽测试点、期望值、断言来消除失败；
- 用代码走读代替波形证据判定行为与时序；
- 参考模型例化 DUT 或复制 DUT 表达式；
- 为通过 LEC 而把真实不等价信号加入 blacklist；
- 为通过 PPA 而静默调高 `ppa_budget.json`；
- 跳过 `all` 直接拿旧 `summary.md` 当本次结果。
