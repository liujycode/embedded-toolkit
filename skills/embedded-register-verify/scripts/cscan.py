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
# 厂商风格寄存器宏：TI TivaWare 的 HWREG/HWREGB/HWREGH(x)（x 为地址常量表达式）
_HWREG_RE = re.compile(r"\bHWREG(?:B|H)?\s*\(")
# 地址别名对象宏：#define NAME (*(volatile uint32_t *)0xADDR)；之后 NAME = / |= 视为对该地址的写入
_ALIAS_DEFINE_RE = re.compile(
    r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+"
    r"\(?\s*\(\s*\*\s*\(\s*" + _ADDR_TYPE + r"\s*\*\s*\)\s*" + _ADDR_VALUE + r"\s*\)\s*\)?\s*$")
_ALIAS_USE_RE = re.compile(r"\s*([A-Za-z_]\w*)\s*(\|=|&=|\^=|=)(?!=)")
_MACRO_CALL_RE = re.compile(
    r"\b(SET_BIT|CLEAR_BIT|MODIFY_REG|WRITE_REG|READ_REG"
    r"|REG_WRITE|REG_SET_BIT|REG_CLR_BIT|REG_SET_FIELD|WRITE_PERI_REG"
    r"|SET_PERI_REG_MASK|CLEAR_PERI_REG_MASK)\s*\(")
_HAL_ENABLE_RE = re.compile(r"__HAL_RCC_([A-Za-z0-9_]+?)_CLK_ENABLE\s*\(")
_GROUPING_RE = re.compile(r"\bNVIC_SetPriorityGrouping\s*\(")
_CAST_RE = re.compile(
    r"\(\s*(?:unsigned\s+)?(?:u?int(?:8|16|32|64)_t|uint\d+_t|int|long|short|char|"
    r"u8|u16|u32|u64|s8|s16|s32|s64|unsigned)\s*\)"
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
    """收集对象宏 #define NAME <表达式>（函数宏与无值宏跳过）。"""
    out = {}
    for line in clean.split("\n"):
        m = _DEFINE_RE.match(line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        if not expr:
            continue
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
    """收集"地址别名"对象宏：#define NAME (*(volatile uint32_t *)0xADDR)。

    返回 {NAME: address}；之后的 `NAME = / |= / &=` 按该地址的寄存器写入核验。
    """
    out = {}
    for line in clean.split("\n"):
        m = _ALIAS_DEFINE_RE.match(line)
        if not m:
            continue
        try:
            out[m.group(1)] = int(m.group(2), 0)
        except (TypeError, ValueError):
            continue
    return out


def extract_all(text):
    """总入口：返回 {defines, aliases, writes, enables, grouping_lines}。

    writes 每项：{kind: member|addr|addr_expr|alias|macro, op, line, code, ...}
    """
    joined, line_map = join_continuations(text)
    clean_all = strip_comments_and_strings(joined)
    defines = collect_defines(clean_all)
    aliases = collect_addr_aliases(clean_all)
    clean = blank_preprocessor(clean_all)
    writes = []
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
            macros.append({
                "kind": "macro", "op": m.group(1).lower(), "line": line,
                "code": display, "args": args,
            })
        if macros:
            writes.extend(macros)
            continue
        hw = _HWREG_RE.search(stmt)
        if hw:
            parsed = _parse_macro_args(stmt, hw.end() - 1)
            if parsed:
                args, close_pos = parsed
                op = _op_after(stmt, close_pos + 1)
                if op and args:
                    value = eval_int(args[0], defines) if args[0] else None
                    rhs = stmt[close_pos + 1:].lstrip().lstrip(op).rstrip().rstrip(";").strip()
                    if value is None:
                        writes.append({
                            "kind": "addr_expr", "op": op, "line": line, "code": display,
                            "expr": args[0][:80], "rhs": rhs,
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
            writes.append({
                "kind": "alias", "op": alias.group(2), "line": line, "code": display,
                "name": name, "address": aliases[name],
                "rhs": stmt[alias.end():].rstrip().rstrip(";").strip(),
            })
            continue
        member = _MEMBER_RE.search(stmt)
        if member:
            writes.append({
                "kind": "member", "op": member.group(3), "line": line, "code": display,
                "peripheral": member.group(1), "register": member.group(2),
                "rhs": stmt[member.end():].rstrip().rstrip(";").strip(),
            })
    enables = sorted({name.upper() for name in _HAL_ENABLE_RE.findall(clean_all)})
    grouping_lines = [_line_of(clean, m.start(), line_map) for m in _GROUPING_RE.finditer(clean)]
    return {
        "defines": defines,
        "aliases": aliases,
        "writes": writes,
        "enables": enables,
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
        if ch in "-+*/%&|^~()":
            out.append(("op", ch))
            i += 1
            continue
        return None
    return out or None


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
