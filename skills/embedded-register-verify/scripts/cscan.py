"""C 源码词法工具（核验器专用）：去注释/字符串、拼接续行、收集宏、切分语句、抽取寄存器写入。

原则（规格 0.7）：只做词法层面处理，不解析完整 C，不执行任何代码。
只对整数字面量与 #define / --define 提供的常量做受限求值；无法确定时返回 None，
由上层标"未判定"，宁可漏报不误报。
"""

from __future__ import annotations

import re

STATEMENT_MAX_CHARS = 4000
DISPLAY_MAX_CHARS = 200
DEFINE_DEPTH_MAX = 8

_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+(.+?)\s*$")
# 函数宏：#define NAME(p1, p2, ...) <表达式>（IDF 里 TIMG_RTCCALICFG_REG(i) 这类带实例参数的寄存器宏、
# libopencm3 的 GPIO_ODR(port) 这类"外设参数"宏；按 C 规范要求函数名与 "(" 之间无空格，
# 避免把 `#define X (Y) ...` 误判为函数宏）
_FUNC_DEFINE_RE = re.compile(
    r"^\s*#\s*define\s+([A-Za-z_]\w*)\(\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*\)\s+(.+?)\s*$")
_MEMBER_RE = re.compile(r"([A-Za-z_]\w*)\s*->\s*([A-Za-z_]\w*)\s*(\|=|&=|\^=|=)(?!=)")
_ADDR_QUAL = r"(?:volatile|const|__IO|__I|__O|__IM|__OM)"
_ADDR_TYPE = (r"(?:" + _ADDR_QUAL + r"\s+)*(?:unsigned\s+(?:int|long)|unsigned|"
              r"u?int(?:8|16|32|64)_t|uint\d+_t|u(?:8|16|32|64)|int|long)"
              r"(?:\s+" + _ADDR_QUAL + r")*")
_ADDR_VALUE = r"(0x[0-9A-Fa-f]+|[0-9]+)"
# 直接地址写入：C 风格 *(volatile uint32_t *)0xADDR（含双括号），C++ 风格
# *reinterpret_cast<volatile uint32_t *>(0xADDR)。组 1/2 分别是两种写法的地址。
_ADDR_RE = re.compile(
    r"(?:\*\s*\(\s*\(?\s*" + _ADDR_TYPE + r"\s*\*\s*\)\s*" + _ADDR_VALUE + r"\s*\)?"
    r"|reinterpret_cast\s*<\s*" + _ADDR_TYPE + r"\s*\*\s*>\s*\(\s*" + _ADDR_VALUE + r"\s*\))"
)
# 厂商风格地址访问宏（x 为地址常量表达式）：
#   TI TivaWare  HWREG/HWREGB/HWREGH(x)、HWREGBITW/H/B(x, bit)
#   libopencm3   MMIO8/MMIO16/MMIO32(x)
#   GD32 等      REG8/REG16/REG32(x)
#   AVR          _SFR_MEM8/16/32(x)（_SFR_IO8 不含偏移换算，靠头文件展开）
ACCESSOR_FUNCS = ("HWREG", "HWREGB", "HWREGH", "MMIO8", "MMIO16", "MMIO32",
                  "REG8", "REG16", "REG32", "_SFR_MEM8", "_SFR_MEM16", "_SFR_MEM32")
ACCESSOR_BIT_FUNCS = ("HWREGBITW", "HWREGBITH", "HWREGBITB")
_ACCESSOR_RE = re.compile(
    r"\b(?:HWREG(?:B|H)?|HWREGBIT[WBH]|MMIO(?:8|16|32)|REG(?:8|16|32)|_SFR_MEM(?:8|16|32))\s*\(")
# 对象宏的值是"地址访问宏 / 指针解引用 / 函数宏调用"形式
# （--headers 头文件里的寄存器宏，如 #define RCC_APB1ENR MMIO32(...)、
#  #define SYSCTL_RCGC2_R (*((volatile uint32_t *)(...)))、#define ADC1_CR1 ADC_CR1(ADC1)）
_ALIAS_VALUE_RE = re.compile(
    r"^\s*\(*\s*(?:"
    r"(?:HWREG(?:B|H)?|MMIO(?:8|16|32)|REG(?:8|16|32)|_SFR_MEM(?:8|16|32))\s*\("
    r"|[A-Za-z_]\w*\s*\("
    r"|\*\s*\(\s*\(?"
    r"|\*\s*reinterpret_cast\b"
    r")")
# 地址别名对象宏（两种写法）：
#   #define NAME (*(volatile uint32_t *)0xADDR)      直接指针字面量
#   #define NAME MMIO32(外设_BASE + 偏移)             访问宏 + 表达式（libopencm3/GD32 头文件风格）
# 之后 NAME = / |= / &= 按该地址的寄存器写入核验。
_ALIAS_DEFINE_RE = re.compile(
    r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+"
    r"\(?\s*\(\s*\*\s*\(\s*" + _ADDR_TYPE + r"\s*\*\s*\)\s*" + _ADDR_VALUE + r"\s*\)\s*\)?\s*$")
_ACCESSOR_ALIAS_DEFINE_RE = re.compile(
    r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+\(?\s*"
    r"(?:HWREG(?:B|H)?|MMIO(?:8|16|32)|REG(?:8|16|32)|_SFR_MEM(?:8|16|32))"
    r"\s*\((.+)\)\s*\)?\s*$")
_ALIAS_USE_RE = re.compile(r"\s*([A-Za-z_]\w*)\s*(\|=|&=|\^=|=)(?!=)")
_MACRO_CALL_RE = re.compile(
    r"\b(SET_BIT|CLEAR_BIT|MODIFY_REG|WRITE_REG|READ_REG"
    r"|REG_WRITE|REG_SET_BIT|REG_CLR_BIT|REG_SET_FIELD|REG_CLR_FIELD|WRITE_PERI_REG"
    r"|SET_PERI_REG_MASK|CLEAR_PERI_REG_MASK)\s*\(")
_HAL_ENABLE_RE = re.compile(r"__HAL_RCC_([A-Za-z0-9_]+?)_CLK_ENABLE\s*\(")
# libopencm3 风格时钟使能：rcc_periph_clock_enable(RCC_ADC1)；rcc_enable_rtc_clock()
_LOCM3_ENABLE_RE = re.compile(r"\brcc_periph_clock_enable\s*\(\s*(?:RCC_)?([A-Z][A-Z0-9_]+)\s*\)")
_LOCM3_RTC_ENABLE_RE = re.compile(r"\brcc_enable_rtc_clock\s*\(")
_GROUPING_RE = re.compile(r"\bNVIC_SetPriorityGrouping\s*\(")
# ESP-IDF 风格寄存器宏 → 写入形态（地址可由 --headers 提供的寄存器常量宏解析时）
ESP_IDF_TO_ALIAS = {
    "reg_write": "=",
    "write_peri_reg": "=",
    "reg_set_bit": "|=",
    "set_peri_reg_mask": "|=",
    "reg_clr_bit": "&=",
    "clear_peri_reg_mask": "&=",
}
# ESP-IDF 字段宏 → 字段写入形态（reg_set_field 三参：寄存器、字段、值；reg_clr_field 两参：寄存器、字段）
ESP_IDF_FIELD_OPS = {
    "reg_set_field": "set_field",
    "reg_clr_field": "clear_field",
}
# 常见"位函数"宏：按参数求值（BIT(n)=1<<n、BIT_MASK(n)=2^n-1、_BV(n)=1<<n，Arduino/AVR 风格）
BIT_FUNCS = frozenset({"BIT", "BIT_MASK", "_BV", "BIT64", "BIT_MASK64"})
_CAST_RE = re.compile(
    r"\(\s*(?:(?:volatile|const|__IO|__I|__O|__IM|__OM)\s+)*"
    r"(?:unsigned\s+)?(?:u?int(?:8|16|32|64)_t|uint\d+_t|int|long|short|char|"
    r"u8|u16|u32|u64|s8|s16|s32|s64|unsigned)"
    r"(?:\s+(?:volatile|const|__IO|__I|__O|__IM|__OM))*\s*\*{0,2}\s*\)"
)
_NUM_START_RE = re.compile(r"0[xX][0-9A-Fa-f]+|0[bB][01]+|\d+")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


def strip_comments_and_strings(text):
    """把注释与字符串/字符字面量替换为空格（等长、保留换行），避免误匹配。

    位置与原文一一对应，因此可直接用原文切片做展示。
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and nxt == "*":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
        elif ch in "\"'":
            quote = ch
            out[i] = " "
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out[i] = " "
                    if text[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                    continue
                if c == quote:
                    out[i] = " "
                    i += 1
                    break
                if c != "\n":
                    out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def join_continuations(text):
    """把反斜杠续行拼成逻辑行。返回（拼接后文本, 逻辑行号 -> 原始行号）。"""
    raw_lines = text.split("\n")
    joined = []
    line_map = []
    i = 0
    while i < len(raw_lines):
        first = i
        buf = raw_lines[i]
        while buf.rstrip().endswith("\\") and i + 1 < len(raw_lines):
            buf = buf.rstrip()[:-1] + " " + raw_lines[i + 1].lstrip()
            i += 1
        joined.append(buf)
        line_map.append(first + 1)
        i += 1
    return "\n".join(joined), line_map


def collect_defines(clean):
    """收集宏定义。

    - 对象宏 #define NAME <表达式> → {NAME: "表达式"}
    - 函数宏 #define NAME(p1, p2, ...) <表达式> → {NAME: {"params": [...], "expr": "表达式"}}
      （供 eval_int 在调用点代入实参求值；变参/复杂函数宏跳过）
    """
    out = {}
    for line in clean.split("\n"):
        m = _FUNC_DEFINE_RE.match(line)
        if m:
            name = m.group(1)
            params = [p.strip() for p in m.group(2).split(",")]
            expr = m.group(3).strip()
            if expr:
                out[name] = {"params": params, "expr": expr}
            continue
        m = _DEFINE_RE.match(line)
        if m:
            name, expr = m.group(1), m.group(2).strip()
            if expr:
                out[name] = expr
    return out


def blank_preprocessor(clean):
    """把预处理指令行整体置空（等长、保留换行），避免干扰语句切分。"""
    lines = clean.split("\n")
    return "\n".join(" " * len(line) if line.lstrip().startswith("#") else line for line in lines)


def split_statements(clean):
    """按分号切分语句（圆括号内不分；花括号与分号都算语句边界）。

    返回 [(start, end)]，区间为 [start, end) 半开；不包含预处理行。
    """
    out = []
    depth = 0
    start = None
    for i, ch in enumerate(clean):
        if start is None:
            if ch in " \t\r\n":
                continue
            start = i
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in "{};" and depth == 0:
            if ch == ";":
                out.append((start, i + 1))
            start = None
    return out


def _line_of(clean, pos, line_map):
    idx = clean.count("\n", 0, pos)
    if idx >= len(line_map):
        return line_map[-1] if line_map else 1
    return line_map[idx]


def _parse_macro_args(stmt, open_pos):
    """从 '(' 位置解析实参列表；返回 (args, end_pos) 或 None。"""
    depth = 0
    args = []
    buf = []
    i = open_pos
    while i < len(stmt):
        ch = stmt[i]
        if ch == "(":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(buf).strip())
                return args, i
        elif ch == "," and depth == 1:
            args.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        if depth >= 1:
            buf.append(ch)
        i += 1
    return None


def _op_after(stmt, pos):
    m = re.match(r"\s*(\|=|&=|\^=|=)(?!=)", stmt[pos:])
    return m.group(1) if m else None


def collect_addr_aliases(clean):
    """收集"地址别名"对象宏（两种写法）。

    - #define NAME (*(volatile uint32_t *)0xADDR)  → {"expr": "0xADDR"}
    - #define NAME MMIO32(外设_BASE + 偏移)         → {"expr": "外设_BASE + 偏移"}

    返回 {NAME: {"expr": 地址表达式}}；之后的 `NAME = / |= / &=` 在调用点解析地址后按寄存器写入核验。
    """
    out = {}
    for line in clean.split("\n"):
        m = _ALIAS_DEFINE_RE.match(line)
        if m:
            out[m.group(1)] = {"expr": m.group(2)}
            continue
        m = _ACCESSOR_ALIAS_DEFINE_RE.match(line)
        if m:
            inner = m.group(2).strip()
            if "," not in inner:  # 带位号的 HWREGBIT 别名暂不支持（地址取第一个实参）
                out[m.group(1)] = {"expr": inner}
    return out


def extract_all(text, extra_defines=None):
    """总入口：返回 {defines, aliases, writes, enables, grouping_lines}。

    extra_defines 为外部补充的宏（--define / --headers），优先于文件内定义。
    writes 每项：{kind: member|addr|addr_expr|alias|macro, op, line, code, ...}
    """
    joined, line_map = join_continuations(text)
    clean_all = strip_comments_and_strings(joined)
    defines = collect_defines(clean_all)
    if extra_defines:
        for name, expr in extra_defines.items():
            defines[name] = expr
    aliases = collect_addr_aliases(clean_all)
    clean = blank_preprocessor(clean_all)
    writes = []
    mentions = set()
    for start, end in split_statements(clean):
        if end - start > STATEMENT_MAX_CHARS:
            continue
        stmt = clean[start:end]
        display = " ".join(clean_all[start:end].split())[:DISPLAY_MAX_CHARS]
        if not display:
            continue
        line = _line_of(clean, start, line_map)
        macros = []
        for m in _MACRO_CALL_RE.finditer(stmt):
            parsed = _parse_macro_args(stmt, m.end() - 1)
            if parsed is None:
                continue
            args, _end = parsed
            op_name = m.group(1).lower()
            alias_op = ESP_IDF_TO_ALIAS.get(op_name)
            if alias_op and len(args) >= 2 and args[0]:
                # 地址可解析（常见于 --headers 带入了寄存器常量宏）→ 按"具名寄存器写入"核验
                address = eval_int(args[0], defines)
                if address is not None:
                    rhs = args[1] if alias_op != "&=" else "~(%s)" % args[1]
                    macros.append({
                        "kind": "alias", "op": alias_op, "line": line, "code": display,
                        "name": args[0][:60], "address": address, "rhs": rhs,
                    })
                    continue
            field_op = ESP_IDF_FIELD_OPS.get(op_name)
            if field_op and len(args) >= 2 and args[0]:
                # 字段宏写入：地址可解析时按"字段级"核验（存在性/只读/值位宽）
                address = eval_int(args[0], defines)
                if address is not None:
                    entry = {
                        "kind": "field_write", "op": field_op, "line": line, "code": display,
                        "name": args[0][:60], "address": address, "field_macro": args[1][:60],
                    }
                    if field_op == "set_field" and len(args) >= 3:
                        entry["value"] = args[2]
                    macros.append(entry)
                    continue
            macros.append({
                "kind": "macro", "op": op_name, "line": line,
                "code": display, "args": args,
            })
        if macros:
            writes.extend(macros)
            continue
        hw = _ACCESSOR_RE.search(stmt)
        if hw:
            parsed = _parse_macro_args(stmt, hw.end() - 1)
            if parsed:
                args, close_pos = parsed
                op = _op_after(stmt, close_pos + 1)
                if op and args:
                    expr = args[0]
                    value = eval_int(expr, defines) if expr else None
                    rhs = stmt[close_pos + 1:].lstrip().lstrip(op).rstrip().rstrip(";").strip()
                    if value is None:
                        # 位带访问（HWREGBIT*）的地址是 &变量 / 裸指针变量时，是 RAM 位带操作，不是外设寄存器写入
                        if hw.group(0).startswith("HWREGBIT") and (
                                expr.strip().startswith("&")
                                or re.match(r"^[A-Za-z_]\w*$", expr.strip())):
                            continue
                        writes.append({
                            "kind": "addr_expr", "op": op, "line": line, "code": display,
                            "expr": expr[:80], "rhs": rhs,
                        })
                    elif re.search(r"(?<![0-9A-Za-z_])[A-Za-z_]\w*", expr):
                        # 由宏表达式组合出的地址（TI TivaWare 的 HWREG(外设_BASE + 寄存器_O_XXX)）：
                        # 按"具名地址"核验（与地址别名宏同口径，不报 E08——它不是硬编码）
                        writes.append({
                            "kind": "alias", "op": op, "line": line, "code": display,
                            "name": expr[:60], "address": value, "rhs": rhs,
                        })
                    else:
                        writes.append({
                            "kind": "addr", "op": op, "line": line, "code": display,
                            "address": value, "rhs": rhs,
                        })
            continue
        addr = _ADDR_RE.search(stmt)
        if addr:
            op = _op_after(stmt, addr.end())
            if op:
                writes.append({
                    "kind": "addr", "op": op, "line": line, "code": display,
                    "address": int(addr.group(1) or addr.group(2), 0),
                    "rhs": stmt[addr.end():].lstrip().lstrip(op).rstrip().rstrip(";").strip(),
                })
            continue
        alias = _ALIAS_USE_RE.match(stmt)
        if alias and alias.group(1) in aliases:
            name = alias.group(1)
            entry = aliases[name]
            expr_text = entry["expr"] if isinstance(entry, dict) else str(entry)
            value = eval_int(expr_text, defines)
            rhs = stmt[alias.end():].rstrip().rstrip(";").strip()
            if value is None:
                writes.append({
                    "kind": "addr_expr", "op": alias.group(2), "line": line, "code": display,
                    "expr": name,
                })
            else:
                writes.append({
                    "kind": "alias", "op": alias.group(2), "line": line, "code": display,
                    "name": name, "address": value, "rhs": rhs,
                })
            continue
        call = re.match(r"\s*([A-Za-z_]\w*)\s*\(", stmt)
        if call:
            # 函数宏调用作左值：libopencm3 的 GPIO_ODR(GPIOA) |= x、GD32 的 GPIO_OCTL(GPIOA) = x
            parsed = _parse_macro_args(stmt, call.end() - 1)
            if parsed:
                _call_args, close_pos = parsed
                op = _op_after(stmt, close_pos + 1)
                if op:
                    call_text = stmt[:close_pos + 1].strip()
                    value = eval_int(call_text, defines)
                    if value is None and _find_func_define(defines, call.group(1)) is None:
                        # 不认识的函数调用后接赋值（本身不是合法 C）→ 静默忽略
                        continue
                    rhs = stmt[close_pos + 1:].lstrip().lstrip(op).rstrip().rstrip(";").strip()
                    if value is None:
                        writes.append({
                            "kind": "addr_expr", "op": op, "line": line, "code": display,
                            "expr": call_text[:80],
                        })
                    else:
                        writes.append({
                            "kind": "alias", "op": op, "line": line, "code": display,
                            "name": call_text[:60], "address": value, "rhs": rhs,
                        })
                    continue
        member = _MEMBER_RE.search(stmt)
        if member:
            writes.append({
                "kind": "member", "op": member.group(3), "line": line, "code": display,
                "peripheral": member.group(1), "register": member.group(2),
                "rhs": stmt[member.end():].rstrip().rstrip(";").strip(),
            })
            continue
        bare = re.match(r"\s*([A-Z][A-Z0-9_]{1,})\s*(\|=|&=|\^=|=)(?!=)", stmt)
        if bare:
            # 裸寄存器名（AVR/MSP430/8051/PIC 风格）：PORTB = / P1OUT |= ...
            name = bare.group(1)
            rhs = stmt[bare.end():].rstrip().rstrip(";").strip()
            entry = defines.get(name)
            if isinstance(entry, str) and _ALIAS_VALUE_RE.match(entry):
                # 名字是"地址宏"形式的对象宏（--headers 里的 libopencm3/GD32/TI/AVR 头文件）→ 按地址核验
                value = eval_int(entry, defines)
                if value is not None:
                    writes.append({
                        "kind": "alias", "op": bare.group(2), "line": line, "code": display,
                        "name": name, "address": value, "rhs": rhs,
                    })
                else:
                    # 地址宏解析不了：让核验侧决定（若名字是唯一寄存器名则按名核验，否则记未判定）
                    writes.append({
                        "kind": "bare_name", "op": bare.group(2), "line": line, "code": display,
                        "name": name, "rhs": rhs, "alias_expr": name,
                    })
                continue
            # 否则只有与设备 SVD 中唯一寄存器名精确匹配时才算寄存器写入（见 crules 裸名索引），
            # 其余按普通变量赋值静默忽略。
            writes.append({
                "kind": "bare_name", "op": bare.group(2), "line": line, "code": display,
                "name": name, "rhs": rhs,
            })
            continue
        for ident in _IDENT_RE.findall(stmt):
            mentions.add(ident)
    enables = sorted({name.upper() for name in _HAL_ENABLE_RE.findall(clean_all)}
                     | {name.upper() for name in _LOCM3_ENABLE_RE.findall(clean_all)}
                     | ({"RTC"} if _LOCM3_RTC_ENABLE_RE.search(clean_all) else set()))
    grouping_lines = [_line_of(clean, m.start(), line_map) for m in _GROUPING_RE.finditer(clean)]
    return {
        "defines": defines,
        "aliases": aliases,
        "writes": writes,
        "enables": enables,
        "mentions": sorted(mentions),
        "grouping_lines": grouping_lines,
    }


class _EvalError(Exception):
    pass


def _tokens(expr):
    text = _CAST_RE.sub(" ", expr or "")
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        m = _NUM_START_RE.match(text, i)
        if m:
            literal = m.group(0)
            i = m.end()
            while i < n and text[i] in "uUlL":
                i += 1
            out.append(("num", literal))
            continue
        m = _IDENT_RE.match(text, i)
        if m:
            out.append(("ident", m.group(0)))
            i = m.end()
            continue
        two = text[i:i + 2]
        if two in ("<<", ">>"):
            out.append(("op", two))
            i += 2
            continue
        if ch in "-+*/%&|^~(),":
            out.append(("op", ch))
            i += 1
            continue
        return None
    return out or None


def _find_func_define(defines, name):
    """在 defines 里找函数宏条目（大小写不敏感）。兼容旧的单参数形式 {"param": p}。"""
    def _ok(entry):
        return isinstance(entry, dict) and (entry.get("params") or entry.get("param"))
    entry = defines.get(name)
    if _ok(entry):
        return entry
    key = name.upper()
    for k, v in defines.items():
        if k.upper() == key and _ok(v):
            return v
    return None


def eval_int(expr, defines, depth=0, seen=None):
    """受限整数常量表达式求值；无法确定时返回 None。

    支持：十进制/0x/0b 字面量、圆括号、~ - + * / % << >> & | ^、
    #define / --define 里的名字（递归解析，带深度与环检测）。
    """
    if depth > DEFINE_DEPTH_MAX:
        return None
    tokens = _tokens(expr)
    if not tokens:
        return None
    state = {"i": 0}

    def peek():
        return tokens[state["i"]] if state["i"] < len(tokens) else (None, None)

    def advance():
        tok = peek()
        state["i"] += 1
        return tok

    def expect(op):
        kind, value = advance()
        if kind != "op" or value != op:
            raise _EvalError()

    def parse_primary():
        kind, value = peek()
        if kind == "num":
            advance()
            return int(value, 0)
        if kind == "ident":
            upper = value.upper()
            nxt = tokens[state["i"] + 1] if state["i"] + 1 < len(tokens) else (None, None)
            if upper in BIT_FUNCS and nxt[0] == "op" and nxt[1] == "(":
                # BIT(n) / BIT_MASK(n) / _BV(n) 等常见位函数
                advance()  # 函数名
                advance()  # "("
                arg = parse_or()
                expect(")")
                if arg < 0 or arg > 63:
                    raise _EvalError()
                if upper in ("BIT_MASK", "BIT_MASK64"):
                    return (1 << arg) - 1
                return 1 << arg
            if nxt[0] == "op" and nxt[1] == "(" and upper in ACCESSOR_FUNCS:
                # 地址访问宏：MMIO32(addr) / REG32(addr) / HWREG(addr) / _SFR_MEM8(addr) → 地址即实参
                advance()  # 函数名
                advance()  # "("
                result = parse_or()
                expect(")")
                return result
            if nxt[0] == "op" and nxt[1] == "(" and upper in ACCESSOR_BIT_FUNCS:
                # 位带访问宏：HWREGBITW(addr, bit) → 地址取第一个实参
                advance()  # 函数名
                advance()  # "("
                result = parse_or()
                expect(",")
                parse_or()  # 位号（求地址时忽略）
                expect(")")
                return result
            if nxt[0] == "op" and nxt[1] == "(":
                # 函数宏（单/多参数，如 TIMG_RTCCALICFG_REG(i)、GPIO_ODR(port)）：调用点代入实参求值
                entry = _find_func_define(defines, value)
                if entry is not None:
                    if upper in (seen or set()):
                        raise _EvalError()
                    advance()  # 函数名
                    advance()  # "("
                    params = entry.get("params") or [entry["param"]]
                    sub = dict(defines)
                    for idx, pname in enumerate(params):
                        if idx:
                            expect(",")
                        arg = parse_or()
                        sub[pname] = str(arg)
                    expect(")")
                    result = eval_int(entry["expr"], sub, depth + 1, (seen or set()) | {upper})
                    if result is None:
                        raise _EvalError()
                    return result
            advance()
            return resolve_name(value)
        if kind == "op" and value == "(":
            advance()
            result = parse_or()
            expect(")")
            return result
        raise _EvalError()

    def parse_unary():
        kind, value = peek()
        if kind == "op" and value == "*":
            # 解引用（求地址时等价于取被解引用的地址）：*(volatile uint32_t *)0xADDR、*((...))
            advance()
            return parse_unary()
        if kind == "op" and value in ("~", "-", "+"):
            advance()
            operand = parse_unary()
            if value == "~":
                return ~operand
            if value == "-":
                return -operand
            return operand
        return parse_primary()

    def parse_mul():
        result = parse_unary()
        while True:
            kind, value = peek()
            if kind == "op" and value in ("*", "/", "%"):
                advance()
                rhs = parse_unary()
                if value == "*":
                    result *= rhs
                elif value == "/":
                    if rhs == 0:
                        raise _EvalError()
                    result = int(result / rhs)
                else:
                    if rhs == 0:
                        raise _EvalError()
                    result %= rhs
            else:
                return result

    def parse_add():
        result = parse_mul()
        while True:
            kind, value = peek()
            if kind == "op" and value in ("+", "-"):
                advance()
                rhs = parse_mul()
                result = result + rhs if value == "+" else result - rhs
            else:
                return result

    def parse_shift():
        result = parse_add()
        while True:
            kind, value = peek()
            if kind == "op" and value in ("<<", ">>"):
                advance()
                rhs = parse_add()
                if rhs < 0 or rhs > 63:
                    raise _EvalError()
                result = result << rhs if value == "<<" else result >> rhs
            else:
                return result

    def parse_and():
        result = parse_shift()
        while True:
            kind, value = peek()
            if kind == "op" and value == "&":
                advance()
                result &= parse_shift()
            else:
                return result

    def parse_xor():
        result = parse_and()
        while True:
            kind, value = peek()
            if kind == "op" and value == "^":
                advance()
                result ^= parse_and()
            else:
                return result

    def parse_or():
        result = parse_xor()
        while True:
            kind, value = peek()
            if kind == "op" and value == "|":
                advance()
                result |= parse_xor()
            else:
                return result

    def resolve_name(name):
        key = name.upper()
        entry = defines.get(name)
        if entry is None:
            # 大小写不敏感回退只用于全大写名字（宏风格）；避免小写变量（如 adc）误撞宏（如 ADC）
            match = None
            if name == key:
                match = next((k for k in defines if k.upper() == key), None)
            if match is None:
                raise _EvalError()
            entry = defines[match]
        active = seen or set()
        if key in active:
            raise _EvalError()
        expr_text = entry["expr"] if isinstance(entry, dict) else entry
        value = eval_int(expr_text, defines, depth + 1, active | {key})
        if value is None:
            raise _EvalError()
        return value

    try:
        result = parse_or()
    except (_EvalError, ZeroDivisionError, RecursionError, ValueError, TypeError):
        return None
    if state["i"] != len(tokens):
        return None
    return result
