#!/usr/bin/env python3
"""embedded-register-lookup：按 CMSIS-SVD 查询外设、寄存器、位域、地址与寄存器值。

示例：
  python scripts/lookup.py lookup USART1.CR1.UE --chip STM32G431
  python scripts/lookup.py fields TIM1.CR1 --svd ./STM32G431xx.svd
  python scripts/lookup.py set TIM1.CR1 CEN=1 DIR=UP --chip STM32G431
  python scripts/lookup.py diff USART1.CR1 --svd-a ./F103.svd --svd-b ./G431.svd
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
__version__ = "1.2.0"
MAX_WARNINGS_SHOWN = 20


def build_parser():
    io = argparse.ArgumentParser(add_help=False)
    io.add_argument("--project-dir", metavar="DIR", help="从此目录向上查找 .etk/config.json（默认当前目录）")
    io.add_argument("--format", choices=("text", "json"), default="text", help="输出格式（默认 text）")
    io.add_argument("--out", metavar="FILE", help="把输出写入文件，而不是标准输出")

    common = argparse.ArgumentParser(add_help=False, parents=[io])
    common.add_argument("--svd", metavar="PATH", help="SVD 文件路径（优先级最高）")
    common.add_argument("--chip", metavar="NAME", help="芯片名，如 STM32G431，用于在本机 CMSIS-Pack 中查找")

    parser = argparse.ArgumentParser(prog="lookup.py", description="查询 CMSIS-SVD 中的外设、寄存器与位域。")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("lookup", parents=[common], help="查外设、寄存器或位域，如 USART1.CR1.UE（可给多个路径）")
    p.add_argument("paths", nargs="+", metavar="路径", help="外设.寄存器.位域，也可写 USART1->CR1")

    p = sub.add_parser("addr", parents=[common], help="地址反查，如 0x4001380C")
    p.add_argument("address", help="十六进制（0x 开头）或十进制地址")

    p = sub.add_parser("search", parents=[common], help="按名称或描述搜索，如 baud")
    p.add_argument("keyword")
    p.add_argument("--kind", choices=("peripheral", "register", "field"), help="只搜索某一层级")
    p.add_argument("--limit", type=int, default=50, help="最多显示条数（默认 50）")

    p = sub.add_parser("irq", parents=[common], help="查中断号：irq USART1 或 irq 37（不给参数则列出全部）")
    p.add_argument("query", nargs="?", default=None, help="中断名/外设名的一部分，或中断号")
    p.add_argument("--limit", type=int, default=100, help="最多显示条数（默认 100）")

    p = sub.add_parser("decode", parents=[common], help="按位域解码寄存器值，如 RCC.CR 0x00040002（可给多个值）")
    p.add_argument("register", help="外设.寄存器")
    p.add_argument("value", nargs="+", help="寄存器值，十六进制或十进制，可给多个")
    p.add_argument("--write", action="store_true", help="按写入方视角给提示：只读位域、未定义位、写读语义")

    p = sub.add_parser("fields", parents=[common], help="位域速查表：位范围、掩码、访问、复位（可给多个寄存器）")
    p.add_argument("paths", nargs="+", metavar="寄存器", help="外设.寄存器")

    p = sub.add_parser("diagram", parents=[common], help="寄存器位图（符号图 + 图例，可给多个寄存器）")
    p.add_argument("paths", nargs="+", metavar="寄存器", help="外设.寄存器")

    p = sub.add_parser("set", parents=[common], help="按位域赋值计算寄存器写入值，如 set TIM1.CR1 CEN=1 DIR=UP")
    p.add_argument("register", help="外设.寄存器")
    p.add_argument("assignments", nargs="+", metavar="字段=值", help="值可以是数字或字段的枚举名，可给多个")
    p.add_argument("--from", dest="from_value", default="reset", metavar="VALUE",
                   help="基准值：reset（默认，以复位值为基准）或数字")

    p = sub.add_parser("macros", parents=[common], help="生成 CMSIS 风格参考宏（_Pos/_Msk/枚举值），带出处注释")
    p.add_argument("path", help="外设、外设.寄存器 或 外设.寄存器.位域")

    p = sub.add_parser("diff", parents=[io], help="对比两份 SVD 中同一寄存器的差异（可给多个寄存器）")
    p.add_argument("registers", nargs="+", metavar="寄存器", help="外设.寄存器")
    p.add_argument("--svd-a", metavar="PATH", help="A 侧 SVD 文件路径")
    p.add_argument("--chip-a", metavar="NAME", help="A 侧芯片名（在本机 CMSIS-Pack 中查找）")
    p.add_argument("--svd-b", metavar="PATH", help="B 侧 SVD 文件路径")
    p.add_argument("--chip-b", metavar="NAME", help="B 侧芯片名（在本机 CMSIS-Pack 中查找）")

    p = sub.add_parser("range", parents=[common], help="列出地址区间内的寄存器，如 range 0x40013800 0x40013FFF")
    p.add_argument("start", help="起始地址（含）")
    p.add_argument("end", help="结束地址（含）")
    p.add_argument("--limit", type=int, default=200, help="最多显示条数（默认 200）")

    sub.add_parser("info", parents=[common], help="SVD 元信息：厂商、CPU、统计与文件哈希")
    sub.add_parser("list", parents=[common], help="列出全部外设及基地址")
    return parser


_PATH_COMMANDS = ("lookup", "fields", "diagram")
_PATH_FUNCS = {
    "lookup": query.lookup,
    "fields": query.register_fields,
    "diagram": query.diagram,
}


def _run(args):
    if args.command in ("search", "range", "irq") and args.limit < 1:
        raise EtkError(E_INPUT_INVALID, "--limit 必须大于 0")
    if args.command == "diff":
        return _run_diff(args)
    path, selected_by, notes = find_svd(args.svd, args.chip, args.project_dir)
    device = load_device(path)
    warnings = list(notes) + list(device.warnings)
    if args.command in _PATH_COMMANDS:
        fn = _PATH_FUNCS[args.command]
        results = []
        errors = []
        for item in args.paths:
            try:
                res = fn(device, item)
            except EtkError as exc:
                errors.append(exc.to_dict())
                continue
            res["source"]["selected_by"] = selected_by
            results.append(res)
        return results, warnings, errors
    if args.command == "addr":
        result = query.find_address(device, _parse(args.address, "地址"))
    elif args.command == "search":
        result = query.search(device, args.keyword, args.limit, args.kind)
    elif args.command == "irq":
        result = query.find_interrupts(device, args.query, args.limit)
    elif args.command == "decode":
        results = []
        errors = []
        for raw in args.value:
            try:
                res = query.decode(device, args.register, _parse(raw, "寄存器值"), args.write)
            except EtkError as exc:
                errors.append(exc.to_dict())
                continue
            res["source"]["selected_by"] = selected_by
            results.append(res)
        return results, warnings, errors
    elif args.command == "set":
        source_value = None if args.from_value == "reset" else _parse(args.from_value, "基准值")
        result = query.set_fields(device, args.register, args.assignments, source_value)
    elif args.command == "macros":
        result = query.macros_for(device, args.path, generator="%s v%s" % (TOOL, __version__))
    elif args.command == "range":
        result = query.find_in_range(
            device, _parse(args.start, "起始地址"), _parse(args.end, "结束地址"), args.limit)
    elif args.command == "info":
        result = query.device_info(device)
    else:
        result = query.list_peripherals(device)
    result["source"]["selected_by"] = selected_by
    return [result], warnings, []


def _run_diff(args):
    path_a, by_a, notes_a = find_svd(args.svd_a, args.chip_a, args.project_dir)
    path_b, by_b, notes_b = find_svd(args.svd_b, args.chip_b, args.project_dir)
    device_a = load_device(path_a)
    device_b = load_device(path_b)
    warnings = []
    warnings.extend("A 侧：%s" % item for item in list(notes_a) + list(device_a.warnings))
    warnings.extend("B 侧：%s" % item for item in list(notes_b) + list(device_b.warnings))
    if os.path.normcase(os.path.abspath(path_a)) == os.path.normcase(os.path.abspath(path_b)):
        warnings.append("两侧解析到同一份 SVD 文件，本次为自比对；要对比两份文件请用 --svd-a / --svd-b。")
    results = []
    errors = []
    for text in args.registers:
        try:
            result = query.diff_registers(device_a, device_b, text)
        except EtkError as exc:
            errors.append(exc.to_dict())
            continue
        result["a"]["source"]["selected_by"] = by_a
        result["b"]["source"]["selected_by"] = by_b
        results.append(result)
    return results, warnings, errors


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


def _semantics_extra(r):
    extras = []
    if r.get("write_semantics"):
        extras.append("写语义 %s" % r["write_semantics"])
    if r.get("read_semantics"):
        extras.append("读语义 %s" % r["read_semantics"])
    return extras


def _fmt_ranges(bits):
    return "、".join(
        "%d-%d" % (lo, hi) if lo != hi else "%d" % lo
        for lo, hi in query.bit_ranges(bits))


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
    if res.get("interrupts"):
        lines.append("中断：")
        for item in res["interrupts"]:
            desc = "  " + item["description"] if item["description"] else ""
            lines.append("  %-3d %-26s%s" % (item["value"], item["name"], desc))
    lines.append("寄存器（%d 个）：" % len(res["registers"]))
    for r in res["registers"]:
        lines.append("  %-6s %-12s %s  复位 %s  %s" % (
            r["offset"], r["name"], r["address"], r["reset"], r["access"]))
    lines.append(_footer(res))
    return lines


def _render_register(res):
    r = res["register"]
    head = "%s.%s  地址 %s  偏移 %s  宽度 %d 位  访问 %s  复位值 %s" % (
        res["peripheral"], r["name"], r["address"], r["offset"], r["size"], r["access"], r["reset"])
    extras = _semantics_extra(r)
    if extras:
        head += "  " + "  ".join(extras)
    lines = [head]
    if r["description"]:
        lines.append("说明：%s" % r["description"])
    if res["fields"]:
        lines.append("位域：")
        for f in res["fields"]:
            tail = _desc(f["name"], f["description"])
            if f["write_semantics"]:
                tail += ("  " if tail else "") + "写语义 %s" % f["write_semantics"]
            if f["read_semantics"]:
                tail += ("  " if tail else "") + "读语义 %s" % f["read_semantics"]
            lines.append("  bit %-6s %-12s 访问 %-11s 复位 %d  %s" % (
                f["bits"], f["name"], f["access"], f["reset"], tail))
            for e in f["enums"]:
                lines.append("        %s = %s%s" % (e["pattern"], e["name"], "  " + e["description"] if e["description"] else ""))
    lines.append(_footer(res))
    return lines


def _render_field(res):
    f = res["field"]
    r = res["register"]
    head = "%s.%s.%s  位 %s（宽 %d）  访问 %s  复位值 %d（寄存器复位 %s）" % (
        res["peripheral"], r["name"], f["name"], f["bits"], f["width"], f["access"], f["reset"], r["reset"])
    extras = _semantics_extra(f)
    if extras:
        head += "  " + "  ".join(extras)
    lines = [head]
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
    for note in res.get("write_notes", []):
        lines.append("写入提示：%s" % note)
    lines.append(_footer(res))
    return lines


def _render_irq(res):
    head = "中断列表" if not res["query"] else "中断筛选 %s" % res["query"]
    head += "：共 %d 条" % res["total"]
    if res["truncated"]:
        head += "，显示前 %d 条" % len(res["matches"])
    lines = [head]
    for m in res["matches"]:
        desc = "  " + m["description"] if m["description"] else ""
        lines.append("  %-3d  %-10s %-26s%s" % (m["value"], m["peripheral"], m["name"], desc))
    if not res["matches"]:
        lines.append("没有匹配项。可用外设名或中断名的一部分再试。")
    lines.append(_footer(res))
    return lines


def _render_macros(res):
    return res["code"].splitlines()


def _render_fields(res):
    r = res["register"]
    lines = ["%s.%s  位域速查（宽 %d 位，复位 %s，访问 %s）" % (
        res["peripheral"], r["name"], r["size"], r["reset"], r["access"])]
    for f in res["fields"]:
        lines.append("  %-9s 位 %-6s 宽 %-2d 掩码 %s  访问 %-11s 复位 %d  %s" % (
            f["name"], f["bits"], f["width"], f["mask"], f["access"], f["reset"],
            _desc(f["name"], f["description"])))
    if res["undefined_bits"]:
        lines.append("未定义位：" + _fmt_ranges(res["undefined_bits"]))
    lines.append(_footer(res))
    return lines


def _render_diagram(res):
    r = res["register"]
    size = r["size"]
    chars = ["."] * size
    for cell in res["cells"]:
        chars[cell["bit"]] = cell["char"] or "."
    seq = [chars[i] for i in range(size - 1, -1, -1)]
    groups = ["".join(seq[i:i + 8]) for i in range(0, len(seq), 8)]
    lines = ["%s.%s  位域图（宽 %d 位，复位 %s；每 8 位一组，从左到右 bit%d..bit0）" % (
        res["peripheral"], r["name"], size, r["reset"], size - 1)]
    lines.append("  " + "|".join(groups))
    if res["legend"]:
        lines.append("  图例：" + " · ".join(
            "%s=%s b%s" % (item["char"], item["field"], item["bits"]) for item in res["legend"]))
    if res["reset_bits"]:
        lines.append("  复位为 1 的位：" + _fmt_ranges(res["reset_bits"]))
    lines.append(_footer(res))
    return lines


def _render_set(res):
    r = res["register"]
    lines = ["%s.%s  写入值计算（基准：%s %s）" % (
        res["peripheral"], r["name"], res["from"]["label"], res["from"]["value_hex"])]
    for a in res["assignments"]:
        change = "%d → %d" % (a["before"], a["value"])
        tags = []
        if a["via_enum"]:
            tags.append("枚举 %s" % a["via_enum"])
        if not a["changed"]:
            tags.append("无变化")
        suffix = "（%s）" % "，".join(tags) if tags else ""
        lines.append("  %-9s 位 %-6s %-10s %s%s" % (a["field"], a["bits"], a["given"], change, suffix))
    lines.append("结果：%s（十进制 %d）" % (res["value_hex"], res["value"]))
    if res["undefined_bits_set"]:
        lines.append("注意：结果中有 SVD 未定义的位被置 1：" + _fmt_ranges(res["undefined_bits_set"]))
    for note in res["notes"]:
        lines.append("注意：" + note)
    lines.append(_footer(res))
    return lines


def _render_diff(res):
    a, b = res["a"], res["b"]
    lines = ["%s  寄存器对比" % res["path"]]
    lines.append("  A：设备 %s（%s，基地址 %s）" % (a["source"]["device"], a["source"]["file"], a["base_address"]))
    lines.append("  B：设备 %s（%s，基地址 %s）" % (b["source"]["device"], b["source"]["file"], b["base_address"]))
    if res["register_differences"]:
        lines.append("寄存器级差异：")
        for item in res["register_differences"]:
            lines.append("  " + item)
    lines.append("字段对比（%d 个字段名）：" % len(res["fields"]))
    for row in res["fields"]:
        if row["status"] == "same":
            lines.append("  %-9s 相同（位 %s）" % (row["name"], row["a"]["bits"]))
        elif row["status"] == "only_a":
            lines.append("  %-9s 仅 A 侧有（位 %s）" % (row["name"], row["a"]["bits"]))
        elif row["status"] == "only_b":
            lines.append("  %-9s 仅 B 侧有（位 %s）" % (row["name"], row["b"]["bits"]))
        else:
            for item in row["differences"]:
                lines.append("  %-9s %s" % (row["name"], item))
    lines.append("结论：" + ("两侧寄存器定义一致。" if res["identical"]
                             else "存在上述差异；跨芯片移植代码时注意位位置与访问类型。"))
    return lines


def _render_range(res):
    head = "%s – %s 区间内的寄存器：共 %d 个" % (res["start"], res["end"], res["count"])
    if res["truncated"]:
        head += "，显示前 %d 个" % len(res["registers"])
    lines = [head]
    for m in res["registers"]:
        lines.append("  %-22s %s  宽 %-2d  %-11s 复位 %s  %s" % (
            m["path"], m["address"], m["size"], m["access"], m["reset"], m["description"]))
    if not res["registers"]:
        lines.append("区间内没有 SVD 定义的寄存器。")
    lines.append(_footer(res))
    return lines


def _render_info(res):
    lines = ["设备 %s（版本 %s）" % (res["device"], res["source"]["version"])]
    if res["description"]:
        lines.append("说明：%s" % res["description"])
    meta = []
    if res["vendor"]:
        meta.append("厂商 %s" % res["vendor"])
    if res["cpu"]:
        meta.append("CPU %s" % res["cpu"])
    if meta:
        lines.append("  ".join(meta))
    lines.append("文件：%s（%d 字节，修改时间 %s）" % (
        res["source"]["file"], res["file_size"], res["mtime"]))
    lines.append("sha256：%s" % res["sha256"])
    c = res["counts"]
    lines.append("统计：外设 %d 个（派生 %d）、寄存器 %d 个、位域 %d 个、枚举值 %d 条、警告 %d 条" % (
        c["peripherals"], c["derived_peripherals"], c["registers"], c["fields"], c["enums"], c["warnings"]))
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
    "fields": _render_fields,
    "diagram": _render_diagram,
    "set": _render_set,
    "diff": _render_diff,
    "range": _render_range,
    "irq": _render_irq,
    "macros": _render_macros,
    "info": _render_info,
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
    return 0 if env["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
