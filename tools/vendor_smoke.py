#!/usr/bin/env python3
"""厂商 SVD 冒烟（本地基准，规格 §2.8 的"其它厂商样本"）。

对给定目录里的每个 .svd 做三件事：
  1) lint：SVD 质量检查（error / warning 计数）；
  2) 查询：取一个"全大写命名"的外设 + 读写寄存器做一次字段级查询；
  3) 核验：构造片段「合法写 / 假字段宏 / 超宽值」，
     预期恰好 E03 + E04 两条"报"、其余 0 条。

用法：
  python tools/vendor_smoke.py --dir <SVD 目录> [--limit N] [--format text|md|json]
说明：SVD 由使用者自备（本仓库不打包厂商文件）；结果可整理进 benchmarks/vendor-svds.md。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, "shared")
SCRIPTS = os.path.join(ROOT, "skills", "embedded-register-verify", "scripts")
for _p in (SHARED, SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import crules  # noqa: E402
from etk_core import query as etk_query  # noqa: E402
from etk_core.errors import EtkError  # noqa: E402
from etk_core.svd import load_device  # noqa: E402

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
CORE_NAMES = {"NVIC", "SCB", "SYSTICK", "MPU", "FPU", "DWT", "ITM", "TPIU"}


def pick_targets(device):
    """挑一个"全大写命名"的外设与其中的读写寄存器；挑不到返回 None。"""
    for periph in sorted(device.peripherals, key=lambda p: p.name):
        if not NAME_RE.match(periph.name) or periph.name.upper() in CORE_NAMES:
            continue
        for reg in sorted(periph.registers, key=lambda r: r.offset):
            name = reg.name
            if not NAME_RE.match(name):
                continue
            if reg.access not in ("read-write", "read-writeOnce", None):
                continue
            if reg.size not in (8, 16, 32):
                continue
            return periph, reg
    return None


def smoke_one(path):
    item = {"file": os.path.basename(path), "device": None, "lint_errors": None,
            "lint_warnings": None, "query": "skip", "verify": "skip", "detail": ""}
    try:
        device = load_device(path)
    except Exception as exc:  # 解析失败：如实记录
        item["detail"] = "解析失败：%s: %s" % (exc.__class__.__name__, exc)
        item["verify"] = "fail"
        return item
    item["device"] = device.name
    try:
        lint = etk_query.lint(device)
        findings = lint.get("findings", [])
        item["lint_errors"] = sum(1 for f in findings if f.get("severity") == "error")
        item["lint_warnings"] = sum(1 for f in findings if f.get("severity") == "warning")
    except Exception as exc:
        item["detail"] = "lint 异常：%r" % exc
    targets = pick_targets(device)
    if targets is None:
        item["query"] = "skip"
        item["verify"] = "skip"
        item["detail"] = (item["detail"] + "；" if item["detail"] else "") + "没有全大写命名的读写寄存器"
        return item
    periph, reg = targets
    item["target"] = "%s.%s" % (periph.name, reg.name)
    try:
        data = etk_query.lookup(device, item["target"])
        item["query"] = "ok" if data.get("kind") == "register" else "fail"
    except EtkError as exc:
        item["query"] = "fail"
        item["detail"] = "查询失败：%s" % exc.message
    macro = "%s_%s_ZZZ" % (periph.name, reg.name)
    over = 1 << reg.size
    text = ("void smoke(void)\n{\n"
            "    %s->%s |= 0;\n"
            "    %s->%s |= %s;\n"
            "    %s->%s = 0x%X;\n"
            "}\n" % (periph.name, reg.name, periph.name, reg.name, macro,
                     periph.name, reg.name, over))
    try:
        res = crules.Verifier(device, clock_check=False).check_file("smoke.c", text)
        classes = sorted(f["class"] for f in res["findings"])
        if classes == ["E03", "E04"] and res["counts"]["report"] == 2:
            item["verify"] = "ok"
        else:
            item["verify"] = "fail"
            shown = "、".join("%s: %s" % (f["class"], f["message"][:60]) for f in res["findings"][:3])
            item["detail"] = (item["detail"] + "；" if item["detail"] else "") + \
                "核验得到 %s（期望 E03+E04）%s" % (classes, ("：" + shown) if shown else "")
    except Exception as exc:
        item["verify"] = "fail"
        item["detail"] = (item["detail"] + "；" if item["detail"] else "") + "核验异常：%r" % exc
    return item


def collect(directory, limit):
    files = []
    for root, _dirs, names in os.walk(directory):
        for name in sorted(names):
            if name.lower().endswith(".svd"):
                files.append(os.path.join(root, name))
    files.sort()
    if limit:
        files = files[:limit]
    return [smoke_one(path) for path in files]


def render_text(items):
    lines = ["%-42s %-12s %-6s %-6s %-6s %-6s %s" % (
        "文件", "设备", "错", "警", "查询", "核验", "备注")]
    for item in items:
        lines.append("%-42s %-12s %-6s %-6s %-6s %-6s %s" % (
            item["file"][:42], (item["device"] or "-")[:12],
            item["lint_errors"] if item["lint_errors"] is not None else "-",
            item["lint_warnings"] if item["lint_warnings"] is not None else "-",
            item["query"], item["verify"], item["detail"][:80]))
    ok = sum(1 for item in items if item["verify"] == "ok")
    fail = sum(1 for item in items if item["verify"] == "fail")
    skip = sum(1 for item in items if item["verify"] == "skip")
    lines.append("合计：%d 个，核验冒烟通过 %d，失败 %d，跳过 %d" % (
        len(items), ok, fail, skip))
    return "\n".join(lines)


def render_md(items):
    lines = ["| SVD | 设备 | lint 错/警 | 查询 | 核验冒烟 | 备注 |",
             "|---|---|---|---|---|---|"]
    for item in items:
        verdict = {"ok": "✅", "fail": "❌"}.get(item["verify"], "跳过")
        lines.append("| %s | %s | %s/%s | %s | %s | %s |" % (
            item["file"], item["device"] or "-",
            item["lint_errors"] if item["lint_errors"] is not None else "-",
            item["lint_warnings"] if item["lint_warnings"] is not None else "-",
            item["query"], verdict,
            item["detail"].replace("|", "/")[:110]))
    ok = sum(1 for item in items if item["verify"] == "ok")
    fail = sum(1 for item in items if item["verify"] == "fail")
    skip = sum(1 for item in items if item["verify"] == "skip")
    lines.append("")
    lines.append("合计：**%d** 个厂商 SVD，核验冒烟通过 **%d**，失败 %d，跳过 %d。" % (
        len(items), ok, fail, skip))
    return "\n".join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="厂商 SVD 冒烟（本地基准）")
    parser.add_argument("--dir", required=True, help="SVD 目录（递归查找 .svd）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个文件")
    parser.add_argument("--format", choices=("text", "md", "json"), default="text")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.dir):
        print("目录不存在：%s" % args.dir)
        return 1
    items = collect(args.dir, args.limit)
    if not items:
        print("目录里没有 .svd：%s" % args.dir)
        return 1
    if args.format == "json":
        print(json.dumps({"kind": "vendor-smoke", "items": items}, ensure_ascii=False, indent=2))
    elif args.format == "md":
        print(render_md(items))
    else:
        print(render_text(items))
    ok = sum(1 for item in items if item["verify"] == "ok")
    return 0 if ok == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
