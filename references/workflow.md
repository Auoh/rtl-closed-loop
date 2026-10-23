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

## 9. 交付清单
- `docs\<module>_spec.md`（需求规格）
- `rtl\<module>.v`（RTL）
- `tb\tb_<module>.v`（自检 TB）
- `formal\<module>.sby` + `formal\<module>_fv.sv`（形式验证，适用时）
- `config\ppa_budget.json` / `config\quality_policy.json`（质量配置）
- `report\summary.md` + `report\quality.json`（质量报告）
- `report\logs\sim_<module>.log`（仿真运行日志；编译日志为
  `report\logs\sim_compile_<module>.log`）
- 结论摘要：PASS/FAIL、覆盖点、PPA（cells/FF/depth）、遗留风险