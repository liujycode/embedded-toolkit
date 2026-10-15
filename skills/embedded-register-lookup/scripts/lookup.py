#!/usr/bin/env python3
"""embedded-register-lookup：按 CMSIS-SVD 查询外设、寄存器、位域、地址与寄存器值。

示例：
  python scripts/lookup.py lookup USART1.CR1.UE --chip STM32G431
  python scripts/lookup.py addr 0x4001380C --svd ./STM32G431xx.svd --format json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from etk_core import query  # noqa: E402
from etk_core.discovery import find_svd  # noqa: E402
from etk_core.errors import E_INPUT_INVALID, E_INTERNAL, EtkError  # noqa: E402
from etk_core.output import envelope  # noqa: E402
from etk_core.svd import load_device  # noqa: E402
from etk_core.values import parse_number  # noqa: E402

TOOL = "embedded-register-lookup"
__version__ = "1.0.0"
MAX_WARNINGS_SHOWN = 20


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--svd", metavar="PATH", help="SVD 文件路径（优先级最高）")
    common.add_argument("--chip", metavar="NAME", help="芯片名，如 STM32G431，用于在本机 CMSIS-Pack 中查找")
    common.add_argument("--project-dir", metavar="DIR", help="从此目录向上查找 .etk/config.json（默认当前目录）")
    common.add_argument("--format", choices=("text", "json"), default="text", help="输出格式（默认 text）")
    common.add_argument("--out", metavar="FILE", help="把输出写入文件，而不是标准输出")

    parser = argparse.ArgumentParser(prog="lookup.py", description="查询 CMSIS-SVD 中的外设、寄存器与位域。")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("lookup", parents=[common], help="查外设、寄存器或位域，如 USART1.CR1.UE")
    p.add_argument("query", help="外设.寄存器.位域，也可写 USART1->CR1")

    p = sub.add_parser("addr", parents=[common], help="地址反查，如 0x4001380C")
    p.add_argument("address", help="十六进制（0x 开头）或十进制地址")

    p = sub.add_parser("search", parents=[common], help="按名称或描述搜索，如 baud")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=50, help="最多显示条数（默认 50）")

    p = sub.add_parser("decode", parents=[common], help="按位域解码寄存器值，如 RCC.CR 0x00040002")
    p.add_argument("register", help="外设.寄存器")
    p.add_argument("value", help="寄存器值，十六进制或十进制")

    sub.add_parser("list", parents=[common], help="列出全部外设及基地址")
    return parser


def _run(args):
    if args.command == "search" and args.limit < 1:
        raise EtkError(E_INPUT_INVALID, "--limit 必须大于 0")
    path, selected_by, notes = find_svd(args.svd, args.chip, args.project_dir)
    device = load_device(path)
    warnings = list(notes) + list(device.warnings)
    if args.command == "lookup":
        result = query.lookup(device, args.query)
    elif args.command == "addr":
        result = query.find_address(device, _parse(args.address, "地址"))
    elif args.command == "search":
        result = query.search(device, args.keyword, args.limit)
    elif args.command == "decode":
        result = query.decode(device, args.register, _parse(args.value, "寄存器值"))
    else:
        result = query.list_peripherals(device)
    result["source"]["selected_by"] = selected_by
    return [result], warnings


def _parse(text, what):
    try:
        return parse_number(text)
    except ValueError:
        raise EtkError(
            E_INPUT_INVALID,
            "%s %r 无法解析" % (what, text),
            hint="使用十六进制（如 0x4001380C）或十进制数字。",
        ) from None


def _footer(res):
    src = res.get("source", {})
    text = "[%s] 来源：%s（设备 %s，版本 %s）" % (
        res.get("label", ""), src.get("file", ""), src.get("device", ""), src.get("version", ""))
    if src.get("selected_by"):
        text += "，SVD 选择方式：%s" % src["selected_by"]
    return text


def _desc(name, description):
    """描述与名称相同（不少 SVD 这样写）时不重复显示。"""
    return "" if not description or description == name else description


def _render_peripheral(res):
    head = "%s  基地址 %s  地址范围 0x%X 字节" % (res["peripheral"], res["base_address"], res["address_span"])
    extras = []
    if res.get("group"):
        extras.append("组 %s" % res["group"])
    if res.get("derived_from"):
        extras.append("派生自 %s" % res["derived_from"])
    if extras:
        head += "  " + "  ".join(extras)
    lines = [head]
    if res.get("description"):
        lines.append("说明：%s" % res["description"])
    lines.append("寄存器（%d 个）：" % len(res["registers"]))
    for r in res["registers"]:
        lines.append("  %-6s %-12s %s  复位 %s  %s" % (
            r["offset"], r["name"], r["address"], r["reset"], r["access"]))
    lines.append(_footer(res))
    return lines


def _render_register(res):
    r = res["register"]
    lines = ["%s.%s  地址 %s  偏移 %s  宽度 %d 位  访问 %s  复位值 %s" % (
        res["peripheral"], r["name"], r["address"], r["offset"], r["size"], r["access"], r["reset"])]
    if r["description"]:
        lines.append("说明：%s" % r["description"])
    if res["fields"]:
        lines.append("位域：")
        for f in res["fields"]:
            lines.append("  bit %-6s %-12s 访问 %-11s 复位 %d  %s" % (
                f["bits"], f["name"], f["access"], f["reset"], _desc(f["name"], f["description"])))
            for e in f["enums"]:
                lines.append("        %s = %s%s" % (e["pattern"], e["name"], "  " + e["description"] if e["description"] else ""))
    lines.append(_footer(res))
    return lines


def _render_field(res):
    f = res["field"]
    r = res["register"]
    lines = ["%s.%s.%s  位 %s（宽 %d）  访问 %s  复位值 %d（寄存器复位 %s）" % (
        res["peripheral"], r["name"], f["name"], f["bits"], f["width"], f["access"], f["reset"], r["reset"])]
    if f["description"]:
        lines.append("说明：%s" % f["description"])
    if f["enums"]:
        lines.append("枚举：")
        for e in f["enums"]:
            lines.append("  %s = %s%s" % (e["pattern"], e["name"], "  " + e["description"] if e["description"] else ""))
    lines.append(_footer(res))
    return lines


def _render_cluster(res):
    lines = ["%s.%s（簇，%d 个寄存器）  基地址 %s" % (
        res["peripheral"], res["cluster"], len(res["registers"]), res["base_address"])]
    for r in res["registers"]:
        lines.append("  %-6s %-12s %s  复位 %s  %s" % (r["offset"], r["name"], r["address"], r["reset"], r["access"]))
    lines.append(_footer(res))
    return lines


def _render_address(res):
    kind = res["kind"]
    if kind == "exact":
        lines = ["%s 是寄存器地址：" % res["address"]]
        for m in res["matches"]:
            lines.append("  %s  偏移 %s  访问 %s  复位 %s  %s" % (
                m["path"], m["offset"], m["access"], m["reset"], m["description"]))
    elif kind == "inside_register":
        n = res["nearest"]
        lines = ["%s 位于寄存器 %s 内部（第 %d 字节，寄存器宽 %d 位）" % (
            res["address"], n["path"], n["offset_in_register"], n["size"])]
    elif kind == "gap":
        if res["nearest"]:
            n = res["nearest"]
            lines = ["%s 不是寄存器地址。最近的寄存器：%s（%s），之后 %d 字节。" % (
                res["address"], n["path"], n["address"], n["offset_in_register"])]
        else:
            lines = ["%s 不是寄存器地址，位于 %s 内，前面没有寄存器定义。" % (res["address"], res["peripheral"])]
        lines.append("SVD 中此处未定义寄存器，可能是保留区。")
    else:
        lines = ["%s 不在 SVD 定义的任何外设地址范围内。" % res["address"]]
    lines.append(_footer(res))
    return lines


def _render_search(res):
    head = "关键词 %s：共 %d 条" % (res["keyword"], res["total"])
    if res["truncated"]:
        head += "，显示前 %d 条" % len(res["matches"])
    lines = [head]
    for m in res["matches"]:
        desc = "  " + m["description"] if m["description"] else ""
        lines.append("  [%s] %s%s" % (m["kind"], m["path"], desc))
    if not res["matches"]:
        lines.append("没有匹配项。可换用英文缩写或寄存器名再试。")
    lines.append(_footer(res))
    return lines


def _render_decode(res):
    r = res["register"]
    lines = ["%s.%s  值 %s（十进制 %d）  宽 %d 位" % (
        res["peripheral"], r["name"], res["value_hex"], res["value"], r["size"])]
    for f in res["fields"]:
        enum = "  → %s" % f["enum"] if f["enum"] else ""
        lines.append("  bit %-6s %-12s = %-6s%s  %s" % (
            f["bits"], f["name"], f["value_hex"], enum, _desc(f["name"], f["description"])))
    if res["undefined_bits"]:
        lines.append("未定义位（SVD 中没有对应位域）：" + "、".join("bit %d" % b for b in res["undefined_bits"]))
    lines.append(_footer(res))
    return lines


def _render_list(res):
    lines = ["设备 %s：共 %d 个外设" % (res["device"], res["count"])]
    for p in res["peripherals"]:
        extra = "  派生自 %s" % p["derived_from"] if p["derived_from"] else ""
        lines.append("  %-12s %s  %d 个寄存器%s  %s" % (
            p["name"], p["base_address"], p["register_count"], extra, p["description"]))
    lines.append(_footer(res))
    return lines


_RENDERERS = {
    "peripheral": _render_peripheral,
    "register": _render_register,
    "field": _render_field,
    "cluster": _render_cluster,
    "search": _render_search,
    "decode": _render_decode,
    "list": _render_list,
    "exact": _render_address,
    "inside_register": _render_address,
    "gap": _render_address,
    "unmapped": _render_address,
}


def render_text(env):
    lines = []
    for err in env["errors"]:
        lines.append("错误 [%s] %s" % (err["code"], err["message"]))
        if err.get("hint"):
            lines.append("  提示：%s" % err["hint"])
        details = err.get("details") or {}
        if details.get("tried"):
            lines.extend("  已尝试：%s" % item for item in details["tried"])
    warnings = env["warnings"]
    for w in warnings[:MAX_WARNINGS_SHOWN]:
        lines.append("注意：%s" % w)
    if len(warnings) > MAX_WARNINGS_SHOWN:
        lines.append("注意：另有 %d 条警告，用 --format json 查看全部" % (len(warnings) - MAX_WARNINGS_SHOWN))
    for res in env["results"]:
        renderer = _RENDERERS.get(res["kind"])
        if renderer is None:
            lines.append(json.dumps(res, ensure_ascii=False))
            continue
        lines.extend(renderer(res))
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
        results, warnings = _run(args)
        env = envelope(TOOL, __version__, results=results, warnings=warnings)
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
    return 0 if env["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
