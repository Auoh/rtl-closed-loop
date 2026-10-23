#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_tb.py - 根据接口描述 JSON 生成自检测试台骨架（Verilog-2001）。

用法:
    python scripts/gen_tb.py -w <工作区> <接口描述.json>

生成: tb/tb_<module>.v
生成内容:
  - 时钟 / 复位生成
  - DUT 例化（支持参数）
  - 随机激励（上升沿 NBA 驱动、负沿检查，1bit 输入可配概率）
  - 输入上升沿捕获（*_cap），供寄存器输出的参考模型使用
  - reference_model 期望逻辑桩（主要人工填写位置；每个检查周期调用一次）
  - REF_DECLS_BEGIN/END 声明区（跨拍状态/辅助变量，重新生成时保留）
  - DIRECTED_BEGIN/END 定向激励区（重新生成时保留）
  - 自动输出比对 + 统计 + PASS/FAIL

JSON 字段:
  module          : DUT 模块名
  clock           : 时钟信号名（默认 clk）
  clock_period_ns : 周期 ns（默认 10）
  reset           : {name, active_low, assert_cycles}
  params          : {NAME: value} 例化参数
  inputs          : [{name, width, prob?}]   prob 仅用于 1bit（驱动概率 0~1）
  outputs         : [{name, width}]
  cycles          : 随机激励周期数（默认 1000）

限制: 端口位宽 <= 32 时使用 $random 驱动/比对；更宽请自行扩展。
"""
import argparse
import json
import re
import sys
from pathlib import Path

WORKSPACE = Path.cwd()
TB_DIR = WORKSPACE / "tb"


def decl(prefix, port, clock=False):
    width = port["width"]
    if width == 1:
        return "%s %s;" % (prefix, port["name"])
    return "%s [%d:0] %s;" % (prefix, width - 1, port["name"])


def reg_decl(port):
    return decl("reg", port)


def wire_decl(port):
    return decl("wire", port)


def gen(spec_path, out_path):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    mod = spec["module"]
    top = "tb_" + mod
    out_path = out_path or (TB_DIR / ("tb_" + mod + ".v"))
    old_ref = None
    old_decls = None
    old_directed = None
    if out_path.exists():
        old_text = out_path.read_text(encoding="utf-8")
        m = re.search(r"task reference_model;\s*begin(.*?)end\s*endtask", old_text, re.S)
        if m:
            old_ref = m.group(1)
        m = re.search(r"// ==== REF_DECLS_BEGIN ====(.*?)// ==== REF_DECLS_END ====",
                      old_text, re.S)
        if m:
            old_decls = m.group(1).strip("\n")
        m = re.search(r"// ==== DIRECTED_BEGIN ====(.*?)// ==== DIRECTED_END ====",
                      old_text, re.S)
        if m:
            old_directed = m.group(1).strip("\n")
    clk = spec.get("clock", "clk")
    period = spec.get("clock_period_ns", 10)
    rst = spec.get("reset", {"name": "rst_n", "active_low": True, "assert_cycles": 4})
    rst_name = rst["name"]
    rst_low = rst.get("active_low", True)
    rst_assert  = "0" if rst_low else "1"
    rst_release = "1" if rst_low else "0"
    rst_cycles = rst.get("assert_cycles", 4)
    params = spec.get("params", {})
    inputs = spec["inputs"]
    outputs = spec["outputs"]
    cycles = spec.get("cycles", 1000)
    seed = spec.get("seed")

    L = []
    a = L.append
    a("// 由 scripts/gen_tb.py 自动生成，请勿手改本头；修改接口后重新生成。")
    a("// 重新生成保留: reference_model 内部逻辑 + REF_DECLS_BEGIN/END 声明 + DIRECTED_BEGIN/END 定向激励。")
    a("// 其他手工代码（task/function、TOP 层额外逻辑）会被模板覆盖，请自行备份。")
    a("// 人工填写位置: reference_model（期望输出）；跨拍状态在 REF_DECLS 区声明并 initial 赋初值。")
    a("// 调用纪律: 每个检查周期调用一次 reference_model; check_outputs;（定向段也一样），")
    a("//           跳过某个 negedge 会让参考模型的跨拍状态与 DUT 失步，造成假失败。")
    a("// 时序约定: 激励在上升沿用 NBA 驱动（零延时），DUT 上升沿采样沿前值；检查在负沿执行，无 #1 延时。")
    a("// 参考模型取值: 寄存器输出用 *_cap（上升沿捕获的采样值）；组合输出用当前输入")
    a("//               （负沿时组合输出已反映本拍输入，*_cap 会落后一拍）。")
    a("`timescale 1ns/1ps")
    a("")
    a("module %s;" % top)
    a("")
    a("    // ---- 参数 ----")
    a("    localparam CYCLES = %d;" % cycles)
    a("")
    a("    // ---- DUT 接口 ----")
    a("    reg  %s;   // 时钟" % clk)
    for p in inputs:
        a("    " + reg_decl(p))
    for p in outputs:
        a("    " + wire_decl(p))
    a("    reg  %s;   // 复位" % rst_name)
    a("")
    a("    // ---- DUT 例化 ----")
    if params:
        ps = ", ".join(".%s(%d)" % (k, v) for k, v in params.items())
        a("    %s #(%s) dut (" % (mod, ps))
    else:
        a("    %s dut (" % mod)
    conns = [".%s(%s)" % (clk, clk)]
    for p in inputs:
        conns.append(".%s(%s)" % (p["name"], p["name"]))
    for p in outputs:
        conns.append(".%s(%s)" % (p["name"], p["name"]))
    conns.append(".%s(%s)" % (rst_name, rst_name))
    a(",\n".join("        " + c for c in conns))
    a("    );")
    a("")
    a("    // ---- 波形（编译时 -DDUMP_WAVE）----")
    a("`ifdef DUMP_WAVE")
    a("    initial begin")
    a('        $dumpfile("wave.vcd");')
    a("        $dumpvars(0, %s);" % top)
    a("    end")
    a("`endif")
    a("")
    a("    // ---- 时钟 ----")
    a("    initial %s = 0;" % clk)
    a("    always #%g %s = ~%s;" % (period / 2.0, clk, clk))
    a("")
    a("    // ---- 输入捕获（正沿采样；寄存器输出参考模型在负沿使用）----")
    for p in inputs:
        w = p["width"]
        a("    reg [%d:0] %s_cap;" % (w - 1, p["name"]))
    a("    always @(posedge %s) begin" % clk)
    for p in inputs:
        a("        %s_cap <= %s;" % (p["name"], p["name"]))
    a("    end")
    a("")
    a("    // ---- 期望输出 / 统计 ----")
    for p in outputs:
        a("    reg [%d:0] exp_%s;" % (p["width"] - 1, p["name"]))
    a("    integer errors;")
    a("    integer checks;")
    a("    localparam ERR_PRINT_MAX = 50;")
    a("    integer seed;")
    a("")
    a("    // ==== 参考模型自定义声明区（重新生成时原样保留） ====")
    a("    // 在此声明跨拍状态/辅助变量，例如: reg [7:0] ref_cnt; integer ref_state;")
    a("    // ==== REF_DECLS_BEGIN ====")
    if old_decls is not None:
        for line in old_decls.splitlines():
            a(line.rstrip())
    else:
        a("    // (在此添加 ref_* 声明)")
    a("    // ==== REF_DECLS_END ====")
    a("")
    a("    // ---- 复位 ----")
    a("    task do_reset;")
    a("        begin")
    a("            %s = %s;" % (rst_name, rst_assert))
    for p in inputs:
        a("            %s = %d'b0;" % (p["name"], p["width"]))
    a("            repeat (%d) @(posedge %s);" % (rst_cycles, clk))
    a("            %s = %s;" % (rst_name, rst_release))
    a("            repeat (2) @(posedge %s);   // 等输出稳定" % clk)
    a("        end")
    a("    endtask")
    a("")
    a("    // ==== 参考模型：期望输出逻辑（重新生成时自动保留已填内容） ====")
    a("    task reference_model;")
    a("        begin")
    if old_ref:
        for line in old_ref.splitlines():
            a(line.rstrip())
    else:
        a("            // 寄存器输出用 *_cap（上沿采样值）；组合输出用当前输入。")
        for p in outputs:
            a("            // TODO: exp_%s = ...;  例如: exp_sum = {1'b0, a_cap} + {1'b0, b_cap};" % p["name"])
            a("            exp_%s = %d'b0;" % (p["name"], p["width"]))
    a("        end")
    a("    endtask")
    a("")
    a("    // ---- 输出比对 ----")
    a("    task check_outputs;")
    a("        begin")
    a("            checks = checks + 1;")
    for p in outputs:
        n = p["name"]
        a("            if (%s !== exp_%s) begin" % (n, n))
        a("                errors = errors + 1;")
        a("                if (errors <= ERR_PRINT_MAX)")
        a("                    $display(\"FAIL@%%0t: %s got=%%h exp=%%h\", $time, %s, exp_%s);" % (n, n, n))
        a("            end")
    a("        end")
    a("    endtask")
    a("")
    a("    // ---- 主流程：复位 -> 随机激励 -> 统计 ----")
    a("    integer i;")
    a("    initial begin")
    a("        errors = 0; checks = 0;")
    for p in inputs:
        a("        %s = %d'b0;" % (p["name"], p["width"]))
        a("        %s_cap = %d'b0;" % (p["name"], p["width"]))
    if seed is not None:
        a("        seed = %d;" % seed)
    a("        $display(\"=== TB start: %s, CYCLES=%%0d ===\", CYCLES);" % mod)
    a("        do_reset;")
    a("")
    a("        // ==== DIRECTED_BEGIN ====")
    if old_directed is None:
        a("        // 定向边界激励写在这里（重新生成时保留）；例如：")
        a("        // @(posedge clk); a <= 8'h12; b <= 8'h34;")
        a("        // @(posedge clk); a <= 8'h00; b <= 8'hff;")
        a("        // @(negedge clk); reference_model; check_outputs;  // 检查上一拍")
        a("        // 每个 negedge 都要调用 reference_model/check_outputs，不能只在部分拍检查。")
    elif old_directed:
        for line in old_directed.splitlines():
            a(line)
    a("        // ==== DIRECTED_END ====")
    a("")
    a("        for (i = 0; i < CYCLES; i = i + 1) begin")
    a("            @(posedge %s);            // DUT 在本沿采样（读到上一拍驱动值）" % clk)
    a("            // 上沿对齐驱动（NBA 零延时），下一拍被 DUT 采样")
    for p in inputs:
        w = p["width"]
        prob = p.get("prob")
        if prob is not None and w == 1:
            a("            %s <= (($random(seed) & 32'h7fffffff) %% 100) < %d;" % (p["name"], round(prob * 100)))
        else:
            a("            %s <= $random(seed);" % p["name"])
    a("            @(negedge %s);            // 半拍后 DUT 输出稳定" % clk)
    a("            reference_model;          // 寄存器输出用 *_cap；组合输出用当前输入")
    a("            check_outputs;")
    a("        end")
    a("")
    a("        $display(\"==================================================\");")
    a("        $display(\"stats: checks=%0d errors=%0d\", checks, errors);")
    a("        if (errors > ERR_PRINT_MAX)")
    a("            $display(\"  (first %0d detailed errors shown, total %0d)\", ERR_PRINT_MAX, errors);")
    a("        if (errors == 0) begin")
    a("            $display(\"RESULT: PASS\");")
    a("            $finish;")
    a("        end else begin")
    a("            $display(\"RESULT: FAIL (%0d errors)\", errors);")
    a("            $fatal(1, \"TEST FAILED: %0d error(s) found\", errors);")
    a("        end")
    a("    end")
    a("")
    a("endmodule")
    a("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L), encoding="utf-8")
    return out_path


def main():
    global WORKSPACE, TB_DIR
    ap = argparse.ArgumentParser(description="生成自检测试台骨架（rtl-closed-loop 技能）")
    ap.add_argument("-w", "--workspace", type=Path, default=Path.cwd(), help="工作区根目录（默认当前目录）")
    ap.add_argument("json", type=Path, help="接口描述 JSON")
    ap.add_argument("-o", "--out", type=Path, default=None, help="输出路径（默认 tb/tb_<module>.v）")
    args = ap.parse_args()
    WORKSPACE = args.workspace
    TB_DIR = WORKSPACE / "tb"
    out = gen(args.json, args.out)
    print("generated: %s" % out)


if __name__ == "__main__":
    main()