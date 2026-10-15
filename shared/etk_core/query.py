"""SVD 查询：外设、寄存器、位域、地址反查、关键词搜索、寄存器值解码。

函数只读 Device，不做 I/O。错误用 EtkError 抛出，由调用方统一输出。
"""

from __future__ import annotations

import difflib
from collections import OrderedDict

from .errors import E_FIELD_NOT_FOUND, E_INPUT_INVALID, E_PERIPH_NOT_FOUND, E_REG_NOT_FOUND, EtkError
from .output import LABEL_VERIFIED, source_meta


def hex_addr(value):
    return "0x%08X" % value


def hex_offset(value):
    return "0x%02X" % value


def hex_reset(value, size):
    return "0x%0*X" % (max(1, size // 4), value)


def split_query(text):
    raw = (text or "").strip().replace("->", ".")
    parts = [p.strip() for p in raw.split(".")]
    if not raw or any(not p for p in parts):
        raise EtkError(
            E_INPUT_INVALID,
            "查询格式不正确：%r" % text,
            hint="格式为 外设.寄存器.位域，例如 USART1.CR1.UE；也可以写 USART1->CR1。",
        )
    return parts


def suggest(name, candidates, limit=3):
    """候选名：先取前缀匹配，再取相近拼写。"""
    orig = OrderedDict()
    for cand in candidates:
        orig.setdefault(cand.upper(), cand)
    key = name.upper()
    picked = [v for k, v in orig.items() if k.startswith(key)]
    for k in difflib.get_close_matches(key, list(orig), n=limit, cutoff=0.6):
        if orig[k] not in picked:
            picked.append(orig[k])
    return picked[:limit]


def _periph_or_raise(device, name):
    periph = device.peripheral(name)
    if periph is None:
        sugg = suggest(name, [p.name for p in device.peripherals])
        hint = "检查拼写；可用 list 子命令列出全部外设。"
        if sugg:
            hint += "你可能要找：%s。" % "、".join(sugg)
        raise EtkError(
            E_PERIPH_NOT_FOUND,
            "在 %s 中找不到外设 %s" % (device.name, name),
            hint=hint,
            details={"suggestions": sugg},
        )
    return periph


def _register_missing(periph, name):
    sugg = suggest(name, [r.name for r in periph.registers])
    owners = [] if "." in name else [r for r in periph.registers if r.field(name) is not None]
    hint = "检查拼写；可用 search 子命令按关键词查找。"
    if owners:
        hint = "%s 是位域而不是寄存器，位于 %s 中，请写成 %s.%s.%s。" % (
            name, "、".join(o.name for o in owners[:3]), periph.name, owners[0].name, name)
    elif sugg:
        hint += "你可能要找：%s。" % "、".join(sugg)
    return EtkError(
        E_REG_NOT_FOUND,
        "%s 中找不到寄存器 %s" % (periph.name, name),
        hint=hint,
        details={"suggestions": sugg},
    )


def _pattern(value, mask, width):
    out = []
    for i in range(width - 1, -1, -1):
        if (mask >> i) & 1:
            out.append("1" if (value >> i) & 1 else "0")
        else:
            out.append("x")
    return "".join(out)


def _reg_dict(periph, reg):
    return {
        "name": reg.name,
        "offset": hex_offset(reg.offset),
        "address": hex_addr(periph.base_address + reg.offset),
        "size": reg.size,
        "access": reg.access,
        "reset": hex_reset(reg.reset_value, reg.size),
        "reset_mask": hex_reset(reg.reset_mask, reg.size),
        "description": reg.description,
    }


def _field_dict(item, reg_reset):
    return {
        "name": item.name,
        "bits": item.bit_text,
        "lsb": item.lsb,
        "msb": item.msb,
        "width": item.width,
        "access": item.access,
        "description": item.description,
        "reset": (reg_reset >> item.lsb) & item.mask,
        "enums": [
            {
                "name": e.name,
                "value": e.value,
                "pattern": _pattern(e.value, e.mask, item.width),
                "description": e.description,
            }
            for e in item.enums
        ],
    }


def resolve_register(device, text):
    parts = split_query(text)
    periph = _periph_or_raise(device, parts[0])
    if len(parts) < 2:
        raise EtkError(E_INPUT_INVALID, "需要指定寄存器，例如 RCC.CR", hint="格式为 外设.寄存器。")
    name = ".".join(parts[1:])
    reg = periph.register(name)
    if reg is None:
        if len(parts) >= 3 and periph.register(".".join(parts[1:-1])) is not None:
            raise EtkError(
                E_INPUT_INVALID,
                "此处需要寄存器，但 %s 是位域" % text,
                hint="去掉最后一段，改为 %s.%s。" % (periph.name, ".".join(parts[1:-1])),
            )
        raise _register_missing(periph, name)
    return periph, reg


def lookup(device, text):
    parts = split_query(text)
    periph = _periph_or_raise(device, parts[0])
    source = source_meta(device)
    if len(parts) == 1:
        return _periph_result(periph, source)
    rest = parts[1:]
    full = ".".join(rest)
    reg = periph.register(full)
    if reg is not None:
        return _register_result(periph, reg, source)
    if len(rest) >= 2:
        owner = periph.register(".".join(rest[:-1]))
        if owner is not None:
            fld = owner.field(rest[-1])
            if fld is None:
                sugg = suggest(rest[-1], [f.name for f in owner.fields])
                hint = "可用 lookup %s.%s 查看全部位域。" % (periph.name, owner.name)
                if sugg:
                    hint += "你可能要找：%s。" % "、".join(sugg)
                raise EtkError(
                    E_FIELD_NOT_FOUND,
                    "%s.%s 中没有位域 %s" % (periph.name, owner.name, rest[-1]),
                    hint=hint,
                    details={"suggestions": sugg},
                )
            return _field_result(periph, owner, fld, source)
    prefix = full.upper() + "."
    members = [r for r in periph.registers if r.name.upper().startswith(prefix)]
    if members:
        return _cluster_result(periph, full, members, source)
    raise _register_missing(periph, ".".join(rest[:-1]) if len(rest) >= 2 else rest[0])


def _periph_result(periph, source):
    return {
        "kind": "peripheral",
        "peripheral": periph.name,
        "base_address": hex_addr(periph.base_address),
        "group": periph.group_name,
        "derived_from": periph.derived_from,
        "description": periph.description,
        "address_span": periph.address_span,
        "registers": [_reg_dict(periph, r) for r in periph.registers],
        "label": LABEL_VERIFIED,
        "source": source,
    }


def _register_result(periph, reg, source):
    return {
        "kind": "register",
        "peripheral": periph.name,
        "base_address": hex_addr(periph.base_address),
        "register": _reg_dict(periph, reg),
        "fields": [_field_dict(f, reg.reset_value) for f in reg.fields],
        "label": LABEL_VERIFIED,
        "source": source,
    }


def _field_result(periph, reg, fld, source):
    return {
        "kind": "field",
        "peripheral": periph.name,
        "base_address": hex_addr(periph.base_address),
        "register": _reg_dict(periph, reg),
        "field": _field_dict(fld, reg.reset_value),
        "label": LABEL_VERIFIED,
        "source": source,
    }


def _cluster_result(periph, cluster, members, source):
    return {
        "kind": "cluster",
        "peripheral": periph.name,
        "base_address": hex_addr(periph.base_address),
        "cluster": cluster,
        "registers": [_reg_dict(periph, r) for r in members],
        "label": LABEL_VERIFIED,
        "source": source,
    }


def find_address(device, address):
    source = source_meta(device)
    base = {"address": hex_addr(address), "label": LABEL_VERIFIED, "source": source}
    matches = []
    for periph in device.peripherals:
        for reg in periph.registers:
            if periph.base_address + reg.offset == address:
                matches.append({
                    "path": "%s.%s" % (periph.name, reg.name),
                    "peripheral": periph.name,
                    "register": reg.name,
                    "offset": hex_offset(reg.offset),
                    "access": reg.access,
                    "reset": hex_reset(reg.reset_value, reg.size),
                    "description": reg.description,
                })
    if matches:
        return dict(base, kind="exact", matches=matches)
    for periph in device.peripherals:
        if periph.address_span <= 0:
            continue
        if not (periph.base_address <= address < periph.base_address + periph.address_span):
            continue
        below = [(periph.base_address + r.offset, r) for r in periph.registers
                 if periph.base_address + r.offset <= address]
        if not below:
            return dict(base, kind="gap", peripheral=periph.name, nearest=None)
        abs_addr, reg = max(below, key=lambda item: item[0])
        delta = address - abs_addr
        kind = "inside_register" if delta < reg.nbytes else "gap"
        nearest = {
            "path": "%s.%s" % (periph.name, reg.name),
            "register": reg.name,
            "address": hex_addr(abs_addr),
            "offset_in_register": delta,
            "size": reg.size,
        }
        return dict(base, kind=kind, peripheral=periph.name, nearest=nearest)
    return dict(base, kind="unmapped", peripheral=None, nearest=None)


def _rank(keyword, name, description):
    low = name.lower()
    if low == keyword:
        return 0
    if keyword in low:
        return 1
    if description and keyword in description.lower():
        return 2
    return None


def search(device, keyword, limit=50):
    kw = (keyword or "").strip().lower()
    if not kw:
        raise EtkError(E_INPUT_INVALID, "搜索关键词不能为空", hint="例如 search baud 或 search DMA。")
    hits = []
    for periph in device.peripherals:
        rank = _rank(kw, periph.name, periph.description)
        if rank is not None:
            hits.append((rank, periph.name, "peripheral", periph.name, periph.description))
        for reg in periph.registers:
            path = "%s.%s" % (periph.name, reg.name)
            rank = _rank(kw, reg.name, reg.description)
            if rank is not None:
                hits.append((rank, path, "register", path, reg.description))
            for fld in reg.fields:
                rank = _rank(kw, fld.name, fld.description)
                if rank is not None:
                    fpath = "%s.%s" % (path, fld.name)
                    hits.append((rank, fpath, "field", fpath, fld.description))
    hits.sort(key=lambda h: (h[0], h[1]))
    matches = [
        {"kind": kind, "path": path, "description": desc, "label": LABEL_VERIFIED}
        for _, _, kind, path, desc in hits[:limit]
    ]
    return {
        "kind": "search",
        "keyword": keyword,
        "total": len(hits),
        "truncated": len(hits) > limit,
        "matches": matches,
        "label": LABEL_VERIFIED,
        "source": source_meta(device),
    }


def decode(device, text, value):
    periph, reg = resolve_register(device, text)
    size_mask = (1 << reg.size) - 1
    if value < 0 or value > size_mask:
        raise EtkError(
            E_INPUT_INVALID,
            "值 0x%X 超出 %d 位寄存器 %s.%s 的范围" % (value, reg.size, periph.name, reg.name),
            hint="寄存器宽 %d 位，取值范围 0 到 0x%X。" % (reg.size, size_mask),
        )
    covered = 0
    rows = []
    for fld in reg.fields:
        covered |= fld.mask << fld.lsb
        fv = (value >> fld.lsb) & fld.mask
        enum = next((e for e in fld.enums if (fv & e.mask) == e.value), None)
        rows.append({
            "name": fld.name,
            "bits": fld.bit_text,
            "value": fv,
            "value_hex": "0x%X" % fv,
            "enum": enum.name if enum else None,
            "enum_description": enum.description if enum else "",
            "description": fld.description,
        })
    undefined = [i for i in range(reg.size) if (value >> i) & 1 and not (covered >> i) & 1]
    return {
        "kind": "decode",
        "peripheral": periph.name,
        "base_address": hex_addr(periph.base_address),
        "register": _reg_dict(periph, reg),
        "value": value,
        "value_hex": hex_reset(value, reg.size),
        "fields": rows,
        "undefined_bits": undefined,
        "label": LABEL_VERIFIED,
        "source": source_meta(device),
    }


def list_peripherals(device):
    return {
        "kind": "list",
        "device": device.name,
        "count": len(device.peripherals),
        "peripherals": [
            {
                "name": p.name,
                "base_address": hex_addr(p.base_address),
                "derived_from": p.derived_from,
                "group": p.group_name,
                "register_count": len(p.registers),
                "description": p.description,
            }
            for p in device.peripherals
        ],
        "label": LABEL_VERIFIED,
        "source": source_meta(device),
    }
