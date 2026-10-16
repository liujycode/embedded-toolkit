#!/usr/bin/env python3
"""embedded-register-verify：核验 C/C++ 代码里的寄存器写入是否与芯片 SVD 一致。

只做词法分析（规格 0.7：不执行用户代码、不 eval）；判定不确定时进"未判定"。
退出码：0 = 没有"报"；1 = 检出问题或工具出错（errors 为空时表示检出问题）。

示例：
  python scripts/verify.py check main.c --chip STM32G431
  python scripts/verify.py check src/ --demo --checklist
  python scripts/verify.py check --patch changes.diff --chip STM32G431
  python scripts/verify.py rules
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import crules  # noqa: E402
import cscan  # noqa: E402
from etk_core import query as etk_query  # noqa: E402
from etk_core.cache import load_device_cached  # noqa: E402
from etk_core.discovery import find_svd  # noqa: E402
from etk_core.errors import E_INPUT_INVALID, E_INTERNAL, E_SVD_NOT_FOUND, EtkError  # noqa: E402
from etk_core.output import envelope  # noqa: E402

TOOL = "embedded-register-verify"
__version__ = "1.9.0"
DEMO_SVD = os.path.normpath(os.path.join(_HERE, os.pardir, "assets", "demo.svd"))
MAX_FILES = 200
MAX_WARNINGS_SHOWN = 20
SKIP_DIRS = frozenset({"node_modules", "__pycache__", "site-packages"})


def build_parser():
    io = argparse.ArgumentParser(add_help=False)
    io.add_argument("--project-dir", metavar="DIR", help="从此目录向上查找 .etk/config.json（默认当前目录）")
    io.add_argument("--format", choices=("text", "json"), default="text", help="输出格式（默认 text）")
    io.add_argument("--out", metavar="FILE", help="把输出写入文件，而不是标准输出")

    common = argparse.ArgumentParser(add_help=False, parents=[io])
    common.add_argument("--svd", metavar="PATH", help="SVD 文件路径（优先级最高）")
    common.add_argument("--chip", metavar="NAME", help="芯片名，如 STM32G431，用于在本机 CMSIS-Pack 中查找")
    common.add_argument("--demo", action="store_true", help="使用内置演示芯片（合成数据）核验")

    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="核验 C/C++ 代码中的寄存器写入是否与芯片 SVD 一致（只做词法分析，不执行代码）。",
        epilog=(
            "示例：\n"
            "  verify.py check main.c --chip STM32G431\n"
            "  verify.py check src/ --demo --checklist\n"
            "  verify.py check --patch changes.diff --chip STM32G431\n"
            "  verify.py rules\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", parents=[common], help="核验文件、目录或补丁中的寄存器写入")
    p.add_argument("paths", nargs="*", metavar="路径",
                   help="C/C++ 源文件、头文件或目录（.c/.h/.cpp/.hpp/.ino 等；用 --patch 时可省略）")
    p.add_argument("--define", action="append", default=[], metavar="NAME=VALUE", help="补充宏定义（可多次）")
    p.add_argument("--headers", action="append", default=[], metavar="路径",
                   help="从头文件加载宏定义（文件或目录，可多次）：用于 ESP-IDF 等以寄存器常量宏写寄存器的代码")
    p.add_argument("--patch", metavar="FILE", help="核验 unified diff / git diff 文件中新增的行")
    p.add_argument("--no-clock-check", action="store_true", help="关闭 E07（时钟使能）检查")
    p.add_argument("--checklist", action="store_true", help="输出复查清单（按复查要求分组）")
    p.add_argument("--explain", action="store_true",
                   help="在报告里内联对应寄存器的定义（来自寄存器百事通的同一份 SVD）")
    p.add_argument("--limit", type=int, default=200, help="每个文件最多列出条数（默认 200）")

    sub.add_parser("rules", parents=[io], help="列出核验规则 E01–E11")
    return parser


# ---------- 输入收集 ----------

def _collect_sources(paths):
    files = []
    for item in paths:
        if os.path.isdir(item):
            for root, dirs, names in os.walk(item):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
                for name in sorted(names):
                    if name.lower().endswith((".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".ino")):
                        files.append(os.path.join(root, name))
        elif os.path.isfile(item):
            files.append(item)
        else:
            raise EtkError(E_INPUT_INVALID, "路径不存在：%s" % item)
    files = sorted(dict.fromkeys(os.path.abspath(f) for f in files))
    truncated = len(files) > MAX_FILES
    sources = []
    for path in files[:MAX_FILES]:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            raise EtkError(E_INPUT_INVALID, "无法读取文件：%s（%s）" % (path, exc))
        sources.append((os.path.basename(path), text, path))
    return sources, truncated


HEADER_EXTS = (".h", ".hpp", ".hh", ".inc", ".c")
HEADER_MAX_FILES = 512
HEADER_MAX_BYTES = 8 * 1024 * 1024
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)


def _resolve_include(token, base_dirs, roots, index):
    """把 `#include` 里的路径解析为实际文件：① 相对当前/被核验文件目录 ② 相对搜索根
    ③ 按文件名匹配（同名多个时按 --headers 给定顺序优先）。"""
    rel = token.replace("\\", "/")
    for base in base_dirs:
        candidate = os.path.normpath(os.path.join(base, rel))
        if os.path.isfile(candidate):
            return candidate
    for root in roots:
        candidate = os.path.normpath(os.path.join(root, rel))
        if os.path.isfile(candidate):
            return candidate
    hits = index.get(os.path.basename(rel).lower())
    if hits:
        return hits[0]
    return None


def _collect_header_defines(paths, requested=None, source_dirs=None):
    """从头文件（或目录）收集宏定义，用于解析寄存器常量宏（如 ESP-IDF 的 UART_CONF0_REG）。

    - requested 为被核验文件里的 `#include` 列表时：先解析出这些头文件的**闭包**并优先加载，
      其余文件按路径顺序补足（上限 512 个文件 / 8 MB）——保证关键宏一定加载，避免大目录截断误伤；
    - 没有 requested（源文件没有 include / 补丁模式）时：按原行为加载全部（带上限）。

    返回 (defines, note)：note 为 None 或加载策略/达到上限的说明。
    """
    roots = []
    explicit = []
    for item in paths:
        if os.path.isdir(item):
            roots.append(os.path.abspath(item))
        elif os.path.isfile(item):
            explicit.append(os.path.abspath(item))
        else:
            raise EtkError(E_INPUT_INVALID, "--headers 路径不存在：%s" % item)

    texts = {}
    total = [0]

    def load(path):
        if path in texts:
            return texts[path]
        if total[0] >= HEADER_MAX_BYTES:
            return None
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read(HEADER_MAX_BYTES - total[0])
        except OSError:
            texts[path] = None
            return None
        total[0] += len(text)
        texts[path] = text
        return text

    # 收集目录树里的全部候选文件（闭包解析与补足共用）；index 按 --headers 顺序构建，
    # 同名头文件（如各芯片家族的 rtc.h）先给哪个目录就优先用哪个
    all_files = list(explicit)
    index = {}
    for path in explicit:
        index.setdefault(os.path.basename(path).lower(), []).append(path)
    for root in roots:
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
            for name in sorted(names):
                if name.lower().endswith(HEADER_EXTS):
                    full = os.path.join(dirpath, name)
                    all_files.append(full)
                    index.setdefault(name.lower(), []).append(full)
    all_files = sorted(set(all_files))

    note = None
    closure = []
    if requested and roots:
        queue = list(requested)
        seen = set()
        while queue and len(closure) < HEADER_MAX_FILES:
            token = queue.pop(0)
            path = _resolve_include(token, source_dirs or [], roots, index)
            if path is None or path in seen:
                continue
            seen.add(path)
            closure.append(path)
            text = load(path)
            if text is None:
                continue
            for nested in _INCLUDE_RE.findall(text):
                queue.append(nested)
        if closure:
            note = "按被核验文件的 #include 优先加载了 %d 个头文件" % len(closure)

    order = closure + [path for path in all_files if path not in set(closure)]
    if len(order) > HEADER_MAX_FILES:
        cap_note = ("头文件数 %d 超过上限 %d，仅加载前 %d 个（建议把 --headers 指向更精确的目录）" % (
            len(order), HEADER_MAX_FILES, HEADER_MAX_FILES))
        note = (note + "；" + cap_note) if note else cap_note
        order = order[:HEADER_MAX_FILES]

    defines = {}
    for path in order:
        if total[0] >= HEADER_MAX_BYTES:
            cap_note = "头文件内容达到 %d MB 上限，其余未加载（建议缩小 --headers 范围）" % (
                HEADER_MAX_BYTES // (1024 * 1024))
            note = (note + "；" + cap_note) if note else cap_note
            break
        text = load(path)
        if text is None:
            continue
        joined, _line_map = cscan.join_continuations(text)
        clean = cscan.strip_comments_and_strings(joined)
        for name, expr in cscan.collect_defines(clean).items():
            defines.setdefault(name, expr)
    return defines, note


def _patch_sources(text):
    """把 unified diff 还原成"只含新增行、行号对齐新文件"的合成文本。"""
    files = {}
    current = None
    new_line = 0
    for raw in text.split("\n"):
        if raw.startswith("+++ "):
            name = raw[4:].strip()
            if name.startswith(("b/", "a/")):
                name = name[2:]
            current = files.setdefault(name, {})
            continue
        if raw.startswith("@@ "):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if m:
                new_line = int(m.group(1))
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            current[new_line] = raw[1:]
            new_line += 1
        elif raw.startswith(("-", "\\")):
            continue
        else:
            new_line += 1
    out = []
    for name, lines in sorted(files.items()):
        if not lines:
            continue
        buf = [""] * max(lines)
        for no, content in lines.items():
            buf[no - 1] = content
        out.append(("%s (patch)" % name, "\n".join(buf), name))
    return out


# ---------- 运行 ----------

def _run(args):
    if args.command == "rules":
        return [crules.rule_table()], [], []
    if args.limit < 1:
        raise EtkError(E_INPUT_INVALID, "--limit 必须大于 0")
    if args.patch and not os.path.isfile(args.patch):
        raise EtkError(E_INPUT_INVALID, "--patch 指定的文件不存在：%s" % args.patch)
    if args.demo:
        if args.svd:
            raise EtkError(
                E_INPUT_INVALID,
                "--demo 与 --svd 不能同时使用",
                hint="二选一：用 --svd 核验真实芯片，或用 --demo 试用内置演示芯片。",
            )
        if not os.path.isfile(DEMO_SVD):
            raise EtkError(E_SVD_NOT_FOUND, "内置演示数据缺失：%s" % DEMO_SVD,
                           hint="安装不完整，请重新安装技能包。")
        path, selected_by = DEMO_SVD, "内置演示数据（--demo）"
        notes = ["当前使用内置演示芯片 ETK-DEMO（合成数据，非真实芯片）；真实核验请用 --svd 或 --chip。"]
    else:
        path, selected_by, notes = find_svd(args.svd, args.chip, args.project_dir)
    device = load_device_cached(path)
    warnings = list(notes) + list(device.warnings)

    if args.patch:
        with open(args.patch, encoding="utf-8", errors="replace") as fh:
            sources = _patch_sources(fh.read())
        if not sources:
            raise EtkError(E_INPUT_INVALID, "补丁里没有可核验的新增行：%s" % args.patch)
    else:
        if not args.paths:
            raise EtkError(E_INPUT_INVALID, "请给出要核验的文件、目录，或用 --patch 指定补丁文件。")
        sources, truncated = _collect_sources(args.paths)
        if truncated:
            warnings.append("文件数超过 %d，只核验了前 %d 个。" % (MAX_FILES, MAX_FILES))
        if not sources:
            raise EtkError(E_INPUT_INVALID, "没有找到可核验的 .c/.h/.cpp/.hpp/.ino 文件。")

    defines = {}
    for item in args.define:
        name, sep, value = item.partition("=")
        if not sep or not name.strip():
            raise EtkError(E_INPUT_INVALID, "--define 需要 NAME=VALUE 形式：%r" % item)
        defines[name.strip()] = value.strip()
    if args.headers:
        requested = []
        source_dirs = set()
        for _name, text, path_hint in sources:
            if path_hint:
                parent = os.path.dirname(path_hint)
                if parent:
                    source_dirs.add(parent)
            for token in _INCLUDE_RE.findall(text):
                if token not in requested:
                    requested.append(token)
        header_defines, header_note = _collect_header_defines(
            args.headers, requested=requested, source_dirs=sorted(source_dirs))
        message = "从头文件加载了 %d 个宏定义（--headers）" % len(header_defines)
        if header_note:
            message += "；" + header_note
        warnings.append(message)
        merged = dict(header_defines)
        merged.update(defines)  # --define 显式指定优先
        defines = merged

    verifier = crules.Verifier(device, extra_defines=defines,
                               clock_check=not args.no_clock_check, limit=args.limit)
    verifier.checklist = bool(args.checklist)

    results = []
    errors = []
    selection = _selection_args(args)
    for name, text, path_hint in sources:
        try:
            res = verifier.check_file(name, text)
        except EtkError as exc:
            errors.append(exc.to_dict())
            continue
        res["path"] = path_hint
        res["source"]["selected_by"] = selected_by
        _attach_next(res, selection)
        if args.explain:
            _attach_explain(res, device)
        results.append(res)
    return results, warnings, errors


# ---------- 与寄存器百事通的联动 ----------

def _selection_args(args):
    """复现本次 SVD 选择的参数，用于生成可直接运行的查证命令。"""
    if args.demo:
        return ["--demo"]
    if args.svd:
        return ["--svd", os.path.abspath(args.svd)]
    if args.chip:
        return ["--chip", args.chip]
    if args.project_dir:
        return ["--project-dir", os.path.abspath(args.project_dir)]
    return []


def _attach_next(res, selection):
    """每条 finding 生成"下一步查证"命令（可在 embedded-register-lookup 技能里直接执行）。"""
    for finding in res["findings"]:
        hint = finding.get("lookup") or {}
        action = hint.get("action")
        if action == "lookup":
            call = ["lookup", hint["path"]]
        elif action == "addr":
            call = ["addr", hint["address"]]
        elif action == "search":
            call = ["search", hint["keyword"]]
        else:
            call = []
        finding["next"] = [{
            "tool": "embedded-register-lookup",
            "args": call + selection,
            "reason": hint.get("reason") or "查看寄存器事实",
        }] if call else []


def _attach_explain(res, device):
    """--explain：把对应寄存器的定义内联进报告（与百事通同一份 SVD、同一套查询）。"""
    cache = {}
    for finding in res["findings"]:
        finding["explain"] = _explain_lines(device, finding.get("lookup") or {}, cache)


def _explain_lines(device, hint, cache):
    action = hint.get("action")
    key = (action, hint.get("path") or hint.get("address") or hint.get("keyword"))
    if key in cache:
        return cache[key]
    lines = []
    try:
        if action == "lookup":
            lines = _format_lookup(etk_query.lookup(device, hint["path"]))
        elif action == "addr":
            lines = _format_addr(etk_query.find_address(device, int(hint["address"], 16)))
    except EtkError:
        lines = []
    cache[key] = lines
    return lines


def _format_lookup(data):
    kind = data.get("kind")
    if kind == "register":
        reg = data["register"]
        lines = ["寄存器 %s.%s：地址 %s  宽 %d 位  访问 %s  复位 %s" % (
            data["peripheral"], reg["name"], reg["address"], reg["size"], reg["access"], reg["reset"])]
        shown = data["fields"][:8]
        for f in shown:
            desc = "（%s）" % f["description"] if f["description"] and f["description"] != f["name"] else ""
            lines.append("  位 %-6s %-12s %s 复位 %d%s" % (
                f["bits"], f["name"], f["access"], f["reset"], desc))
        if len(data["fields"]) > len(shown):
            lines.append("  …另有 %d 个位域（用 lookup 查看全部）" % (len(data["fields"]) - len(shown)))
        return lines
    if kind == "field":
        f = data["field"]
        reg = data["register"]
        lines = ["位域 %s.%s.%s：位 %s（宽 %d） 访问 %s 复位 %d（寄存器复位 %s）" % (
            data["peripheral"], reg["name"], f["name"], f["bits"], f["width"],
            f["access"], f["reset"], reg["reset"])]
        for e in f["enums"][:6]:
            lines.append("  枚举 %s = %s%s" % (
                e["pattern"], e["name"], "（%s）" % e["description"] if e["description"] else ""))
        return lines
    if kind == "peripheral":
        shown = data["registers"][:8]
        lines = ["外设 %s：基地址 %s，共 %d 个寄存器" % (
            data["peripheral"], data["base_address"], len(data["registers"]))]
        lines.append("  " + "、".join(r["name"] for r in shown)
                     + ("……" if len(data["registers"]) > len(shown) else ""))
        return lines
    return []


def _format_addr(data):
    kind = data.get("kind")
    if kind == "exact" and data.get("matches"):
        m = data["matches"][0]
        return ["%s 是寄存器 %s（访问 %s，复位 %s）" % (
            data["address"], m["path"], m["access"], m["reset"])]
    if kind == "inside_register":
        n = data["nearest"]
        return ["%s 位于寄存器 %s 内部（第 %d 字节）" % (
            data["address"], n["path"], n["offset_in_register"])]
    if kind == "gap":
        return ["%s 不是寄存器地址（%s 内的保留区附近）" % (data["address"], data.get("peripheral") or "?")]
    return ["%s 不在任何外设地址范围内" % data["address"]]


# ---------- 渲染 ----------

def _render_rules(res):
    lines = ["核验规则（E01–E11）："]
    for item in res["rules"]:
        lines.append("  %s %s（%s）｜桶：%s｜标签：%s｜严重度：%s" % (
            item["class"], item["name"], item["verdict"], item["bucket"], item["label"], item["severity"]))
    lines.append("  " + res["note"])
    return lines


def _render_checklist(res):
    cl = res["checklist"]
    lines = ["复查清单："]
    if cl["chip_default"]:
        lines.append("  芯片默认（写入等于复位值，确认可删或有意为之）：")
        for item in cl["chip_default"][:20]:
            lines.append("    第 %d 行 %s" % (item["line"], item["code"]))
    lines.append("  已核验（无需复查）：%d 处" % cl["verified"])
    if cl["manual"]:
        lines.append("  需查手册（%d 条）：" % len(cl["manual"]))
        for item in cl["manual"][:20]:
            if "class" in item:
                lines.append("    第 %d 行（%s）%s" % (item["line"], item["class"], item["message"]))
            else:
                lines.append("    第 %d 行（未判定）%s" % (item["line"], item["reason"]))
    if cl["measured"]:
        lines.append("  需实测（%d 条，涉及 DMA/NVIC/SysTick 等，建议上板验证）：" % len(cl["measured"]))
        for item in cl["measured"][:20]:
            lines.append("    第 %d 行 %s" % (item["line"], item["code"]))
    return lines


def _render_verify(res):
    c = res["counts"]
    lines = ["%s：%d 处寄存器写入（报 %d、未判定 %d、通过 %d）" % (
        res["file"], c["writes"], c["report"], c["undetermined"], c["passed"])]
    for item in res["findings"]:
        lines.append("  [报] %s 第 %d 行：%s" % (item["class"], item["line"], item["message"]))
        lines.append("      代码：%s" % item["code"])
        if item.get("suggestion"):
            lines.append("      建议：%s" % item["suggestion"])
        for explain in item.get("explain") or []:
            lines.append("      " + explain)
        for nxt in item.get("next") or []:
            lines.append("      下一步：%s %s  （%s）" % (
                nxt["tool"], " ".join(nxt["args"]), nxt["reason"]))
    if res["findings_truncated"]:
        lines.append("  （问题过多，仅显示前 %d 条；用 --format json 获取全部）" % len(res["findings"]))
    for item in res["undetermined"]:
        lines.append("  [未判定] 第 %d 行：%s" % (item["line"], item["reason"]))
        lines.append("      代码：%s" % item["code"])
    if res["undetermined_truncated"]:
        lines.append("  （未判定条目过多，仅显示前 %d 条）" % len(res["undetermined"]))
    if res.get("checklist"):
        lines.extend(_render_checklist(res))
    src = res.get("source") or {}
    lines.append("[核验] 依据：%s（设备 %s，版本 %s）" % (
        src.get("file"), src.get("device"), src.get("version")))
    return lines


def render_text(env):
    lines = []
    for err in env["errors"]:
        lines.append("错误 [%s] %s" % (err["code"], err["message"]))
        if err.get("hint"):
            lines.append("  提示：%s" % err["hint"])
        for item in (err.get("details") or {}).get("tried", []):
            lines.append("  已尝试：%s" % item)
    for w in env["warnings"][:MAX_WARNINGS_SHOWN]:
        lines.append("注意：%s" % w)
    if len(env["warnings"]) > MAX_WARNINGS_SHOWN:
        lines.append("注意：另有 %d 条警告，用 --format json 查看全部" % (
            len(env["warnings"]) - MAX_WARNINGS_SHOWN))
    for res in env["results"]:
        if res["kind"] == "verify":
            lines.extend(_render_verify(res))
        elif res["kind"] == "rules":
            lines.extend(_render_rules(res))
        else:
            lines.append(json.dumps(res, ensure_ascii=False))
    files = [r for r in env["results"] if r["kind"] == "verify"]
    if len(files) > 1:
        keys = ("writes", "report", "undetermined", "passed", "findings")
        total = {k: sum(r["counts"][k] for r in files) for k in keys}
        lines.append("合计：%d 个文件、%d 处写入（报 %d、未判定 %d、通过 %d）" % (
            len(files), total["writes"], total["report"], total["undetermined"], total["passed"]))
    return "\n".join(lines)


def _emit(text, out_path):
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print("已写入 %s" % out_path)
    else:
        sys.stdout.write(text + "\n")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        results, warnings, errors = _run(args)
        env = envelope(TOOL, __version__, results=results, warnings=warnings, errors=errors)
    except EtkError as exc:
        env = envelope(TOOL, __version__, errors=[exc.to_dict()])
    except Exception as exc:  # 兜底：避免向用户抛出裸 traceback
        env = envelope(TOOL, __version__, errors=[{
            "code": E_INTERNAL,
            "message": "内部错误：%s: %s" % (exc.__class__.__name__, exc),
            "hint": "请加 --format json 复现，并把输出附在 issue 中。",
            "details": {},
        }])
    text = json.dumps(env, ensure_ascii=False, indent=2) if args.format == "json" else render_text(env)
    _emit(text, args.out)
    if not env["ok"]:
        return 1
    if args.command == "check":
        report = sum(res.get("counts", {}).get("report", 0) for res in env["results"])
        if report:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
