#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rtlq - lightweight RTL quality / PPA closed-loop CLI.

Commands:
  doctor     check iverilog/GTKWave plus optional quality-lite (Yosys/slang/sby)
  lint       style rules (format_check.py) + slang lint + Yosys structural checks
  sim        compile & run a self-checking testbench (optional VCD/FST)
  synth      Yosys generic synthesis, cell/FF/depth metrics and PPA budget
  lec        Yosys equivalence check (gold RTL vs synthesized netlist)
  formal     SymbiYosys property proof using formal/<top>.sby
  all        lint -> sim -> negative sim -> synth -> lec -> formal + summary
             (writes report/history/<top>/<timestamp>.json)
  compare    compare the latest two history snapshots, or --baseline <file>
  report     re-render report/summary.md from report/quality.json
  manifest   hash the bundled quality-lite toolchain into tools/manifest.json

The CLI is intentionally dependency-free (Python standard library only).  It is
designed for Windows + Git Bash / PowerShell, but uses pathlib so Linux works too.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = "1.1.6"
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY: Dict[str, Any] = {
    "lint": {
        "strict_warnings": False,
        "yosys_structural": True,
    },
    "sim": {
        "grammar": "2012",
        "timeout_s": 120,
        "fst": False,
    },
    "synth": {
        "timeout_s": 300,
        "liberty": None,
    },
    "lec": {
        "timeout_s": 300,
        # Empty by default: silently excluding a real mismatch hides bugs.
        # Projects may opt in per module via config/quality_policy.json, and
        # lec prints a hint when the only unproven signal is state_next.
        "blacklist": {"default": []},
        "multiclock": True,
    },
    "formal": {
        "timeout_s": 180,
        "python": "auto",
    },
    "all": {
        "negative": True,
        "formal": True,
        "lec": True,
        "synth": True,
        "fail_on_ppa": True,
    },
}
DEFAULT_BUDGET: Dict[str, Any] = {"version": 1, "tops": {}}
STAGE_ORDER = ("lint", "sim", "negative", "synth", "lec", "formal")
# Lower rank is better.  SKIP shares WARN's rank: losing a previously-passing
# stage is still a regression, but SKIP -> PASS counts as an improvement.
_STATUS_RANK = {"PASS": 0, "WARN": 1, "SKIP": 1, "FAIL": 2, "ERROR": 3}


class RtlqError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _posix(p: Path) -> str:
    # Yosys/ABC on Windows accept D:/... but not /d/... from Git Bash.
    return p.resolve().as_posix()


def _q(p: Path) -> str:
    s = _posix(p)
    return '"' + s.replace('"', '\\"') + '"'


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")


def _load_json(p: Path, default: Any) -> Any:
    if not p.is_file():
        return default
    try:
        return json.loads(_read_text(p))
    except Exception as exc:
        raise RtlqError("JSON 解析失败 %s: %s" % (p, exc))


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _status_rank(s: str) -> int:
    return {"SKIP": 0, "PASS": 1, "WARN": 2, "FAIL": 3, "ERROR": 4}.get(s, 4)


def _worst(statuses: Iterable[str]) -> str:
    vals = [s for s in statuses if s and s != "SKIP"]
    if not vals:
        return "SKIP"
    return max(vals, key=_status_rank)


def _bool_status(ok: bool, fail: str = "FAIL") -> str:
    return "PASS" if ok else fail


# ---------------------------------------------------------------------------
# process execution
# ---------------------------------------------------------------------------

class RunResult:
    def __init__(self, cmd: Sequence[str], rc: int, out: str, seconds: float,
                 timed_out: bool = False, log: Optional[Path] = None):
        self.cmd = [str(c) for c in cmd]
        self.rc = rc
        self.out = out
        self.seconds = seconds
        self.timed_out = timed_out
        self.log = log

    @property
    def ok(self) -> bool:
        return self.rc == 0 and not self.timed_out

    def tail(self, n: int = 12) -> str:
        lines = [x for x in self.out.splitlines() if x.strip()]
        return "\n".join(lines[-n:])


def _kill_process_tree(proc: "subprocess.Popen[str]") -> str:
    """Kill a child process and all of its descendants.

    Tools such as sby spawn yosys/abc grandchildren.  Killing only the direct
    child on timeout leaves those processes holding report/formal/<top>, so the
    next run fails in shutil.rmtree with WinError 32.
    """
    if os.name == "nt":
        try:
            r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15)
            if r.returncode == 0:
                return "taskkill /T /F /PID %d" % proc.pid
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return "killpg(%d, SIGKILL)" % proc.pid
        except Exception:
            pass
    try:
        proc.kill()
        return "Popen.kill(%d)" % proc.pid
    except Exception:
        return "kill failed (pid=%d)" % proc.pid


def _run(cmd: Sequence[Any], cwd: Path, timeout: Optional[float],
         log: Optional[Path] = None, extra_env: Optional[Dict[str, str]] = None) -> RunResult:
    cmd_s = [str(c) for c in cmd]
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    t0 = time.time()
    timed_out = False
    out = ""
    rc = 1
    popen_kw: Dict[str, Any] = {}
    if os.name == "nt":
        popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kw["start_new_session"] = True
    proc: Optional["subprocess.Popen[str]"] = None
    try:
        proc = subprocess.Popen(
            cmd_s, cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", **popen_kw,
        )
        try:
            out, _ = proc.communicate(timeout=timeout)
            rc = int(proc.returncode)
        except subprocess.TimeoutExpired:
            timed_out = True
            rc = 124
            how = _kill_process_tree(proc)
            try:
                out, _ = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    out, _ = proc.communicate(timeout=5)
                except Exception:
                    out = ""
            out = out or ""
            out += "\n[rtlq] TIMEOUT after %s s; killed process tree: %s\n" % (timeout, how)
    except FileNotFoundError as exc:
        rc = 127
        out = "[rtlq] command not found: %s\n%s\n" % (cmd_s[0], exc)
    except Exception as exc:  # noqa: BLE001 - report tool failures, don't crash
        rc = 1
        out = "[rtlq] execution error: %s\n" % exc
        if proc is not None and proc.poll() is None:
            _kill_process_tree(proc)
    seconds = time.time() - t0
    if log is not None:
        try:
            _write_text(log, "$ " + " ".join(shlex.quote(x) for x in cmd_s) +
                        "\n\n" + out + "\n[rtlq] rc=%d elapsed=%.3fs\n" % (rc, seconds))
        except Exception:
            pass
    return RunResult(cmd_s, rc, out, seconds, timed_out, log)


# ---------------------------------------------------------------------------
# tool discovery
# ---------------------------------------------------------------------------

def _which(name: str) -> Optional[Path]:
    p = shutil.which(name)
    return Path(p) if p else None


def _first(*paths: Optional[Path]) -> Optional[Path]:
    for p in paths:
        if p and p.is_file():
            return p
    return None


def _cache_roots() -> List[Path]:
    out: List[Path] = []
    env = os.environ.get("RTL_TOOLCHAIN")
    if env:
        out.append(Path(env))
    home = Path.home()
    out.append(home / ".codex" / "rtl-toolchain")
    for root in ("C:/rtl-toolchain", "D:/rtl-toolchain", "E:/rtl-toolchain", "F:/rtl-toolchain"):
        out.append(Path(root))
    return out


# setup.ps1 -Install puts iverilog either directly in the cache root
# (<root>/bin, <root>/gtkwave/bin) or in a named subdirectory
# (<root>/iverilog/bin, <root>/iverilog/gtkwave/bin).  Support both layouts.
_IVERILOG_SUBDIRS = (
    Path("bin"),
    Path("gtkwave") / "bin",
    Path("iverilog") / "bin",
    Path("iverilog") / "gtkwave" / "bin",
)
_GTKWAVE_SUBDIRS = (
    Path("gtkwave") / "bin",
    Path("iverilog") / "gtkwave" / "bin",
)


def _cached_iverilog_pair(reject: Optional[Path]) -> Optional[Tuple[Path, Path]]:
    """Return (iverilog, vvp) from the cache, skipping the *reject* executable.

    A rejected tool is the one whose path contains spaces and whose internal
    ivlpp subprocess fails.  The pair must live in the same directory so the
    two binaries belong to the same installation.
    """
    iv_name, vvp_name = _exe_name("iverilog"), _exe_name("vvp")
    reject_key = ""
    if reject is not None:
        try:
            reject_key = str(reject.resolve()).lower()
        except OSError:
            reject_key = str(reject).lower()
    seen = set()
    for root in _cache_roots():
        for rel in _IVERILOG_SUBDIRS:
            iv = root / rel / iv_name
            vv = root / rel / vvp_name
            if not (iv.is_file() and vv.is_file()):
                continue
            try:
                key = str(iv.resolve()).lower()
            except OSError:
                key = str(iv).lower()
            if key in seen or key == reject_key:
                continue
            seen.add(key)
            return iv, vv
    return None


# iverilog's driver launches ivlpp/ivl with an unquoted argv[0]; an install
# under "D:\01 software\..." therefore fails as a shell parse error.  Windows
# reports it as a localized "not recognized" message, so match both the
# English text and the leading quoted drive path (locale-independent, also
# survives UTF-8 decoding of GBK console output).
_CMD_PARSE_ERROR_RE = re.compile(
    r"(is not recognized as an internal or external command"
    r"|不是内部或外部命令"
    r"|command not found"
    r"|^\s*'[A-Za-z]:\\[^'\r\n]*'\s)",
    re.IGNORECASE | re.MULTILINE,
)


def _looks_like_cmd_parse_error(text: str) -> bool:
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    return bool(first) and bool(_CMD_PARSE_ERROR_RE.search(first))


def _quality_roots(ws: Path) -> List[Path]:
    out: List[Path] = []
    env = os.environ.get("RTL_QUALITY_LITE")
    if env:
        out.append(Path(env))
    out.extend([
        ws / "tools" / "quality-lite",
        SKILL_ROOT / "tools" / "quality-lite",
    ])
    # Offline setup installs quality-lite next to the iverilog cache:
    #   .../rtl-toolchain/iverilog  +  .../rtl-toolchain/quality-lite
    for root in _cache_roots():
        out.append(root.parent / "quality-lite")
        out.append(root / "quality-lite")
    for root in ("C:/rtl-toolchain", "D:/rtl-toolchain",
                 "E:/rtl-toolchain", "F:/rtl-toolchain"):
        out.append(Path(root) / "quality-lite")
    return out


def _exe_name(name: str) -> str:
    if os.name == "nt" and not name.lower().endswith((".exe", ".py", ".bat", ".cmd")):
        return name + ".exe"
    return name


class Tools:
    def __init__(self, ws: Path):
        self.ws = ws
        self.quality_root = next((p for p in _quality_roots(ws) if p.is_dir()), None)
        self.iverilog = self._find_iverilog("iverilog")
        self.vvp = self._find_iverilog("vvp")
        self.gtkwave = self._find_gtkwave("gtkwave")
        self.vcd2fst = self._find_gtkwave("vcd2fst")
        self.yosys = self._find_quality("yosys", "bin", "yosys")
        self.yosys_abc = self._find_quality("yosys", "bin", "yosys-abc")
        self.slang = self._find_quality("slang", "bin", "slang")
        self.sby_py = None
        if self.quality_root:
            for rel in (Path("sby") / "sbysrc" / "sby.py",
                        Path("sby") / "sby.py"):
                p = self.quality_root / rel
                if p.is_file():
                    self.sby_py = p
                    break
        self.verible_format = self._find_verible("verible-verilog-format")
        self.verible_lint = self._find_verible("verible-verilog-lint")

    def _find_iverilog(self, name: str) -> Optional[Path]:
        rels = [Path("tools") / "iverilog" / "bin" / _exe_name(name),
                Path("tools") / "iverilog" / "gtkwave" / "bin" / _exe_name(name)]
        for rel in rels:
            p = self.ws / rel
            if p.is_file():
                return p
        for root in _cache_roots():
            for rel in _IVERILOG_SUBDIRS:
                p = root / rel / _exe_name(name)
                if p.is_file():
                    return p
        return _which(_exe_name(name))

    def _find_gtkwave(self, name: str) -> Optional[Path]:
        rels = [Path("tools") / "iverilog" / "gtkwave" / "bin" / _exe_name(name)]
        for rel in rels:
            p = self.ws / rel
            if p.is_file():
                return p
        for root in _cache_roots():
            for rel in _GTKWAVE_SUBDIRS:
                p = root / rel / _exe_name(name)
                if p.is_file():
                    return p
        return _which(_exe_name(name))

    def _find_quality(self, package: str, sub: str, exe: str) -> Optional[Path]:
        for root in _quality_roots(self.ws):
            for name in (_exe_name(exe), exe):
                p = root / package / sub / name
                if p.is_file():
                    return p
        return _which(_exe_name(exe))

    def _find_verible(self, name: str) -> Optional[Path]:
        for root in _cache_roots():
            for rel in (Path("verible") / "bin" / _exe_name(name),
                        Path("bin") / _exe_name(name)):
                p = root / rel
                if p.is_file():
                    return p
            # Offline setup installs verible next to the iverilog root:
            #   .../rtl-toolchain/iverilog  +  .../rtl-toolchain/verible
            p = root.parent / "verible" / "bin" / _exe_name(name)
            if p.is_file():
                return p
        p = self.ws / "tools" / "verible" / "bin" / _exe_name(name)
        return p if p.is_file() else _which(_exe_name(name))

    @property
    def core_ok(self) -> bool:
        return bool(self.iverilog and self.vvp)

    @property
    def quality_ok(self) -> bool:
        return bool(self.yosys and self.slang and self.sby_py)


# ---------------------------------------------------------------------------
# context / report helpers
# ---------------------------------------------------------------------------

class Context:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.ws = Path(args.workdir).resolve()
        if not self.ws.is_dir():
            raise RtlqError("工作区不存在: %s" % self.ws)
        self.report_dir = Path(args.report_dir).resolve() if args.report_dir else self.ws / "report"
        self.logs = self.report_dir / "logs"
        self.tools = Tools(self.ws)
        policy_path = Path(args.policy) if args.policy else self.ws / "config" / "quality_policy.json"
        self.policy = _deep_merge(DEFAULT_POLICY, _load_json(policy_path, {}))
        budget_path = Path(args.budget_file) if args.budget_file else self.ws / "config" / "ppa_budget.json"
        self.budget = _deep_merge(DEFAULT_BUDGET, _load_json(budget_path, {}))
        self.top = args.top
        self._files: Optional[List[Path]] = None
        self.start = time.time()

    def log_path(self, name: str) -> Path:
        return self.logs / (name + ".log")

    def stage_timeout(self, stage: str) -> Optional[int]:
        if getattr(self.args, "timeout", None) is not None:
            return int(self.args.timeout)
        v = (self.policy.get(stage) or {}).get("timeout_s")
        return int(v) if v else None

    def infer_top(self, required: bool = False) -> Optional[str]:
        if self.top:
            return self.top
        tbs = sorted((self.ws / "tb").glob("tb_*.v")) + sorted((self.ws / "tb").glob("tb_*.sv"))
        if len(tbs) == 1:
            self.top = tbs[0].stem[3:]
            return self.top
        rtls = sorted((self.ws / "rtl").glob("*.v")) + sorted((self.ws / "rtl").glob("*.sv"))
        if len(rtls) == 1:
            self.top = rtls[0].stem
            return self.top
        if required:
            names = ", ".join(p.stem for p in rtls) or "(none)"
            raise RtlqError("无法推断 top，请用 --top 指定；rtl/: %s" % names)
        return None

    def rtl_files(self, explicit: Optional[List[str]] = None) -> List[Path]:
        if explicit:
            out: List[Path] = []
            for x in explicit:
                p = Path(x)
                if not p.is_absolute():
                    p = self.ws / p
                if not p.is_file():
                    raise RtlqError("RTL 文件不存在: %s" % p)
                out.append(p.resolve())
            return _dedupe(out)
        if self._files is None:
            files = sorted((self.ws / "rtl").glob("*.v")) + sorted((self.ws / "rtl").glob("*.sv"))
            self._files = [p.resolve() for p in files if p.is_file()]
        return list(self._files)

    def tb_file(self, explicit: Optional[str] = None) -> Path:
        if explicit:
            p = Path(explicit)
            if not p.is_absolute():
                p = self.ws / p
            if not p.is_file():
                raise RtlqError("TB 文件不存在: %s" % p)
            return p.resolve()
        top = self.infer_top(required=True)
        cand = self.ws / "tb" / ("tb_%s.v" % top)
        if cand.is_file():
            return cand
        cand_sv = self.ws / "tb" / ("tb_%s.sv" % top)
        if cand_sv.is_file():
            return cand_sv
        cands = sorted((self.ws / "tb").glob("*%s*.v" % top))
        if len(cands) == 1:
            return cands[0].resolve()
        raise RtlqError("找不到 TB: tb/tb_%s.v（或 --tb 指定）" % top)

    def top_name(self, tb: Path) -> str:
        explicit = getattr(self.args, "tb_top", None)
        if explicit:
            return explicit
        m = re.search(r"(?m)^\s*module\s+([A-Za-z_]\w*)", _read_text(tb))
        return m.group(1) if m else "tb_%s" % self.infer_top(required=True)

    def write_stage(self, name: str, result: Dict[str, Any]) -> Path:
        p = self.report_dir / (name + ".json")
        _write_json(p, result)
        return p

    def versions(self) -> Dict[str, Optional[str]]:
        return {
            "iverilog": _version_of(self.tools.iverilog, ["-V"]),
            "yosys": _version_of(self.tools.yosys, ["-V"]),
            "slang": _version_of(self.tools.slang, ["--version"]),
            "verible": _version_of(self.tools.verible_format, ["--version"]),
            "python": sys.version.split()[0],
        }


def _dedupe(paths: Sequence[Path]) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for p in paths:
        key = str(p.resolve()).lower() if os.name == "nt" else str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p.resolve())
    return out


def _version_of(exe: Optional[Path], args: Sequence[str]) -> Optional[str]:
    if not exe:
        return None
    if exe.suffix.lower() == ".py":
        return None
    r = _run([exe] + list(args), exe.parent, 10)
    first = next((x.strip() for x in r.out.splitlines() if x.strip()), "")
    return first or None


def _json_from_tee(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    text = _read_text(path)
    idx = text.find("{")
    while idx >= 0:
        try:
            return json.JSONDecoder().raw_decode(text, idx)[0]
        except Exception:
            idx = text.find("{", idx + 1)
    return None


def _ff_count(stat: Any) -> int:
    if not isinstance(stat, dict):
        return 0
    by = ((stat.get("design") or {}).get("num_cells_by_type") or {})
    return sum(int(v) for k, v in by.items() if re.search(r"dff", k, re.I))


def _ltp_depth(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    text = _read_text(path)
    vals = [int(x) for x in re.findall(r"length\s*=\s*(\d+)", text)]
    return vals[-1] if vals else None


def _status_line(status: str, msg: str) -> str:
    return "[%s] %s" % (status, msg)


# ---------------------------------------------------------------------------
# doctor / manifest
# ---------------------------------------------------------------------------

def _doctor_table(ctx: Context) -> Tuple[List[Dict[str, Any]], int]:
    t = ctx.tools
    rows: List[Dict[str, Any]] = []
    specs = [
        ("iverilog", t.iverilog, "core", _version_of(t.iverilog, ["-V"])),
        ("vvp", t.vvp, "core", _version_of(t.vvp, ["-V"])),
        ("python", Path(sys.executable), "core", sys.version.split()[0]),
        ("yosys", t.yosys, "quality", _version_of(t.yosys, ["-V"])),
        ("yosys-abc", t.yosys_abc, "quality", None),
        ("slang", t.slang, "quality", _version_of(t.slang, ["--version"])),
        ("sby", t.sby_py, "quality", _sby_version(t)),
        ("gtkwave", t.gtkwave, "optional", _version_of(t.gtkwave, ["--version"])),
        ("vcd2fst", t.vcd2fst, "optional", None),
        ("verible-format", t.verible_format, "optional", _version_of(t.verible_format, ["--version"])),
        ("verible-lint", t.verible_lint, "optional", _version_of(t.verible_lint, ["--version"])),
    ]
    for name, path, kind, ver in specs:
        rows.append({
            "name": name,
            "kind": kind,
            "path": str(path) if path else None,
            "version": ver,
            "ok": bool(path),
        })
    core_ok = t.core_ok
    quality_ok = t.quality_ok
    optional_ok = all(r["ok"] for r in rows if r["kind"] == "optional")
    rc = 0 if (core_ok and quality_ok) else 1
    if getattr(ctx.args, "strict", False) and not optional_ok:
        rc = 1
    return rows, rc


def _sby_version(t: Tools) -> Optional[str]:
    if not t.sby_py:
        return None
    for p in (t.sby_py.parent.parent / "VERSION", t.sby_py.parent / "VERSION"):
        if p.is_file():
            return _read_text(p).strip()
    return None


def _doctor_warnings(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Environment hazards that do not fail doctor but break later stages."""
    warnings: List[Dict[str, Any]] = []
    iv = next((r for r in rows if r["name"] == "iverilog" and r.get("path")), None)
    if iv and " " in iv["path"]:
        warnings.append({
            "kind": "path_space",
            "tool": "iverilog",
            "path": iv["path"],
            "message": "iverilog 位于含空格路径，内部子进程（ivlpp）可能解析失败: %s" % iv["path"],
            "hint": "运行 scripts/setup.ps1 -Install 部署到无空格缓存根（如 C:\\rtl-toolchain）；sim 失败时会自动重试缓存版本",
        })
    return warnings


def cmd_doctor(ctx: Context, args: argparse.Namespace) -> int:
    rows, rc = _doctor_table(ctx)
    warnings = _doctor_warnings(rows)
    status = "FAIL" if rc != 0 else ("WARN" if warnings else "PASS")
    if ctx.args.json:
        print(json.dumps({
            "command": "doctor", "status": status,
            "quality_root": str(ctx.tools.quality_root) if ctx.tools.quality_root else None,
            "tools": rows, "warnings": warnings,
        }, ensure_ascii=False, indent=2))
        return rc
    print("== rtlq doctor ==")
    print("workspace: %s" % ctx.ws)
    print("quality-lite: %s" % (ctx.tools.quality_root or "(not found)"))
    for r in rows:
        mark = "[OK]  " if r["ok"] else ("[MISS]" if r["kind"] != "optional" else "[OPT] ")
        ver = ("  " + r["version"]) if r["version"] else ""
        print("%s %-16s %s%s" % (mark, r["name"], r["path"] or "-", ver))
    for w in warnings:
        print("[WARN] %s" % w["message"])
        print("       提示: %s" % w["hint"])
    if rc != 0:
        print("== FAIL（缺少核心/质量工具） ==")
    elif warnings:
        print("== WARN（工具可用，但存在环境隐患） ==")
    else:
        print("== PASS ==")
    return rc


def cmd_manifest(ctx: Context, args: argparse.Namespace) -> int:
    root = ctx.tools.quality_root
    if not root:
        raise RtlqError("未找到 quality-lite 目录（tools/quality-lite）")
    rels = [
        Path("yosys/bin/yosys.exe"),
        Path("yosys/bin/yosys-abc.exe"),
        Path("yosys/LICENSE"),
        Path("slang/bin/slang.exe"),
        Path("slang/LICENSE"),
        Path("sby/sbysrc/sby.py"),
        Path("sby/sbysrc/sby_core.py"),
        Path("sby/COPYING"),
        Path("sby/VERSION"),
    ]
    entries = []
    for rel in rels:
        p = root / rel
        if p.is_file():
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            entries.append({"path": rel.as_posix(), "size": p.stat().st_size, "sha256": h.hexdigest()})
    data = {
        "schema_version": 1,
        "name": "rtl-quality-lite",
        "generated_at": _now(),
        "platform": sys.platform,
        "root": str(root),
        "tools": {
            "yosys": _version_of(ctx.tools.yosys, ["-V"]),
            "slang": _version_of(ctx.tools.slang, ["--version"]),
            "sby": _sby_version(ctx.tools),
        },
        "files": entries,
    }
    out = ctx.ws / "tools" / "manifest.json"
    _write_json(out, data)
    print("manifest: %s (%d files)" % (out, len(entries)))
    if ctx.args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

def _load_style_module():
    p = Path(__file__).resolve().parent / "format_check.py"
    spec = importlib.util.spec_from_file_location("rtlq_format_check", str(p))
    if spec is None or spec.loader is None:
        raise RtlqError("无法加载样式检查器: %s" % p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _style_check(files: Sequence[Path]) -> Dict[str, Any]:
    mod = _load_style_module()
    issues = []
    for f in files:
        try:
            s = mod.load(str(f))
        except Exception as exc:
            issues.append({"file": str(f), "line": 0, "rule": "IO", "message": str(exc)})
            continue
        s2 = re.sub(r"//[^\n]*", "", s)
        s2 = re.sub(r"/\*.*?\*/", "", s2, flags=re.S)
        for ln, rule, msg in sorted(set(mod.check(s2, s2.splitlines()))):
            issues.append({"file": str(f), "line": int(ln), "rule": rule, "message": msg})
    return {"status": "FAIL" if issues else "PASS", "issues": issues,
            "files": [str(f) for f in files]}


def _slang_lint(ctx: Context, files: Sequence[Path]) -> Dict[str, Any]:
    slang = ctx.tools.slang
    if not slang:
        return {"status": "SKIP", "reason": "slang not found", "warnings": [], "errors": []}
    incs = _dedupe([ctx.ws / "rtl", ctx.ws / "tb", ctx.ws])
    cmd: List[Any] = [slang, "--lint-only", "--std", "1800-2017",
                      "-Weverything", "-Wno-empty-body", "-Wno-newline-eof"]
    for d in incs:
        if d.is_dir():
            cmd += ["-I", str(d)]
    cmd += [str(f) for f in files]
    r = _run(cmd, ctx.ws, ctx.stage_timeout("lint"), ctx.log_path("lint_slang"))
    warnings = [ln for ln in r.out.splitlines() if re.search(r":\s*warning:", ln)]
    errors = [ln for ln in r.out.splitlines() if re.search(r":\s*error:", ln)]
    if r.timed_out:
        status = "ERROR"
    elif r.rc != 0:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"
    return {"status": status, "rc": r.rc, "seconds": round(r.seconds, 3),
            "warnings": warnings, "errors": errors,
            "log": str(r.log) if r.log else None, "tail": r.tail(20)}


def _yosys_lint(ctx: Context, files: Sequence[Path], top: str) -> Dict[str, Any]:
    y = ctx.tools.yosys
    if not y:
        return {"status": "SKIP", "reason": "yosys not found"}
    lines = ["read_verilog -sv " + " ".join(_q(f) for f in files),
             "hierarchy -check -top " + top,
             "proc", "opt_clean",
             "check -assert",
             "select -assert-none t:$dlatch",
             "stat"]
    r = _yosys(ctx, "lint_%s" % top, lines, ctx.stage_timeout("lint"))
    latch = "Latch inferred" in r.out
    if r.timed_out:
        status = "ERROR"
    elif r.rc != 0:
        status = "FAIL"
    elif latch:
        status = "FAIL"
    else:
        status = "PASS"
    return {"status": status, "rc": r.rc, "seconds": round(r.seconds, 3),
            "latch": latch, "log": str(r.log) if r.log else None, "tail": r.tail(20)}


def _yosys(ctx: Context, name: str, lines: Sequence[str],
           timeout: Optional[float]) -> RunResult:
    y = ctx.tools.yosys
    if not y:
        raise RtlqError("未找到 yosys")
    script = ctx.logs / (name + ".ys")
    _write_text(script, "\n".join(lines) + "\n")
    return _run([y, "-s", str(script)], ctx.ws, timeout, ctx.log_path(name))


def do_lint(ctx: Context, args: argparse.Namespace) -> Dict[str, Any]:
    top = ctx.infer_top(required=False)
    files = ctx.rtl_files(getattr(args, "files", None))
    if not files:
        raise RtlqError("rtl/ 下没有 .v/.sv 文件")
    style = _style_check(files)
    slang = _slang_lint(ctx, files)
    yosys = {"status": "SKIP", "reason": "no top or disabled"}
    if top and (ctx.policy.get("lint") or {}).get("yosys_structural", True):
        yosys = _yosys_lint(ctx, files, top)
    statuses = [style["status"], slang["status"], yosys["status"]]
    status = _worst(statuses)
    if status == "WARN" and (getattr(args, "strict", False) or
                             (ctx.policy.get("lint") or {}).get("strict_warnings")):
        status = "FAIL"
    return {
        "command": "lint", "status": status, "top": top,
        "files": [str(f) for f in files],
        "style": style, "slang": slang, "yosys": yosys,
        "seconds": round(time.time() - ctx.start, 3),
    }


def cmd_lint(ctx: Context, args: argparse.Namespace) -> int:
    result = do_lint(ctx, args)
    ctx.write_stage("lint", result)
    _print_lint(result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("PASS", "WARN") else 1


def _print_lint(r: Dict[str, Any]) -> None:
    s = r["style"]
    print("[%s] lint style: %d issue(s) / %d file(s)" % (s["status"], len(s["issues"]), len(s["files"])))
    for i in s["issues"][:20]:
        print("  %s:%s [%s] %s" % (i["file"], i["line"], i["rule"], i["message"]))
    sl = r["slang"]
    print("[%s] slang: %d warning(s), %d error(s)" %
          (sl["status"], len(sl.get("warnings", [])), len(sl.get("errors", []))))
    for w in sl.get("warnings", [])[:10]:
        print("  " + w)
    y = r["yosys"]
    print("[%s] yosys structural%s" % (y["status"], " (latch!)" if y.get("latch") else ""))
    print("RESULT: %s" % r["status"])


# ---------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------

def _resolve_sim_files(ctx: Context, args: argparse.Namespace, tb: Path) -> List[Path]:
    rtl = ctx.rtl_files(getattr(args, "files", None))
    return _dedupe(list(rtl) + [tb])


def do_sim(ctx: Context, args: argparse.Namespace, bug: Optional[bool] = None) -> Dict[str, Any]:
    top = ctx.infer_top(required=True)
    tb = ctx.tb_file(getattr(args, "tb", None))
    tb_top = ctx.top_name(tb)
    files = _resolve_sim_files(ctx, args, tb)
    if not ctx.tools.iverilog or not ctx.tools.vvp:
        return {"command": "sim", "status": "ERROR", "top": top, "tb": str(tb),
                "reason": "iverilog/vvp not found", "seconds": 0}
    use_bug = bool(getattr(args, "bug", False) if bug is None else bug)
    use_wave = bool(getattr(args, "wave", False))
    grammar = getattr(args, "grammar", None) or (ctx.policy.get("sim") or {}).get("grammar", "2012")
    sim_dir = ctx.ws / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    vvp_out = sim_dir / (top + ("_bug" if use_bug else "") + ("_wave" if use_wave else "") + ".vvp")
    vcd = sim_dir / "wave.vcd"
    if use_wave:
        try:
            vcd.unlink()
        except FileNotFoundError:
            pass
    incs = _dedupe([ctx.ws / "rtl", ctx.ws / "tb", ctx.ws])

    def _compile_cmd(iverilog: Path) -> List[Any]:
        c: List[Any] = [iverilog, "-g" + str(grammar), "-s", tb_top,
                        "-o", str(vvp_out)]
        for d in incs:
            if d.is_dir():
                c += ["-I", str(d)]
        if use_bug:
            c += ["-DINJECT_BUG=1"]
        if use_wave:
            c += ["-DDUMP_WAVE"]
        c += [str(f) for f in files]
        return c

    compile_log = ctx.log_path("sim_compile_%s%s%s" %
                               (top, "_bug" if use_bug else "",
                                "_wave" if use_wave else ""))
    cr = _run(_compile_cmd(ctx.tools.iverilog), ctx.ws, ctx.stage_timeout("sim"), compile_log)
    tool_retry: Optional[Dict[str, Any]] = None
    parse_error = (cr.rc != 0 and not cr.timed_out and
                   _looks_like_cmd_parse_error(cr.out))
    if parse_error:
        # iverilog at "D:\01 software\..." splits its own child command line.
        # Retry once with a cached installation on a space-free path.
        pair = _cached_iverilog_pair(ctx.tools.iverilog)
        if pair:
            iv2, vvp2 = pair
            original_iv = ctx.tools.iverilog
            first_log, first_rc = compile_log, cr.rc
            compile_log = ctx.log_path(
                "sim_compile_%s%s%s_retry" % (top, "_bug" if use_bug else "",
                                              "_wave" if use_wave else ""))
            cr = _run(_compile_cmd(iv2), ctx.ws, ctx.stage_timeout("sim"), compile_log)
            ctx.tools.iverilog, ctx.tools.vvp = iv2, vvp2
            tool_retry = {
                "reason": "command parse error",
                "from": str(original_iv),
                "to": str(iv2),
                "first_rc": first_rc,
                "first_log": str(first_log),
                "retry_rc": cr.rc,
                "retry_log": str(compile_log),
            }
    if cr.rc != 0 or cr.timed_out:
        result = {
            "command": "sim", "status": "ERROR" if cr.timed_out else "FAIL",
            "top": top, "tb": str(tb), "tb_top": tb_top,
            "bug": use_bug, "compile_rc": cr.rc,
            "compile_seconds": round(cr.seconds, 3),
            "compile_log": str(compile_log), "tail": cr.tail(30),
            "iverilog": str(ctx.tools.iverilog),
            "seconds": round(cr.seconds, 3),
        }
        if tool_retry:
            result["tool_retry"] = tool_retry
        elif parse_error:
            result["hint"] = ("iverilog 位于含空格路径，内部子进程解析失败；"
                              "请运行 scripts/setup.ps1 -Install 部署到无空格缓存根")
        return result
    run_log = ctx.log_path("sim_%s%s%s" %
                           (top, "_bug" if use_bug else "",
                            "_wave" if use_wave else ""))
    rr = _run([ctx.tools.vvp, str(vvp_out)], sim_dir, ctx.stage_timeout("sim"), run_log)
    text = rr.out
    if "RESULT: PASS" in text:
        status = "PASS"
    elif "RESULT: FAIL" in text:
        status = "FAIL"
    elif rr.rc != 0:
        status = "FAIL"
    else:
        status = "ERROR"
    wave_info: Dict[str, Any] = {"vcd": str(vcd) if vcd.is_file() else None}
    if use_wave:
        if not vcd.is_file() or vcd.stat().st_size == 0:
            status = "FAIL"
            wave_info["error"] = "DUMP_WAVE 已定义，但未生成非空 wave.vcd"
        else:
            wave_info["size"] = vcd.stat().st_size
            want_fst = bool(getattr(args, "fst", False) or (ctx.policy.get("sim") or {}).get("fst"))
            if want_fst and ctx.tools.vcd2fst:
                fst = sim_dir / "wave.fst"
                fr = _run([ctx.tools.vcd2fst, "-v", str(vcd), "-f", str(fst)],
                          sim_dir, ctx.stage_timeout("sim"), ctx.log_path("vcd2fst_%s" % top))
                wave_info["fst"] = str(fst) if fst.is_file() else None
                wave_info["fst_rc"] = fr.rc
                if fr.rc != 0:
                    status = "FAIL"
    m = re.search(r"stats:\s*(.+)", text)
    stats = m.group(1).strip() if m else None
    if not stats:
        # 兼容只打印中文“错误数”的 TB
        m = re.search(r"错误数\s*[:：]\s*(\d+)", text)
        if m:
            stats = "errors=%s" % m.group(1)
    result = {
        "command": "sim", "status": status, "top": top, "tb": str(tb),
        "tb_top": tb_top, "bug": use_bug, "grammar": str(grammar),
        "compile_rc": cr.rc, "vvp_rc": rr.rc,
        "compile_seconds": round(cr.seconds, 3),
        "run_seconds": round(rr.seconds, 3),
        "stats": stats, "wave": wave_info,
        "iverilog": str(ctx.tools.iverilog),
        "compile_log": str(compile_log), "run_log": str(run_log),
        "tail": rr.tail(20), "seconds": round(cr.seconds + rr.seconds, 3),
    }
    if tool_retry:
        result["tool_retry"] = tool_retry
    return result


def cmd_sim(ctx: Context, args: argparse.Namespace) -> int:
    result = do_sim(ctx, args)
    name = "sim_bug" if result.get("bug") else "sim"
    ctx.write_stage(name, result)
    print("[%s] sim %s%s: %s" % (result["status"], result.get("top"), " (INJECT_BUG)" if result.get("bug") else "",
                                 result.get("stats") or result.get("reason") or ""))
    rt = result.get("tool_retry")
    if rt:
        print("[WARN] sim 首次编译命令解析失败，已改用缓存工具: %s（原: %s）"
              % (rt.get("to"), rt.get("from")))
    if result.get("hint"):
        print("[HINT] %s" % result["hint"])
    if result.get("tail") and result["status"] not in ("PASS",):
        print(result["tail"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


# ---------------------------------------------------------------------------
# synthesis / PPA
# ---------------------------------------------------------------------------

def _budget_for(ctx: Context, top: str) -> Dict[str, Any]:
    tops = (ctx.budget.get("tops") or {})
    b = dict(ctx.budget.get("default") or {})
    b.update(tops.get(top) or {})
    return b


def do_synth(ctx: Context, args: argparse.Namespace) -> Dict[str, Any]:
    top = ctx.infer_top(required=True)
    files = ctx.rtl_files(getattr(args, "files", None))
    if not files:
        raise RtlqError("rtl/ 下没有 .v/.sv 文件")
    if not ctx.tools.yosys:
        return {"command": "synth", "status": "SKIP", "top": top,
                "reason": "yosys not found", "metrics": None}
    out_dir = ctx.report_dir / "ppa"
    out_dir.mkdir(parents=True, exist_ok=True)
    pre_json = out_dir / ("%s_pre_stat.json" % top)
    pre_ltp = out_dir / ("%s_pre_ltp.txt" % top)
    post_json = out_dir / ("%s_stat.json" % top)
    post_ltp = out_dir / ("%s_ltp.txt" % top)
    for p in (pre_json, pre_ltp, post_json, post_ltp):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    lines = ["read_verilog -sv " + " ".join(_q(f) for f in files),
             "hierarchy -check -top " + top,
             "proc", "opt_clean", "flatten",
             'tee -o %s stat -json' % _q(pre_json),
             'tee -o %s ltp -noff' % _q(pre_ltp),
             "synth -top " + top + " -flatten",
             'tee -o %s stat -json' % _q(post_json),
             'tee -o %s ltp -noff' % _q(post_ltp)]
    r = _yosys(ctx, "synth_%s" % top, lines, ctx.stage_timeout("synth"))
    pre_stat = _json_from_tee(pre_json)
    post_stat = _json_from_tee(post_json)
    metrics: Dict[str, Any] = {}
    if post_stat:
        metrics["cells"] = int(((post_stat.get("design") or {}).get("num_cells")) or 0)
        metrics["ff"] = _ff_count(post_stat)
    depth = _ltp_depth(post_ltp)
    if depth is not None:
        metrics["depth"] = depth
    pre_metrics: Dict[str, Any] = {}
    if pre_stat:
        pre_metrics["cells"] = int(((pre_stat.get("design") or {}).get("num_cells")) or 0)
        pre_metrics["ff"] = _ff_count(pre_stat)
    pre_depth = _ltp_depth(pre_ltp)
    if pre_depth is not None:
        pre_metrics["depth"] = pre_depth
    budget = _budget_for(ctx, top)
    violations = []
    for key, label in (("max_cells", "cells"), ("max_ff", "ff"), ("max_depth", "depth")):
        lim = budget.get(key)
        if lim is not None and metrics.get(label) is not None:
            if int(metrics[label]) > int(lim):
                violations.append({"metric": label, "actual": int(metrics[label]),
                                   "limit": int(lim)})
    if r.timed_out:
        status = "ERROR"
    elif r.rc != 0 or not post_stat:
        status = "FAIL"
    elif violations and (ctx.policy.get("all") or {}).get("fail_on_ppa", True) and \
            not getattr(args, "no_fail_ppa", False):
        status = "FAIL"
    else:
        status = "PASS"
    return {
        "command": "synth", "status": status, "top": top,
        "metrics": metrics, "pre_metrics": pre_metrics,
        "budget": budget, "violations": violations,
        "rc": r.rc, "seconds": round(r.seconds, 3),
        "stat": str(post_json), "ltp": str(post_ltp),
        "log": str(r.log) if r.log else None, "tail": r.tail(20),
    }


def cmd_synth(ctx: Context, args: argparse.Namespace) -> int:
    top = ctx.infer_top(required=True)
    baseline_path = _baseline_for_run(ctx, top, getattr(args, "baseline", None))
    baseline_data = _load_json(baseline_path, {}) if baseline_path else None
    result = do_synth(ctx, args)
    ctx.write_stage("ppa", result)
    snap = _snapshot_payload(ctx, result, "synth")
    snap_path = _write_snapshot(ctx, top, snap)
    print("[%s] synth %s: cells=%s ff=%s depth=%s" % (
        result["status"], result.get("top"),
        (result.get("metrics") or {}).get("cells"),
        (result.get("metrics") or {}).get("ff"),
        (result.get("metrics") or {}).get("depth")))
    for v in result.get("violations") or []:
        print("  PPA budget exceeded: %s actual=%s limit=%s" %
              (v["metric"], v["actual"], v["limit"]))
    if baseline_data is not None:
        cmp = _compare_snapshots(
            baseline_data, snap, ctx, top, baseline_path, snap_path,
            allow_ppa_regression=getattr(args, "allow_ppa_regression", False))
        print("  baseline %s -> %s: %s" % (baseline_path, snap_path, cmp["status"]))
        for key in ("cells", "ff", "depth"):
            row = (cmp.get("metrics") or {}).get(key) or {}
            if row.get("delta") is not None:
                print("    %-5s %s -> %s (%+d)" %
                      (key, row.get("before"), row.get("after"), row.get("delta")))
    if result.get("tail") and result["status"] not in ("PASS",):
        print(result["tail"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("PASS", "WARN") else 1


# ---------------------------------------------------------------------------
# LEC / formal
# ---------------------------------------------------------------------------

def _blacklist_for(ctx: Context, top: str) -> List[str]:
    b = (ctx.policy.get("lec") or {}).get("blacklist") or {}
    if isinstance(b, dict):
        vals = b.get(top)
        if vals is None:
            vals = b.get("default") or []
    else:
        vals = b
    return [str(x) for x in vals]


def do_lec(ctx: Context, args: argparse.Namespace) -> Dict[str, Any]:
    top = ctx.infer_top(required=True)
    files = ctx.rtl_files(getattr(args, "files", None))
    if not ctx.tools.yosys:
        return {"command": "lec", "status": "SKIP", "top": top, "reason": "yosys not found"}
    # An explicit empty `--blacklist` must clear a configured policy entry;
    # using `or` here would treat [] as "not given" and silently fall back.
    cli_bl = getattr(args, "blacklist", None)
    bl = list(cli_bl) if cli_bl is not None else _blacklist_for(ctx, top)
    bl_file = ctx.logs / ("lec_blacklist_%s.txt" % top)
    _write_text(bl_file, "\n".join(bl) + ("\n" if bl else ""))
    flags = ""
    if (ctx.policy.get("lec") or {}).get("multiclock", True):
        flags += " -multiclock"
    flags += " -assert"
    if bl:
        # equiv_opt's -blacklist argument is passed to a C++ helper without
        # shell-style quote stripping; a quoted path becomes a literal quote
        # in the filename.  Workspace paths here are normally ASCII/no-space.
        flags += " -blacklist " + _posix(bl_file)
    lines = ["read_verilog -sv " + " ".join(_q(f) for f in files),
             "hierarchy -check -top " + top,
             "proc", "memory", "opt_clean",
             "equiv_opt" + flags + " synth"]
    r = _yosys(ctx, "lec_%s" % top, lines, ctx.stage_timeout("lec"))
    proven = 0
    unproven = 0
    # Yosys prints: "Of those cells 32 are proven and 0 are unproven."
    m = re.search(r"Of those cells\s+(\d+)\s+are proven and\s+(\d+)\s+are unproven", r.out)
    if m:
        proven, unproven = int(m.group(1)), int(m.group(2))
    else:
        for m in re.finditer(r"(\d+)\s+\$equiv cells:?\s*(\d+)\s+proven,\s*(\d+)\s+unproven", r.out):
            proven, unproven = int(m.group(2)), int(m.group(3))
    success = "Equivalence successfully proven!" in r.out and r.rc == 0
    if r.timed_out:
        status = "ERROR"
    elif success:
        status = "PASS"
    elif r.rc != 0 or unproven:
        status = "FAIL"
    else:
        status = "FAIL"
    unproven_names = _lec_unproven_names(r.out)
    result = {
        "command": "lec", "status": status, "top": top,
        "proven": proven, "unproven": unproven, "blacklist": bl,
        "unproven_signals": unproven_names,
        "rc": r.rc, "seconds": round(r.seconds, 3),
        "log": str(r.log) if r.log else None, "tail": r.tail(30),
    }
    if unproven and not bl and unproven_names and \
            set(unproven_names) <= {"state_next"}:
        result["hint"] = (
            "unproven 仅剩 state_next：常见原因是 F2 用 `else ;` 或块首 "
            "`state_next = state;` 兜底保持，综合出 DFFE。请按 "
            "references/coding_style.md 第 13 节在每个分支显式赋值状态常量后重跑。"
            "blacklist 默认为空，不会自动排除该信号。")
    return result


def _lec_unproven_names(text: str) -> List[str]:
    """Signal names from Yosys lines like:
    `Unproven $equiv ...: \\state_next_gold [1] \\state_next_gate [1]`."""
    names = set()
    for line in (text or "").splitlines():
        if "Unproven" not in line:
            continue
        for m in re.finditer(r"\\([A-Za-z_][\w$]*)_gold\b", line):
            names.add(m.group(1))
    return sorted(names)


def cmd_lec(ctx: Context, args: argparse.Namespace) -> int:
    result = do_lec(ctx, args)
    ctx.write_stage("lec", result)
    print("[%s] lec %s: proven=%d unproven=%d" %
          (result["status"], result.get("top"), result.get("proven", 0), result.get("unproven", 0)))
    if result.get("hint"):
        print("[HINT] %s" % result["hint"])
    if result.get("tail") and result["status"] not in ("PASS", "SKIP"):
        print(result["tail"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("PASS", "SKIP") else 1


def _sby_command(ctx: Context) -> List[str]:
    cfg = (ctx.policy.get("formal") or {}).get("python", "auto")
    if cfg and cfg != "auto":
        return shlex.split(cfg)
    if os.name == "nt":
        py = shutil.which("py")
        if py:
            return [py, "-3.12"]
    return [sys.executable]


def _sby_engines(sby_file: Path) -> List[str]:
    """Full command line of every [engines] entry (mode headers allow
    `[engines prove]`).  An empty list means sby would reject the config.

    Keep the whole line (`abc pdr`) instead of only the engine name so report
    readers can tell which options were actually used.
    """
    engines: List[str] = []
    section = ""
    for raw in _read_text(sby_file).splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and "]" in line:
            inner = line[1:line.index("]")].strip().lower()
            section = inner.split()[0] if inner else ""
            continue
        if section != "engines":
            continue
        line = line.split("#", 1)[0].strip()
        if line:
            engines.append(line)
    return engines


def _sby_engine_name(entry: str) -> str:
    parts = entry.split()
    return parts[0].lower() if parts else ""


def _find_yosys_smtbmc(ctx: Context) -> Optional[Path]:
    """quality-lite 的 Yosys 只有 yosys.exe/yosys-abc.exe, 不含 smtbmc 驱动。"""
    roots: List[Path] = []
    if ctx.tools.quality_root:
        roots.append(ctx.tools.quality_root)
    roots.extend(_quality_roots(ctx.ws))
    seen = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        for rel in (Path("yosys") / "bin", Path("bin")):
            for name in ("yosys-smtbmc.exe", "yosys-smtbmc", "yosys-smtbmc.py"):
                p = root / rel / name
                if p.is_file():
                    return p
    w = shutil.which("yosys-smtbmc")
    return Path(w) if w else None


def _leftover_abc_pids() -> List[int]:
    """Best-effort list of yosys-abc.exe PIDs (Windows only, stdlib only)."""
    if os.name != "nt":
        return []
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq yosys-abc.exe",
             "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", timeout=10)
    except Exception:
        return []
    pids: List[int] = []
    for line in (r.stdout or "").splitlines():
        parts = [p.strip().strip('"') for p in line.strip().split('","')]
        if len(parts) >= 2 and parts[0].lower() == "yosys-abc.exe":
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def _rmtree_with_retry(path: Path, attempts: int = 5,
                       delay: float = 0.3) -> Optional[OSError]:
    """Remove a tree, tolerating short-lived Windows handle release delays."""
    for i in range(attempts):
        try:
            shutil.rmtree(path)
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            if i == attempts - 1:
                return exc
            time.sleep(delay)
    return None


def do_formal(ctx: Context, args: argparse.Namespace) -> Dict[str, Any]:
    top = ctx.infer_top(required=True)
    sby_file = Path(getattr(args, "sby", "") or (ctx.ws / "formal" / (top + ".sby")))
    if not sby_file.is_absolute():
        sby_file = ctx.ws / sby_file
    if not sby_file.is_file():
        return {"command": "formal", "status": "SKIP", "top": top,
                "reason": "未找到 %s" % sby_file}
    if not ctx.tools.sby_py:
        return {"command": "formal", "status": "SKIP", "top": top,
                "reason": "sby not found", "sby": str(sby_file)}
    engines = _sby_engines(sby_file)
    if not engines:
        return {
            "command": "formal", "status": "ERROR", "top": top,
            "sby": str(sby_file),
            "reason": "sby 配置缺少可用的 [engines] 段（sby 会报 lacking engine configuration）",
            "hint": "在 %s 中增加:\n[engines]\nabc pdr" % sby_file,
        }
    if any(_sby_engine_name(e) in ("smtbmc", "yosys-smtbmc") for e in engines) and \
            not _find_yosys_smtbmc(ctx):
        return {
            "command": "formal", "status": "ERROR", "top": top,
            "sby": str(sby_file), "engines": engines,
            "reason": "sby 配置使用 smtbmc，但当前 quality-lite 未提供 yosys-smtbmc",
            "hint": "把 %s 的 [engines] 改为:\n[engines]\nabc pdr" % sby_file,
        }
    work = ctx.report_dir / "formal" / top
    if work.exists():
        rm_err = _rmtree_with_retry(work)
        if rm_err is not None:
            pids = _leftover_abc_pids()
            hint = ("关闭占用 %s 的进程后重试。常见原因是上次 formal 超时残留的 "
                    "yosys-abc.exe 孙进程" % work)
            if pids:
                hint += ("；当前检测到 yosys-abc.exe PID: %s，可执行 "
                         "`taskkill /F /T /PID <pid>` 清理" %
                         ", ".join(str(p) for p in pids))
            hint += "。清理后重跑 rtlq.py formal。"
            return {
                "command": "formal", "status": "ERROR", "top": top,
                "sby": str(sby_file), "engines": engines,
                "workdir": str(work),
                "reason": "无法清理上一次的形式验证目录（%s: %s）" %
                          (type(rm_err).__name__, rm_err),
                "hint": hint,
            }
    work.mkdir(parents=True, exist_ok=True)
    cmd: List[Any] = _sby_command(ctx) + [str(ctx.tools.sby_py)]
    if ctx.tools.yosys:
        cmd += ["--yosys", str(ctx.tools.yosys)]
    if ctx.tools.yosys_abc:
        cmd += ["--abc", str(ctx.tools.yosys_abc)]
    cmd += ["-d", str(work), str(sby_file)]
    formal_timeout = ctx.stage_timeout("formal")
    r = _run(cmd, ctx.ws, formal_timeout, ctx.log_path("formal_%s" % top))
    text = r.out
    if "DONE (PASS" in text or "Status returned by engine: PASS" in text:
        status = "PASS"
    elif "DONE (FAIL" in text or "Status returned by engine: FAIL" in text:
        status = "FAIL"
    elif r.timed_out:
        status = "ERROR"
    elif r.rc != 0:
        status = "FAIL"
    else:
        status = "FAIL"
    result = {
        "command": "formal", "status": status, "top": top, "sby": str(sby_file),
        "engines": engines, "workdir": str(work), "rc": r.rc,
        "seconds": round(r.seconds, 3),
        "log": str(r.log) if r.log else None, "tail": r.tail(30),
    }
    if r.timed_out:
        result["hint"] = (
            "formal 超时（%s s），已尝试终止 sby 及其 yosys/abc 子进程树。"
            "若下一次仍报 report/formal/%s 被占用，用 `tasklist /FI "
            "\"IMAGENAME eq yosys-abc.exe\"` 找到残留进程并 `taskkill /F /T "
            "/PID <pid>`，或调大 formal.timeout_s / 缩小证明规模后重试。"
            % (formal_timeout, top))
    return result


def cmd_formal(ctx: Context, args: argparse.Namespace) -> int:
    result = do_formal(ctx, args)
    ctx.write_stage("formal", result)
    lines = (result.get("tail") or "").splitlines()
    detail = result.get("reason") or (lines[-1] if lines else "")
    print("[%s] formal %s: %s" % (result["status"], result.get("top"), detail))
    if result.get("hint"):
        print("[HINT] %s" % result["hint"])
    if result.get("tail") and result["status"] not in ("PASS", "SKIP"):
        print(result["tail"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("PASS", "SKIP") else 1


# ---------------------------------------------------------------------------
# all + report
# ---------------------------------------------------------------------------

def _has_bug_injection(files: Sequence[Path]) -> bool:
    return any("INJECT_BUG" in _read_text(f) for f in files)


def _stage_extra(name: str, s: Dict[str, Any]) -> str:
    """One-line summary for a stage (shared by console and markdown report)."""
    status = s.get("status")
    if name == "lint":
        return "style=%d slang_warn=%d" % (
            len((s.get("style") or {}).get("issues") or []),
            len((s.get("slang") or {}).get("warnings") or []))
    if name == "sim":
        return s.get("stats") or s.get("reason") or ""
    if name == "negative":
        if status == "SKIP":
            return s.get("reason") or ""
        return "expected=%s actual=%s" % (s.get("expected"), s.get("actual"))
    if name == "synth":
        m = s.get("metrics") or {}
        if not m:
            return s.get("reason") or ""
        return "cells=%s ff=%s depth=%s" % (m.get("cells"), m.get("ff"), m.get("depth"))
    if name == "lec":
        if status == "SKIP":
            return s.get("reason") or ""
        return "proven=%s unproven=%s" % (s.get("proven"), s.get("unproven"))
    if name == "formal":
        if status == "SKIP":
            return s.get("reason") or ""
        lines = [x for x in (s.get("tail") or "").splitlines() if x.strip()]
        last = lines[-1] if lines else ""
        if "] " in last:
            last = last.split("] ", 1)[1]
        return last
    return s.get("reason") or s.get("stats") or ""


# ---------------------------------------------------------------------------
# history snapshots / baseline comparison
# ---------------------------------------------------------------------------

def _snapshot_dir(ctx: Context, top: str) -> Path:
    return ctx.report_dir / "history" / top


def _snapshot_files(ctx: Context, top: str) -> List[Path]:
    d = _snapshot_dir(ctx, top)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.is_file())


def _snapshot_payload(ctx: Context, result: Dict[str, Any], command: str) -> Dict[str, Any]:
    snap = dict(result)
    snap["snapshot_version"] = 1
    snap["command"] = command
    snap["top"] = result.get("top") or ctx.top
    snap["generated_at"] = result.get("generated_at") or _now()
    snap["workspace"] = str(ctx.ws)
    if command == "synth":
        snap["stages"] = {"synth": result}
        snap["ppa"] = result if result.get("metrics") else None
        snap["metrics"] = result.get("metrics") or {}
    else:
        synth = (result.get("stages") or {}).get("synth") or {}
        snap["metrics"] = synth.get("metrics") or {}
    return snap


def _write_snapshot(ctx: Context, top: str, snap: Dict[str, Any]) -> Path:
    d = _snapshot_dir(ctx, top)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    p = d / (stamp + ".json")
    n = 1
    while p.exists():
        p = d / ("%s_%d.json" % (stamp, n))
        n += 1
    _write_json(p, snap)
    return p


def _resolve_snapshot_path(ctx: Context, top: str, spec: Optional[str]) -> Optional[Path]:
    if not spec:
        return None
    p = Path(spec)
    if not p.is_absolute():
        # Accept a bare timestamp/filename under history/<top>, else a
        # workspace-relative path.
        alt = _snapshot_dir(ctx, top) / spec
        if not alt.is_file() and not Path(spec).suffix:
            alt = _snapshot_dir(ctx, top) / (spec + ".json")
        p = alt if alt.is_file() else (ctx.ws / spec)
    if p.is_dir():
        files = sorted(x for x in p.glob("*.json") if x.is_file())
        if not files:
            raise RtlqError("baseline 目录中没有快照: %s" % p)
        return files[-1].resolve()
    if not p.is_file():
        raise RtlqError("baseline 不存在: %s" % p)
    return p.resolve()


def _baseline_for_run(ctx: Context, top: str, spec: Optional[str]) -> Optional[Path]:
    """Pick the baseline before the current run writes its own snapshot."""
    explicit = _resolve_snapshot_path(ctx, top, spec)
    if explicit:
        return explicit
    files = _snapshot_files(ctx, top)
    return files[-1] if files else None


def _stage_status(snap: Dict[str, Any], name: str) -> Optional[str]:
    s = (snap.get("stages") or {}).get(name)
    return s.get("status") if isinstance(s, dict) else None


def _snap_metrics(snap: Dict[str, Any]) -> Dict[str, Any]:
    m = snap.get("metrics")
    if isinstance(m, dict) and m:
        return m
    ppa = snap.get("ppa")
    return (ppa.get("metrics") or {}) if isinstance(ppa, dict) else {}


def _snap_violations(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    v = snap.get("violations")
    if v is None:
        ppa = snap.get("ppa")
        if isinstance(ppa, dict):
            v = ppa.get("violations")
    return list(v or [])


def _fmt_value(v: Any) -> str:
    return "n/a" if v is None else str(v)


def _delta_text(v: Any) -> str:
    return "n/a" if v is None else ("%+d" % int(v))


def _compare_snapshots(base: Dict[str, Any], cur: Dict[str, Any], ctx: Context, top: str,
                       baseline_file: Optional[Path] = None,
                       current_file: Optional[Path] = None,
                       allow_ppa_regression: bool = False) -> Dict[str, Any]:
    stage_rows: Dict[str, Any] = {}
    stage_regressions: List[str] = []
    stage_improvements: List[str] = []
    for name in STAGE_ORDER:
        before = _stage_status(base, name)
        after = _stage_status(cur, name)
        if before is None and after is None:
            change = "n/a"
        elif before is None:
            change = "new"
        elif after is None:
            # 本次快照未执行该阶段（如 synth-only 对 all 快照）：不可比较，非回归。
            change = "n/a"
        else:
            rb = _STATUS_RANK.get(before, 2)
            ra = _STATUS_RANK.get(after, 2)
            if ra > rb:
                change = "regressed"
                stage_regressions.append(name)
            elif ra < rb:
                change = "improved"
                stage_improvements.append(name)
            else:
                change = "same"
        stage_rows[name] = {"before": before, "after": after, "change": change}

    bm = _snap_metrics(base)
    cm = _snap_metrics(cur)
    metric_rows: Dict[str, Any] = {}
    ppa_regressions: List[str] = []
    ppa_improvements: List[str] = []
    for key in ("cells", "ff", "depth"):
        before = bm.get(key)
        after = cm.get(key)
        delta = None
        change = "n/a"
        if before is not None and after is not None:
            delta = int(after) - int(before)
            if delta > 0:
                change = "regressed"
                ppa_regressions.append(key)
            elif delta < 0:
                change = "improved"
                ppa_improvements.append(key)
            else:
                change = "same"
        metric_rows[key] = {"before": before, "after": after,
                            "delta": delta, "change": change}
    if allow_ppa_regression:
        ppa_regressions = []

    # Budget is always checked against the current workspace configuration,
    # even when the snapshot itself carries an older budget.
    budget = _budget_for(ctx, top)
    violations: List[Dict[str, Any]] = []
    for key, label in (("max_cells", "cells"), ("max_ff", "ff"), ("max_depth", "depth")):
        lim = budget.get(key)
        if lim is not None and cm.get(label) is not None and int(cm[label]) > int(lim):
            violations.append({"metric": label, "actual": int(cm[label]),
                               "limit": int(lim)})
    seen = {(v.get("metric"), v.get("actual"), v.get("limit")) for v in violations}
    for v in _snap_violations(cur):
        k = (v.get("metric"), v.get("actual"), v.get("limit"))
        if k not in seen:
            violations.append(v)
            seen.add(k)

    regressions = list(stage_regressions) + list(ppa_regressions)
    if violations:
        regressions.append("budget")
    return {
        "command": "compare",
        "status": "PASS" if not regressions else "FAIL",
        "top": top,
        "baseline": {"file": str(baseline_file) if baseline_file else None,
                     "generated_at": base.get("generated_at")},
        "current": {"file": str(current_file) if current_file else None,
                    "generated_at": cur.get("generated_at")},
        "stages": stage_rows,
        "metrics": metric_rows,
        "budget": budget,
        "violations": violations,
        "regressions": regressions,
        "improvements": list(stage_improvements) + list(ppa_improvements),
    }


def _comparison_md(cmp: Dict[str, Any]) -> List[str]:
    b = cmp.get("baseline") or {}
    c = cmp.get("current") or {}
    regs = cmp.get("regressions") or []
    imps = cmp.get("improvements") or []
    if regs:
        concl = "存在回归"
    elif imps:
        concl = "无回归，存在改善"
    else:
        concl = "无回归，无变化"
    lines = ["## Baseline vs Current", "",
             "- baseline: `%s` (%s)" % (b.get("file") or "-", b.get("generated_at") or "-"),
             "- current : `%s` (%s)" % (c.get("file") or "-", c.get("generated_at") or "-"),
             "- 结论: **%s**" % concl]
    if regs:
        lines.append("- 回归项: %s" % ", ".join(str(x) for x in regs))
    if imps:
        lines.append("- 改善项: %s" % ", ".join(str(x) for x in imps))
    lines += ["", "| 阶段 | Baseline | Current | 变化 |", "|---|---|---|---|"]
    for name in STAGE_ORDER:
        row = (cmp.get("stages") or {}).get(name) or {}
        lines.append("| %s | %s | %s | %s |" % (
            name, _fmt_value(row.get("before")), _fmt_value(row.get("after")),
            row.get("change", "n/a")))
    lines += ["", "| 指标 | Baseline | Current | Delta | 变化 |", "|---|---|---|---|---|"]
    for key in ("cells", "ff", "depth"):
        row = (cmp.get("metrics") or {}).get(key) or {}
        lines.append("| %s | %s | %s | %s | %s |" % (
            key, _fmt_value(row.get("before")), _fmt_value(row.get("after")),
            _delta_text(row.get("delta")), row.get("change", "n/a")))
    if cmp.get("violations"):
        lines.append("")
        lines.append("**PPA 超预算**: " + "; ".join(
            "%s actual=%s limit=%s" % (v.get("metric"), v.get("actual"), v.get("limit"))
            for v in cmp["violations"]))
    lines.append("")
    return lines


def _mutation_files(ctx: Context, top: str) -> List[str]:
    """Mutation logs live in report/mutation/<top>/ (see formal README)."""
    d = ctx.report_dir / "mutation" / top
    if not d.is_dir():
        return []
    return sorted(str(p.relative_to(ctx.ws)) for p in d.rglob("*") if p.is_file())


def _summary_md(quality: Dict[str, Any],
                mutation_files: Optional[Sequence[str]] = None) -> str:
    stages = quality.get("stages") or {}
    lines = ["# RTL 质量报告 — %s" % (quality.get("top") or "(unknown)"),
             "- 结论: **%s**" % quality.get("status"),
             "- 生成时间: %s" % quality.get("generated_at"),
             "- 工作区: `%s`" % quality.get("workspace"),
             ""]
    lines += ["## 阶段结果", "", "| 阶段 | 状态 | 摘要 |", "|---|---|---|"]
    for name in ("lint", "sim", "negative", "synth", "lec", "formal"):
        s = stages.get(name)
        if not s:
            continue
        lines.append("| %s | %s | %s |" % (name, s.get("status"), _stage_extra(name, s)))
    if quality.get("ppa"):
        lines += ["", "## PPA", "", "| 指标 | 数值 | 预算 |", "|---|---|---|"]
        m = quality["ppa"].get("metrics") or {}
        b = quality["ppa"].get("budget") or {}
        lines.append("| cells | %s | %s |" % (m.get("cells"), b.get("max_cells", "-")))
        lines.append("| FF | %s | %s |" % (m.get("ff"), b.get("max_ff", "-")))
        lines.append("| depth | %s | %s |" % (m.get("depth"), b.get("max_depth", "-")))
        for v in quality["ppa"].get("violations") or []:
            lines.append("")
            lines.append("**PPA 超限**: %s actual=%s limit=%s" %
                         (v["metric"], v["actual"], v["limit"]))
    baseline = quality.get("baseline") or {}
    if baseline.get("compare"):
        lines += [""] + _comparison_md(baseline["compare"])
    elif baseline.get("error"):
        lines += ["", "## Baseline vs Current", "",
                  "- baseline: `%s`" % baseline.get("file"),
                  "- 错误: %s" % baseline.get("error")]
    if mutation_files:
        lines += ["", "## 变异/反例证据", ""]
        for f in mutation_files:
            lines.append("- `%s`" % f)
    lines += ["", "## 工具版本", ""]
    for k, v in (quality.get("tools") or {}).items():
        lines.append("- %s: `%s`" % (k, v))
    lines += ["", "## 明细", "", "```json",
              json.dumps(quality, ensure_ascii=False, indent=2)[:20000], "```", ""]
    return "\n".join(lines)


def _render_summary(ctx: Context, quality: Dict[str, Any]) -> Path:
    p = ctx.report_dir / "summary.md"
    top = str(quality.get("top") or "")
    _write_text(p, _summary_md(quality, _mutation_files(ctx, top)))
    return p


def do_all(ctx: Context, args: argparse.Namespace) -> Dict[str, Any]:
    top = ctx.infer_top(required=True)
    files = ctx.rtl_files(getattr(args, "files", None))
    # Resolve/load the baseline *before* this run writes its own snapshot.
    baseline_path = _baseline_for_run(ctx, top, getattr(args, "baseline", None))
    baseline_data = _load_json(baseline_path, {}) if baseline_path else None
    stages: Dict[str, Any] = {}
    stages["lint"] = do_lint(ctx, args)
    ctx.write_stage("lint", stages["lint"])
    stages["sim"] = do_sim(ctx, args, bug=False)
    ctx.write_stage("sim", stages["sim"])
    if (ctx.policy.get("all") or {}).get("negative", True) and not getattr(args, "no_negative", False):
        # Only the selected top's own file matters here.  Scanning every RTL
        # file would make reg_adder inherit sync_fifo's INJECT_BUG branch.
        top_files = [f for f in files if f.stem == top]
        if _has_bug_injection(top_files or files):
            neg_sim = do_sim(ctx, args, bug=True)
            ctx.write_stage("sim_bug", neg_sim)
            stages["negative"] = {
                "status": "PASS" if neg_sim["status"] == "FAIL" else "FAIL",
                "expected": "FAIL", "actual": neg_sim["status"],
                "reason": "缺陷注入被测试台检出" if neg_sim["status"] == "FAIL"
                          else "缺陷注入后测试台仍 PASS，说明测试无鉴别力",
                "sim": neg_sim,
            }
        else:
            stages["negative"] = {"status": "SKIP", "reason": "RTL 未包含 INJECT_BUG 分支"}
    else:
        stages["negative"] = {"status": "SKIP", "reason": "disabled"}
    if (ctx.policy.get("all") or {}).get("synth", True) and not getattr(args, "no_synth", False):
        stages["synth"] = do_synth(ctx, args)
    else:
        stages["synth"] = {"status": "SKIP", "reason": "disabled"}
    if (ctx.policy.get("all") or {}).get("lec", True) and not getattr(args, "no_lec", False):
        stages["lec"] = do_lec(ctx, args)
    else:
        stages["lec"] = {"status": "SKIP", "reason": "disabled"}
    if (ctx.policy.get("all") or {}).get("formal", True) and not getattr(args, "no_formal", False):
        stages["formal"] = do_formal(ctx, args)
    else:
        stages["formal"] = {"status": "SKIP", "reason": "disabled"}
    status = _worst(s["status"] for s in stages.values())
    if status == "WARN" and getattr(args, "strict", False):
        status = "FAIL"
    quality = {
        "command": "all", "status": status, "top": top,
        "workspace": str(ctx.ws), "generated_at": _now(),
        "files": [str(f) for f in files],
        "stages": stages,
        "ppa": stages.get("synth") if stages.get("synth", {}).get("metrics") else None,
        "tools": ctx.versions(),
        "seconds": round(time.time() - ctx.start, 3),
    }
    snap = _snapshot_payload(ctx, quality, "all")
    snap_path = _write_snapshot(ctx, top, snap)
    quality["snapshot"] = str(snap_path)
    if baseline_data is not None:
        baseline_cmp = _compare_snapshots(
            baseline_data, snap, ctx, top, baseline_path, snap_path,
            allow_ppa_regression=getattr(args, "allow_ppa_regression", False))
        quality["baseline"] = {
            "file": str(baseline_path),
            "generated_at": baseline_data.get("generated_at"),
            "compare": baseline_cmp,
        }
        if getattr(args, "fail_on_regression", False) and \
                baseline_cmp.get("status") != "PASS":
            # The six stages themselves passed, but the embedded baseline
            # comparison found a regression.  Off by default: `all` is also
            # used to record a baseline, and an intentional experiment should
            # not fail the gate by itself.  Opt in with --fail-on-regression.
            quality["status"] = "FAIL"
            snap["status"] = "FAIL"
            _write_json(snap_path, snap)
    ctx.write_stage("quality", quality)
    _render_summary(ctx, quality)
    # Keep a per-top copy so running another module does not overwrite the
    # evidence for this one.
    _write_text(ctx.report_dir / ("summary_%s.md" % top),
                _summary_md(quality, _mutation_files(ctx, top)))
    if args.json:
        print(json.dumps(quality, ensure_ascii=False, indent=2))
    return quality


def cmd_all(ctx: Context, args: argparse.Namespace) -> int:
    q = do_all(ctx, args)
    print("== rtlq all: %s ==" % q["status"])
    for name in STAGE_ORDER:
        s = q["stages"].get(name) or {}
        print("  %-8s %-5s %s" % (name, s.get("status"), _stage_extra(name, s)))
    lec = q["stages"].get("lec") or {}
    if lec.get("hint"):
        print("  [HINT] %s" % lec["hint"])
    for name in ("sim", "negative"):
        s = q["stages"].get(name) or {}
        rt = s.get("tool_retry") or (s.get("sim") or {}).get("tool_retry")
        if rt:
            print("  [WARN] %s 阶段编译命令解析失败，已改用缓存工具: %s（原: %s）"
                  % (name, rt.get("to"), rt.get("from")))
    base = q.get("baseline") or {}
    cmp = base.get("compare") or {}
    if cmp:
        print("  baseline %s: %s%s" % (
            base.get("file"), cmp.get("status"),
            (" (" + ", ".join(str(x) for x in cmp.get("regressions")) + ")")
            if cmp.get("regressions") else ""))
    print("report: %s" % (ctx.report_dir / "summary.md"))
    return 0 if q["status"] in ("PASS", "WARN") else 1


def cmd_compare(ctx: Context, args: argparse.Namespace) -> int:
    top = ctx.infer_top(required=True)
    files = _snapshot_files(ctx, top)
    if not files:
        raise RtlqError("没有历史快照；请先运行 rtlq all/synth -Top %s" % top)
    current_path = files[-1]
    if getattr(args, "baseline", None):
        baseline_path = _resolve_snapshot_path(ctx, top, args.baseline)
    else:
        baseline_path = files[-2] if len(files) >= 2 else None
    if not baseline_path:
        raise RtlqError("至少需要两个快照，或用 --baseline 指定基准")
    base = _load_json(baseline_path, {})
    cur = _load_json(current_path, {})
    cmp = _compare_snapshots(
        base, cur, ctx, top, baseline_path, current_path,
        allow_ppa_regression=getattr(args, "allow_ppa_regression", False))
    print("== rtlq compare: %s ==" % top)
    print("baseline: %s (%s)" % (baseline_path, base.get("generated_at") or "-"))
    print("current : %s (%s)" % (current_path, cur.get("generated_at") or "-"))
    print("")
    print("%-8s %-8s %-8s %s" % ("stage", "baseline", "current", "change"))
    for name in STAGE_ORDER:
        row = (cmp.get("stages") or {}).get(name) or {}
        print("%-8s %-8s %-8s %s" % (
            name, _fmt_value(row.get("before")), _fmt_value(row.get("after")),
            row.get("change", "n/a")))
    print("")
    print("%-8s %-8s %-8s %-8s %s" % ("metric", "baseline", "current", "delta", "change"))
    for key in ("cells", "ff", "depth"):
        row = (cmp.get("metrics") or {}).get(key) or {}
        print("%-8s %-8s %-8s %-8s %s" % (
            key, _fmt_value(row.get("before")), _fmt_value(row.get("after")),
            _delta_text(row.get("delta")), row.get("change", "n/a")))
    print("")
    if cmp.get("violations"):
        print("budget: FAIL")
        for v in cmp["violations"]:
            print("  %s actual=%s limit=%s" %
                  (v.get("metric"), v.get("actual"), v.get("limit")))
    else:
        print("budget: PASS")
    extra: List[str] = []
    if cmp.get("regressions"):
        extra.append("regressions: " + ", ".join(str(x) for x in cmp["regressions"]))
    if cmp.get("improvements"):
        extra.append("improvements: " + ", ".join(str(x) for x in cmp["improvements"]))
    print("RESULT: %s%s" % (cmp["status"], (" (" + "; ".join(extra) + ")") if extra else ""))
    if args.json:
        print(json.dumps(cmp, ensure_ascii=False, indent=2))
    return 0 if cmp["status"] == "PASS" else 1


def cmd_report(ctx: Context, args: argparse.Namespace) -> int:
    p = ctx.report_dir / "quality.json"
    if not p.is_file():
        raise RtlqError("找不到 %s；请先运行 rtlq all" % p)
    q = _load_json(p, {})
    summary = _render_summary(ctx, q)
    print("summary: %s" % summary)
    print("RESULT: %s" % q.get("status"))
    if args.json:
        print(json.dumps(q, ensure_ascii=False, indent=2))
    return 0 if q.get("status") in ("PASS", "WARN") else 1


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-W", "--workdir", default=str(Path.cwd()),
                   help="工作区根目录（含 rtl/ tb/），默认当前目录")
    p.add_argument("--top", default=None, help="DUT top module")
    p.add_argument("--files", nargs="*", default=None, help="显式 RTL 文件列表（默认 rtl/*.v rtl/*.sv）")
    p.add_argument("--report-dir", default=None, help="报告目录（默认 <ws>/report）")
    p.add_argument("--policy", default=None, help="quality_policy.json 路径")
    p.add_argument("--budget-file", default=None, help="ppa_budget.json 路径")
    p.add_argument("--timeout", type=int, default=None, help="单阶段超时秒数（覆盖 policy）")
    p.add_argument("--strict", action="store_true", help="警告也视为失败")
    p.add_argument("--json", action="store_true", help="额外输出 JSON 到 stdout")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rtlq", description="lightweight RTL quality / PPA CLI")
    ap.add_argument("--version", action="version", version="rtlq " + VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="检查工具链")
    _add_common(p); p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("manifest", help="生成 quality-lite 清单/哈希")
    _add_common(p); p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("lint", help="风格 + slang + Yosys 结构检查")
    _add_common(p); p.set_defaults(func=cmd_lint)

    p = sub.add_parser("sim", help="编译并运行自检测试台")
    _add_common(p)
    p.add_argument("--tb", default=None, help="TB 文件（默认 tb/tb_<top>.v）")
    p.add_argument("--tb-top", default=None, help="TB module 名（默认自动识别）")
    p.add_argument("--bug", action="store_true", help="编译时定义 INJECT_BUG=1")
    p.add_argument("--wave", action="store_true", help="编译时定义 DUMP_WAVE，检查 VCD")
    p.add_argument("--fst", action="store_true", help="wave 后调用 vcd2fst 生成 FST")
    p.add_argument("--grammar", default=None, help="iverilog -g 版本（默认 2012）")
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser("synth", help="Yosys 综合 + PPA 指标/预算（写历史快照）")
    _add_common(p)
    p.add_argument("--no-fail-ppa", action="store_true", help="PPA 超限不判失败")
    p.add_argument("--baseline", default=None, help="对比的基准快照（默认上一个快照）")
    p.add_argument("--allow-ppa-regression", action="store_true",
                   help="PPA 指标变差不判失败（预算仍校验）")
    p.set_defaults(func=cmd_synth)

    p = sub.add_parser("lec", help="Yosys 逻辑等价检查")
    _add_common(p)
    p.add_argument("--blacklist", nargs="*", default=None, help="等价检查 blacklist 信号")
    p.set_defaults(func=cmd_lec)

    p = sub.add_parser("formal", help="SymbiYosys 属性证明")
    _add_common(p)
    p.add_argument("--sby", default=None, help=".sby 文件（默认 formal/<top>.sby）")
    p.set_defaults(func=cmd_formal)

    p = sub.add_parser("all", help="完整闭环：lint/sim/negative/synth/lec/formal（写历史快照）")
    _add_common(p)
    p.add_argument("--no-negative", action="store_true")
    p.add_argument("--no-synth", action="store_true")
    p.add_argument("--no-lec", action="store_true")
    p.add_argument("--no-formal", action="store_true")
    p.add_argument("--no-fail-ppa", action="store_true")
    p.add_argument("--baseline", default=None, help="对比的基准快照（默认上一个快照）")
    p.add_argument("--allow-ppa-regression", action="store_true",
                   help="PPA 指标变差不判失败（预算仍校验）")
    p.add_argument("--fail-on-regression", action="store_true",
                   help="内嵌 Baseline vs Current 有阶段/PPA 回归或超预算时整体判 FAIL")
    p.set_defaults(func=cmd_all)

    p = sub.add_parser("compare", help="对比最近两次快照或指定 baseline")
    _add_common(p)
    p.add_argument("--baseline", default=None,
                   help="基准快照文件/时间戳（默认上一次快照）")
    p.add_argument("--allow-ppa-regression", action="store_true",
                   help="PPA 指标变差不判失败（预算仍校验）")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("report", help="从 report/quality.json 重新生成 summary.md")
    _add_common(p); p.set_defaults(func=cmd_report)
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Keep Chinese diagnostics and JSON UTF-8 even when the Windows console /
    # redirected stream would otherwise pick the active ANSI code page (GBK).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        ctx = Context(args)
        return int(args.func(ctx, args))
    except RtlqError as exc:
        print("[ERROR] %s" % exc, file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("[ERROR] interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
