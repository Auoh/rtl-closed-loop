# 闭环步骤详解

## 0. 输入
- 用户需求说明（功能、接口、边界行为、验收标准）
- 可选：已有 .v 文件

## 1. 规格化 → docs\<module>_spec.md
- 接口表：信号/方向/位宽/时序
- 行为要求：逐条可验证
- 验收标准：确定性检查点 + 随机统计指标（如溢出/下溢尝试次数非零）

## 2. RTL 检查清单
- 可综合风格、参数化、复位完整、无意外 latch、位宽对齐
- 文件命名：`rtl\<module>.v`，模块名与 TB 顶层一致

## 2.5 测试点分解与完备性评审（写 TB 之前）

因果顺序固定为：**规格条目 → 测试点 → 完备性检查 → 用例设计 → 执行**。
不允许从需求直接跳到写 TB，否则覆盖是否完整只能靠临场判断。

1. 从 §1 的每条需求、每个边界与非法配置抽出测试点，编号
   `TP<需求号>.<序号>`，写入 `docs/testplan_<module>.md`
   （模板：`references/templates/testplan.md`）。
2. 每个测试点必须标注：类别（功能 / 边界 / 异常与非法配置 / 复位 /
   接口时序 / 性能约束）、完备性判据、预期载体（`DIRECTED` 段、随机段、
   `INJECT_BUG` 注入点、formal 属性名）。
3. 最低完备性要求：
   - 每条需求 ≥1 个测试点；每个测试点 ≥1 个用例或断言；
   - 边界条件与非法/异常配置逐条显式，不得用“随机覆盖”代替；
   - 复位行为与接口时序各自单独成点；
   - 性能约束必须有可判定判据，不适用时写“不适用 + 理由”。
4. 完备性评审：无孤儿需求、无无主测试点、每个载体可定位；评审通过后才进入
   §3 写 TB。
5. 需求变更时先改规格与 testplan，再改 RTL/TB；回归后把实际结果回填
   testplan 的“结果”列。negative 注入点至少覆盖一个关键验收点。

## 3. 测试环境
- 接口 JSON → `gen_tb.py` 生成骨架（示例：技能 `references\examples\iface_reg_adder.json`）
- 重新生成只保留 `reference_model` 任务内部逻辑、`REF_DECLS_BEGIN/END` 声明和
  `DIRECTED_BEGIN/END` 定向激励区；其他手工代码会被覆盖。跨拍状态请在 `REF_DECLS`
  区声明，并在参考模型任务内更新
- `REF_DECLS` 区的 `ref_*` 必须用 `initial` 赋初值（否则 X 会在首次比较中传播）；
  参考模型的复位分支也要覆盖这些状态：
  ```verilog
  initial begin
      ref_cnt = 0;
      ref_busy = 1'b0;
  end
  ```
- 参考模型要点：
  - 独立计数/独立状态判定，不依赖 DUT 输出（避免循环论证）
  - 期望值按需求语义编写，注意位宽加宽
  - **每个检查周期调用一次** `reference_model; check_outputs;`。参考模型的跨拍
    状态（`ref_*`）按周期推进，跳过某个 `negedge` 会让它与 DUT 失步，之后即使
    DUT 正确也会报假失败；定向激励段也必须逐拍成对调用，不能只在末尾检查一次。
- 补充定向边界用例：满/空/溢出/下溢/首读顺序/复位后行为；写在
  `DIRECTED_BEGIN/END` 区，重新生成时保留

## 4. 回归判定
- 输出 `RESULT: PASS` 且退出码 0 才算通过
- 检查统计合理性：写入/读取尝试、成功次数、溢出/下溢尝试
  （覆盖到边界才有意义）

## 5. 负向演练（每模块至少一次）
- 在 RTL 里临时用 `ifdef` 注入代表性缺陷（如去掉满/空保护）
- 确认 TB 能报错且退出码非 0，然后移除注入
- 目的：验证 TB 敏感度，防止"测试写了但没抓到任何东西"
- `rtlq.py all` 的 negative 阶段只在**顶层 RTL**（`rtl\<top>.v`，按文件名 stem
  匹配 `--top`）文本包含 `INJECT_BUG` 时自动运行 `sim --bug`；没有该分支时
  记为 SKIP 并在 reason 中说明，不是失败。需要门禁覆盖时在 RTL 中保留注入
  分支，或手工运行 `sim --bug` 并把日志归档。

## 6. 波形确认
- `wave.ps1` 打开 GTKWave；无 GUI 环境用 `wave.ps1 -NoGui` 只生成波形文件，
  再拷到有界面的机器查看。核对：复位时序、首笔读写、满/空翻转、
  读数据一拍延迟、随机段与排空段

## 7. 质量门禁
- 一键：`rtlq.py all -W <工作区> --top <module>`，阶段：lint → sim → negative → synth → lec → formal
- lint：R1-R10 风格 0 违例、slang 0 warning、Yosys 结构检查无 latch/组合环
- synth：cells/FF/depth 不超过 `config\ppa_budget.json`；超限必须优化或书面说明
- lec：Yosys `equiv_opt` unproven=0。状态机按 `coding_style.md` 第 13 节写
  （`(* fsm_encoding = "none" *)` + F2 每个分支显式赋值 `state_next`，保持分支
  写状态常量、不要写 `state_next = state;`），通常可保持 blacklist 为空；
  blacklist 仅用于工具无法匹配的等价编码，不得掩盖真实不等价。
- formal：`formal\<module>.sby` 的 prove 必须 `DONE (PASS)`；无配置时 SKIP 并说明。
  最小可运行模板见 `references\examples\formal\`：`initial boot = 0` + 复位窗口内
  `assume(rst_n == 0)` 清除 anyinit，断言用 `boot >= RESET_CYCLES` 门控；
  `[files]` 路径相对 `-W` 工作区。quality-lite 无 `yosys-witness`，失败时按
  `toolchain.md`「形式验证调试」用日志和定向仿真定位。
- 变异证据（改坏 RTL 后 formal 必须 FAIL）归档到 `report\mutation\<module>\`；
  `all`/`report` 重生成的 `summary.md` 会列出该目录下的文件（写法见
  `references\examples\formal\README.md`「变异证据归档」）。
- 产物：`report\quality.json`、`report\summary.md`、`report\logs\`

## 8. 优化（基线 → 改动 → 复测 → 对比 → 记录）
- 常见项：消除冗余寄存器、指针比较简化、合并等价数据通路、参数化宽度、清理仿真残留
- 固定顺序：
  1. **记录基线**：改动前跑 `rtlq.py all -W <工作区> --top <module>`；快照追加到
     `report\history\<module>\<timestamp>.json`。要对比更早版本时，后续显式传
     `--baseline <快照文件>`（`synth`/`all`/`compare` 均支持）。
  2. **优化 RTL**：一次只做一组语义等价改动，保留原代码对照。
  3. **复测**：重跑 4-7；`rtlq.py all` 会自动写新快照，并在
     `report\summary_<module>.md` 生成「Baseline vs Current」小节。
  4. **对比**：`rtlq.py compare -W <工作区> --top <module>`，检查六阶段状态
     （PASS/WARN/SKIP/FAIL/ERROR）与 cells/FF/depth 变化；退出码 0=PASS，
     1=存在阶段回归、PPA 回退或预算超限。`--allow-ppa-regression` 仅放宽
     PPA 增量判定，不放过预算超限。CI 里若只跑 `all`，内嵌 Baseline vs Current
     对比**默认不改变 `all` 的退出码**（用于记录基线时不应因实验性改动失败）；
     需要门禁时加 `all --fail-on-regression`。
  5. **记录**：把优化理由、前后数据、命令与退出码写入
     `docs\optimization_iteration.md`；有回归则回退该改动。
- 注意：基线在写当前快照之前解析，历史快照只追加、不覆盖；`compare` 默认
  取最近两次快照，因此中间不要插入无关的 `synth` 运行。

### 8.1 优化前后 RTL 等价性（baseline vs optimized）

`lec` 阶段只比较“当前 RTL vs 综合网表”，不比较两版 RTL。优化前后要单独做一次
等价性检查，用 Yosys `equiv_make` + `equiv_induct`（quality-lite 自带）。
把优化前版本保存为 `docs\rtl_baseline\<top>.v`（模块名仍为 `<top>`；**不要**放在
`rtl\`，否则会被 `rtlq` 的 RTL 扫描当作重复模块），在工作区根目录写 `equiv.ys`：

```text
read_verilog docs/rtl_baseline/<top>.v
prep -top <top>
design -stash gold
read_verilog rtl/<top>.v
prep -top <top>
design -stash gate
design -copy-from gold -as gold <top>
design -copy-from gate -as gate <top>
equiv_make gold gate equiv
hierarchy -top equiv
async2sync
equiv_simple
equiv_induct
equiv_status -assert
```

运行（quality-lite 的 Yosys 在 `<质量根>\yosys\bin\yosys.exe`，也可用 PATH 中的
`yosys`）：

```powershell
& '<质量根>\yosys\bin\yosys.exe' -s equiv.ys 2>&1 | Tee-Object docs\equiv_<top>_<时间戳>.log
```

- 两版模块名必须相同（都叫 `<top>`），`design -stash` 后由
  `-copy-from ... -as gold/gate` 放入同一设计；
- 异步复位设计保留 `async2sync`，纯同步复位可省略；
- 状态机若被重新编码，先按 `coding_style.md` 第 13 节加
  `(* fsm_encoding = "none" *)`，否则会因状态编码不同而失败；
- `equiv_status -assert` 不等价时返回非 0（实测把 `cnt+1` 改成 `cnt+2` 报
  `Found 4 unproven $equiv cells`），把日志归档到 `docs\` 并写入优化记录；
- 输出打拍数、握手时序改变不属于“语义等价优化”，必须同步更新 TB/规格，
  不能靠这条流程放行。

## 9. 交付清单
- `docs\<module>_spec.md`（需求规格）
- `docs\testplan_<module>.md`（测试计划与需求追溯矩阵，含结果回填）
- `rtl\<module>.v`（RTL）
- `tb\tb_<module>.v`（自检 TB）
- `formal\<module>.sby` + `formal\<module>_fv.sv`（形式验证，适用时）
- `config\ppa_budget.json` / `config\quality_policy.json`（质量配置）
- `report\summary.md` + `report\quality.json`（质量报告）
- `report\logs\sim_<module>.log`（仿真运行日志；编译日志为
  `report\logs\sim_compile_<module>.log`）
- 结论摘要：PASS/FAIL、覆盖点（引用 testplan 追溯矩阵的测试点与结果）、
  PPA（cells/FF/depth）、遗留风险