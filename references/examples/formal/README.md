# Formal template: single clock + async reset

最小可运行形式验证模板，配套 `rtl-closed-loop` 的 `formal` 阶段。

| 文件 | 作用 |
|---|---|
| `rtl/demo_ctr.v` | 示例 DUT（异步低有效复位） |
| `formal/demo_ctr.sby` | sby 任务：`mode prove`、`[engines] abc pdr` |
| `formal/demo_ctr_fv.sv` | 形式 wrapper：boot 计数、复位约束、断言门控 |

目录结构与工作区一致。把 `rtl/`、`formal/` 复制到工作区后运行：

```powershell
python scripts/rtlq.py formal -W <工作区> --top demo_ctr
```

要点：

- `prep` 会执行 `formalff -ff2anyinit`，所有未初始化触发器在形式视图中
  初始值任意；不能用单条 `initial assume(rst_n == 0)` 代替复位序列。
  模板用 `initial boot = 0` + 前 `RESET_CYCLES` 拍 `assume(rst_n == 0)`
  清空任意初值，之后 `assume(rst_n == 1)` 并仅在 `boot >= RESET_CYCLES`
  时检查断言。
- `[files]` 路径相对于 `-W` 工作区，不是相对于 `.sby` 文件所在目录；
  sby 会把文件复制到 `report/formal/<top>/`，所以 `[script]` 里的 `read`
  使用复制后的文件名（不含 `rtl/`、`formal/` 前缀）。
- 带异步复位的设计在 `prep` 后加 `clk2fflogic`；只有同步复位时可省略。
- 本模板用 `[engines] abc pdr`，因为技能自带的 quality-lite 不含
  `yosys-smtbmc`。`smtbmc` 的可用性与失败轨迹说明见
  `references/toolchain.md` 的「形式验证引擎与调试」。
