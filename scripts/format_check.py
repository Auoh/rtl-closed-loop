#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rtl-closed-loop coding-style checker / fixer (rules: references/coding_style.md).

Usage:
  python format_check.py -f <rtl.v>                     check only; exit 0=OK, 1=violations
  python format_check.py -f <rtl.v> --report <out.md>   check + write markdown report
  python format_check.py --fix -f <rtl.v>               apply safe fixes (R5 input wire,
                                                        R7 hold-else), then check again
"""
import argparse
import io
import re
import sys
from datetime import datetime


# rule id -> (name, coding_style.md section, suggestion)
RULE_ADVICE = {
    'R1': ('end 单独一行，else 独立起行', 6,
           '把 end 与下一个 else 拆开：end 单独一行，else begin 与条件写在同一行。'),
    'R2': ('信号定义集中在模块头部', 3,
           '把所有 localparam/reg/wire 声明集中到端口列表之后、逻辑之前；localparam 区块放最前。'),
    'R3': ('低电平复位条件写全', 4,
           '把 !rst_n 改为 rst_n == 1\'b0（禁止省略写法，避免低/高电平复位混淆）。'),
    'R4': ('case 必须有显式 default', 7,
           '每个 case 补 default 分支：组合逻辑 default 显式赋值；时序保持写自赋值，禁止 default: ;。'),
    'R5': ('input 端口不带类型关键字', 3,
           '把 input wire 改为 input（input 默认就是 wire；output 保留显式 output wire）。'),
    'R6': ('不使用 function', 8,
           '把 function 改写为 wire + assign 组合逻辑表达式。'),
    'R7': ('保持分支写 else;', 5,
           '信号保持的最后一个 else 写 else;，不要用 begin/end 包空语句。'),
    'R8': ('一个 always 块只驱动一个信号', 2,
           '把同一 always 块内的多信号赋值拆成多个 always 块，每块只驱动一个 reg。'),
}


def load(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read()


def apply_fix(s):
    # R5: input ports carry no type keyword
    s = re.sub(r'(?m)^(\s*)input\s+wire\b', r'\1input', s)
    # R7: hold else "else begin ; <comment>" -> "else;  <comment>"
    s = re.sub(r'(?m)^(\s*)else begin\n\1\s*;\s*(//[^\n]*)\n\1end\n',
               r'\1else;  \2\n', s)
    s = re.sub(r'(?m)^(\s*)else begin\n\1\s*;\n\1end\n',
               r'\1else;\n', s)
    return s


def check(s2, lines):
    errs = []

    def err(ln, rule, msg):
        errs.append((ln, rule, msg))

    # R3: low-active reset written fully
    for m in re.finditer(r'!rst_n\b', s2):
        err(s2[:m.start()].count('\n') + 1, 'R3', '使用 "rst_n == 1\'b0"，禁止 "!rst_n"')
    # R5: input ports carry no type keyword
    for m in re.finditer(r'input\s+wire\b', s2):
        err(s2[:m.start()].count('\n') + 1, 'R5', '"input wire" 应改为 "input"（input 默认就是 wire）')
    # R1: end must be alone; else starts its own line
    for i, l in enumerate(lines, 1):
        if re.match(r'^\s*end\s+else\b', l):
            err(i, 'R1', 'end 必须单独一行；else 独立起行')
    # R6: no function
    for m in re.finditer(r'\bfunction\b', s2):
        err(s2[:m.start()].count('\n') + 1, 'R6', '禁止使用 function；改用 wire + assign')
    # R4: every case has default; default writes the signal explicitly
    ncase = len(re.findall(r'\bcase\s*\(', s2))
    ndef = len(re.findall(r'\bdefault\s*:', s2))
    if ncase != ndef:
        err(0, 'R4', '共 %d 个 case 但只有 %d 个 default（每个 case 都必须写 default）' % (ncase, ndef))
    for m in re.finditer(r'\bdefault\s*:\s*(;|begin)\b', s2):
        seg = s2[m.start():m.start() + 200]
        if re.match(r'\bdefault\s*:\s*;', seg) or re.match(r'\bdefault\s*:\s*begin\s*\n\s*;', seg):
            err(s2[:m.start()].count('\n') + 1, 'R4',
                'default 必须显式对信号赋值（保持 -> 写自赋值），禁止空语句')
    # R7: hold else written as "else ;" (no begin/end)
    for m in re.finditer(r'else\s+begin\s*\n\s*;\s*\n', s2):
        err(s2[:m.start()].count('\n') + 1, 'R7', '保持分支应写 "else ;"，不要用 begin/end 包空语句')
    # R8: one always block per signal
    i = 0
    while True:
        mm = re.search(r'\balways\b', s2[i:])
        if not mm:
            break
        start = i + mm.start()
        rest = s2[start:]
        bb = rest.find('begin')
        if bb == -1:
            break
        depth = 0
        j = bb
        while j < len(rest):
            if rest[j:j + 5] == 'begin':
                depth += 1
                j += 5
            elif rest[j:j + 3] == 'end':
                depth -= 1
                j += 3
                if depth == 0:
                    break
            else:
                j += 1
        body = rest[bb:j]
        lhs = set()
        for lm in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*<=\s*(?!=)', body):
            lhs.add(lm.group(1))
        for lm in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?!=)', body):
            lhs.add(lm.group(1))
        if len(lhs) > 1:
            err(s2[:start].count('\n') + 1, 'R8',
                '一个 always 块只允许对一个信号赋值，当前驱动了 %s' % ', '.join(sorted(lhs)))
        i = start + 1
    # R2: per-module declarations at top
    for mi, mm in enumerate(re.finditer(r'^\s*module\s+\w+', s2, re.M)):
        mend = s2.find('endmodule', mm.start())
        body = s2[mm.start():mend]
        cand = [x.start() for x in re.finditer(r'\balways\b|\bassign\b', body)]
        if not cand:
            continue
        decls = re.findall(r'^\s*(?:reg|wire|localparam)\s+(?!\w+\s*[=:])',
                           body[min(cand):], re.M)
        if decls:
            err(s2[:mm.start() + min(cand)].count('\n') + 1, 'R2',
                '信号声明必须集中在模块头部，逻辑段之后还有 %d 处声明' % len(decls))
    return errs


def esc(t):
    return t.replace('|', '\\|').replace('\n', ' ')


def write_report(fname, out, errs):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    used = {r for _, r, _ in errs}
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# RTL 编码规范检查报告\n\n')
        f.write('- 检查文件: `%s`\n' % fname)
        f.write('- 检查时间: %s\n' % now)
        f.write('- 检查脚本: `scripts/format_check.py`（规则依据 `references/coding_style.md`）\n')
        f.write('- 结论: **%s**\n\n' % ('PASS（未发现可自动检测的违例）'
                                        if not errs else 'FAIL（%d 处违例）' % len(errs)))
        if errs:
            f.write('## 违例明细与修改建议\n\n')
            f.write('| # | 行号 | 规则 | 问题 | 修改建议 |\n')
            f.write('|---|------|------|------|----------|\n')
            for i, (ln, rule, msg) in enumerate(errs, 1):
                adv = RULE_ADVICE.get(rule, ('', 0, '参照 coding_style.md 对应条目'))[2]
                f.write('| %d | %d | %s | %s | %s |\n' % (i, ln, rule, esc(msg), esc(adv)))
            f.write('\n## 涉及规则一览\n\n')
            for rule in sorted(RULE_ADVICE):
                name, sec, adv = RULE_ADVICE[rule]
                mark = '**（本报告命中）**' if rule in used else ''
                f.write('- %s %s：%s（coding_style.md 第 %d 节）%s\n'
                        % (rule, name, adv, sec, mark))
        else:
            f.write('未发现可自动检测的规范违例；建议人工复核三段式状态机划分'
                    '（coding_style.md 第 1 节）与 if/else 分支完整性（第 5 节）。\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-f', '--file', required=True, help='RTL file to check/fix')
    ap.add_argument('--fix', action='store_true', help='apply safe rule fixes (R5/R7) first')
    ap.add_argument('--report', metavar='OUT.md', help='write markdown check report')
    args = ap.parse_args()

    s = load(args.file)
    if args.fix:
        fixed = apply_fix(s)
        if fixed != s:
            io.open(args.file, 'w', encoding='utf-8', newline='\n').write(fixed)
            s = fixed
    s2 = re.sub(r'//[^\n]*', '', s)
    s2 = re.sub(r'/\*.*?\*/', '', s2, flags=re.S)
    lines = s2.split('\n')
    errs = sorted(set(check(s2, lines)))
    if args.report:
        write_report(args.file, args.report, errs)
    if errs:
        for ln, rule, msg in errs:
            print('%s:%d: [%s] %s' % (args.file, ln, rule, msg))
        print('FORMAT: FAIL (%d issue(s))' % len(errs))
        sys.exit(1)
    print('%s: FORMAT OK' % args.file)


if __name__ == '__main__':
    main()