"""核验规则 E01–E11：用 SVD 检查 C 源码里的寄存器写入。

判定口径（规格 §2.5）：不确定时一律进"未判定"，宁可漏报不误报。
标签：E01–E05、E08、E10 = 已核验；E06、E07、E09 = 需查手册。
"""

from __future__ import annotations

import difflib
import re

import cscan
from etk_core.output import source_meta

CORE_PERIPHERALS = frozenset({
    "NVIC", "NVIC_STIR", "SYSTICK", "STK", "SCB", "MPU", "FPU", "DWT", "ITM", "TPIU",
    "COREDEBUG", "DCB", "DIB",
})
ESP_IDF_OPS = frozenset({
    "reg_write", "reg_set_bit", "reg_clr_bit", "reg_set_field", "write_peri_reg",
    "set_peri_reg_mask", "clear_peri_reg_mask",
})
_EN_MACRO_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_(?:EN|ENABLE)\b")
_DMA_CONFIG_REGS = frozenset({"CNDTR", "NDTR", "CMAR", "CPAR"})
# DMA 控制寄存器（EN 恒为 bit0）：CCR（ST 通道）、CR（ST 流）、CHCTL（GD32）、CTL（部分厂商）
_DMA_CTRL_REGS = frozenset({"CCR", "CR", "CHCTL", "CTL"})
EXT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
IDENT_WORD_RE = re.compile(r"\b([A-Za-z_]\w*)\b")
MEMBER_ARG_RE = re.compile(r"^(&)?\s*([A-Za-z_]\w*)\s*->\s*([A-Za-z_]\w*)\s*$")
TILDE_MACRO_RE = re.compile(r"^~\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")
MEASURED_PREFIXES = ("DMA", "NVIC", "SYSTICK", "STK")


def looks_like_macro(name):
    """判断标识符是否像寄存器宏：全大写，或带 _Msk/_Pos 等后缀的驼峰写法。"""
    if not name or not name[0].isupper() or "_" not in name:
        return False
    if name.upper() == name:
        return True
    return name.endswith(("_Msk", "_Mask", "_MSK", "_MASK", "_Pos", "_POS"))


def macro_words(expr):
    return [m.group(1) for m in IDENT_WORD_RE.finditer(expr or "")
            if looks_like_macro(m.group(1))]

_SEVERITY = {"E01": "高", "E02": "高", "E03": "高", "E04": "高", "E05": "中",
             "E06": "低", "E07": "中", "E08": "高", "E09": "中", "E10": "高", "E11": "中"}
_LABELS = {"E01": "已核验", "E02": "已核验", "E03": "已核验", "E04": "已核验", "E05": "已核验",
           "E06": "需查手册", "E07": "需查手册", "E08": "已核验", "E09": "需查手册",
           "E10": "已核验", "E11": "需查手册"}

RULES = [
    {"class": "E01", "name": "外设不存在", "verdict": "SVD 中查外设名", "bucket": "报", "label": "已核验", "severity": "高"},
    {"class": "E02", "name": "寄存器不存在", "verdict": "SVD 中查寄存器名", "bucket": "报", "label": "已核验", "severity": "高"},
    {"class": "E03", "name": "位域宏不存在或与寄存器不符", "verdict": "CMSIS 命名映射后查 SVD", "bucket": "报", "label": "已核验", "severity": "高"},
    {"class": "E04", "name": "值超出宽度", "verdict": "值与寄存器/位域宽度比较", "bucket": "报", "label": "已核验", "severity": "高"},
    {"class": "E05", "name": "枚举值不合法", "verdict": "SVD enumeratedValues 校验", "bucket": "报", "label": "已核验", "severity": "中"},
    {"class": "E06", "name": "无效清位", "verdict": "清位域但复位为 0 且本文件未见置位", "bucket": "报", "label": "需查手册", "severity": "低"},
    {"class": "E07", "name": "访问前未见时钟使能", "verdict": "RCC 中 <外设>EN 位是否置位", "bucket": "报", "label": "需查手册", "severity": "中"},
    {"class": "E08", "name": "硬编码地址", "verdict": "直接地址写入（并用地址反查命名）", "bucket": "报", "label": "已核验", "severity": "高"},
    {"class": "E09", "name": "中断分组多处设置", "verdict": "NVIC_SetPriorityGrouping 出现次数", "bucket": "报", "label": "需查手册", "severity": "中"},
    {"class": "E10", "name": "写只读寄存器或位域", "verdict": "SVD access 为 read-only", "bucket": "报", "label": "已核验", "severity": "高"},
    {"class": "E11", "name": "使能后写 DMA 配置寄存器", "verdict": "使能（EN=1）后写 CNDTR/CMAR/CPAR 等", "bucket": "报", "label": "需查手册", "severity": "中"},
]


def _lookup_hint(action, **kwargs):
    """核验结果 → 寄存器百事通 的查证提示（CLI 会把它物化成可直接执行的 next 命令）。"""
    return dict(action=action, **kwargs)


def rule_table():
    return {
        "kind": "rules",
        "rules": RULES,
        "note": "不确定的内容一律进\"未判定\"；E06/E07/E09 依赖约定，标注为\"需查手册\"。",
    }


class Verifier:
    def __init__(self, device, extra_defines=None, clock_check=True, limit=200):
        self.device = device
        self.extra_defines = dict(extra_defines or {})
        self.clock_check = clock_check
        self.limit = limit
        self.peripherals = {p.name.upper(): p for p in device.peripherals}
        self._addr_map = None

    # ---------- 基础映射 ----------

    def _periph(self, name):
        key = name.upper()
        periph = self.peripherals.get(key)
        if periph is None and key.startswith("NRF_"):
            # Nordic SDK 约定：nrf.h 用 NRF_<外设> 作为 SVD 外设名的别名（如 NRF_USBD → USBD）
            periph = self.peripherals.get(key[4:])
        if periph is None and key.startswith("R_"):
            # Renesas RA/FSP 约定：R_<外设> 为 SVD 外设名的别名（如 R_PORT0 → PORT0）
            periph = self.peripherals.get(key[2:])
        return periph

    def _by_address(self):
        if self._addr_map is None:
            self._addr_map = {}
            for periph in self.device.peripherals:
                for reg in periph.registers:
                    self._addr_map.setdefault(periph.base_address + reg.offset, (periph, reg))
        return self._addr_map

    def _suggest_names(self, name, names, limit=3):
        by_upper = {}
        for item in names:
            by_upper.setdefault(item.upper(), item)
        picked = difflib.get_close_matches(name.upper(), list(by_upper), n=limit, cutoff=0.6)
        return [by_upper[k] for k in picked]

    def _find_registers(self, periph, name):
        key = name.upper()
        exact = [r for r in periph.registers if r.name.upper() == key]
        if exact:
            return exact
        return [r for r in periph.registers if r.name.upper().startswith(key + "_")]

    def _resolve_field(self, reg, field_tokens):
        """返回 (field, kind, value)：kind 为 field / enum / extra（位域名后多出无法识别的后缀）。"""
        joined = "_".join(field_tokens)
        field = reg.field(joined)
        if field is not None:
            return field, "field", None
        for cut in range(len(field_tokens) - 1, 0, -1):
            base = "_".join(field_tokens[:cut])
            field = reg.field(base)
            if field is None:
                continue
            trailing = "_".join(field_tokens[cut:])
            for enum in field.enums:
                if enum.name and enum.name.upper() == trailing.upper():
                    return field, "enum", enum.value
            return field, "extra", None
        return None, None, None

    def _map_macro(self, name, periph, context_reg=None):
        """CMSIS 风格宏 → 外设内的寄存器/位域。

        返回：{"register", "field", "kind", "value"}；
        寄存器可判定但位域不匹配时 {"register", "missing": "字段名", "extra": bool}；
        完全无法映射时 None。
        """
        upper = name.upper()
        for suf in ("_MSK", "_MASK", "_POS", "_SHIFT"):
            if upper.endswith(suf):
                upper = upper[: -len(suf)]
                break
        tokens = upper.split("_")
        if len(tokens) < 2:
            return None
        family = {periph.name.upper()}
        stripped = periph.name.upper().rstrip("0123456789")
        if stripped:
            family.add(stripped)
        if periph.name.isalpha() and len(periph.name) >= 4:
            family.add(periph.name.upper()[:-1])  # GPIOA -> GPIO
        head = periph.name.upper().split("_")[0]
        family.add(head)
        family.add(head.rstrip("0123456789"))
        # 先试最长的前缀：外设名本身可能带下划线（RTC_CNTL_RTC_ULP_CP_TIMER_ZZZ → RTC_CNTL）
        start = 0
        for size in range(min(4, len(tokens) - 2), 0, -1):
            if "_".join(tokens[:size]) in family:
                start = size
                break
        if start == 0 and tokens[0] in family:
            start = 1
        rest = tokens[start:]
        if len(rest) < 2:
            return None
        fallback = None
        for cut in range(1, len(rest)):
            reg_tokens = rest[:cut]
            field_tokens = rest[cut:]
            for reg in self._find_registers(periph, "_".join(reg_tokens)):
                field, kind, value = self._resolve_field(reg, field_tokens)
                if field is not None and kind in ("field", "enum"):
                    return {"register": reg, "field": field, "kind": kind, "value": value}
                if field is not None and kind == "extra" and fallback is None:
                    fallback = {"register": reg, "missing": "_".join(field_tokens), "extra": True}
                elif fallback is None:
                    fallback = {"register": reg, "missing": "_".join(field_tokens), "extra": False}
        return fallback

    def _target(self, write):
        """解析写入目标，返回 (periph, reg, problem)。

        problem 为 None 表示可判定；否则为 {"core"|"clusterish"|"unknown"|"bad_arg": 名称}；
        返回 (None, None, None) 表示按本地指针处理（静默忽略）。
        """
        if write["kind"] == "alias":
            hit = self._by_address().get(write.get("address"))
            if hit is None:
                return None, None, {"alias_addr": (write.get("name") or "?", write.get("address") or 0)}
            return hit[0], hit[1], None
        if write["kind"] == "field_write":
            hit = self._by_address().get(write.get("address"))
            if hit is None:
                return None, None, {"alias_addr": (write.get("name") or "?", write.get("address") or 0)}
            return hit[0], hit[1], None
        if write["kind"] == "addr_expr":
            return None, None, {"addr_expr": write.get("expr") or "?"}
        if write["kind"] == "addr":
            hit = self._by_address().get(write["address"])
            if hit is None:
                return None, None, {"address": write["address"]}
            return hit[0], hit[1], None
        if write["kind"] == "macro" and write.get("op") in ESP_IDF_OPS:
            # ESP-IDF 等风格：第一个参数是寄存器号常量（定义在 SDK 头文件里），不解析头文件
            return None, None, {"esp_idf": write["op"]}
        if write["kind"] == "macro":
            args = write.get("args") or []
            if not args:
                return None, None, {"bad_arg": ""}
            m = MEMBER_ARG_RE.match(args[0])
            if not m:
                return None, None, {"bad_arg": args[0]}
            periph_name, reg_name = m.group(2), m.group(3)
        else:
            periph_name, reg_name = write["peripheral"], write["register"]
        periph = self._periph(periph_name)
        if periph is None:
            key = periph_name.upper()
            if key in CORE_PERIPHERALS:
                return None, None, {"core": periph_name}
            if any(key.startswith(name + "_") for name in self.peripherals):
                return None, None, {"clusterish": periph_name}
            if EXT_NAME_RE.match(periph_name):
                return None, None, {"unknown": periph_name}
            return None, None, None
        reg = periph.register(reg_name)
        if reg is None:
            if periph.name.upper() in CORE_PERIPHERALS:
                return None, None, {"core_reg": "%s.%s" % (periph.name, reg_name)}
            prefix = reg_name.upper() + "."
            if any(r.name.upper().startswith(prefix) for r in periph.registers):
                return None, None, {"cluster_reg": "%s.%s" % (periph_name, reg_name)}
            return periph, None, None
        return periph, reg, None

    # ---------- 位域触碰分析（用于 E06/E07） ----------

    def _fields_for_expr(self, expr, periph, context_reg, defines):
        """表达式里出现的位域宏 → (mapped_fields, missing_list, unmapped_macros, value)。"""
        mapped = []
        missing = []
        unmapped = []
        for name in macro_words(expr):
            if name.upper() in cscan.BIT_FUNCS:
                continue  # BIT(n)/BIT_MASK(n) 等位函数：按整体表达式求值，不当作宏映射
            if cscan.eval_int(name, defines) is not None:
                continue  # 文件内/--define 能解析的数值宏，不是位域宏
            result = self._map_macro(name, periph, context_reg)
            if result and result.get("field") is not None:
                mapped.append((name, result["field"], result))
            elif result and result.get("missing"):
                missing.append((name, result))
            else:
                unmapped.append(name)
        value = cscan.eval_int(expr, defines) if expr else None
        return mapped, missing, unmapped, value

    # ---------- 主流程 ----------

    def check_file(self, name, text):
        parsed = cscan.extract_all(text, self.extra_defines)
        defines = dict(parsed["defines"])
        defines.update(self.extra_defines)
        findings = []
        undetermined = []
        defaults = []
        sets = set()
        unknown_set_regs = set()
        periph_first = {}
        rcc_enabled = set()
        hal_enables = set(parsed["enables"])
        write_buckets = []
        write_lines = []

        def add_undet(write, reason):
            undetermined.append({
                "line": write["line"], "code": write["code"], "reason": reason,
            })
            state["undet"] = True

        def add_finding(write, cls, message, suggestion=None, periph=None, register=None,
                        field=None, lookup=None):
            findings.append({
                "class": cls, "bucket": "报",
                "severity": _SEVERITY[cls], "label": _LABELS[cls],
                "line": write["line"], "code": write["code"], "message": message,
                "suggestion": suggestion,
                "peripheral": periph, "register": register, "field": field,
                "lookup": lookup,
            })
            state["report"] = True

        state = {"report": False, "undet": False}

        # 第一遍：收集"置位"信息与时钟使能（供 E06/E07 使用）
        for write in parsed["writes"]:
            periph, reg, problem = self._target(write)
            if write["kind"] == "macro" and write["op"] == "read_reg":
                continue
            if periph is None or reg is None:
                continue
            periph_first.setdefault(periph.name.upper(), (write["line"], write["code"]))
            if write["kind"] == "macro":
                args = write.get("args") or []
                if write["op"] == "set_bit" and len(args) >= 2:
                    mapped, _missing, _unmapped, _value = self._fields_for_expr(args[1], periph, reg, defines)
                    for _macro, field, _info in mapped:
                        sets.add((periph.name.upper(), reg.name.upper(), field.name.upper()))
                    if periph.name.upper() == "RCC":
                        for _macro, field, _info in mapped:
                            rcc_enabled.add(field.name.upper())
                elif write["op"] in ("write_reg", "modify_reg") and len(args) >= 2:
                    expr = args[2] if write["op"] == "modify_reg" and len(args) >= 3 else args[1]
                    mapped, _missing, _unmapped, value = self._fields_for_expr(expr, periph, reg, defines)
                    for _macro, field, _info in mapped:
                        sets.add((periph.name.upper(), reg.name.upper(), field.name.upper()))
                        if periph.name.upper() == "RCC":
                            rcc_enabled.add(field.name.upper())
                    if value is not None and value >= 0:
                        for field in reg.fields:
                            if value & (field.mask << field.lsb):
                                sets.add((periph.name.upper(), reg.name.upper(), field.name.upper()))
                                if periph.name.upper() == "RCC":
                                    rcc_enabled.add(field.name.upper())
            else:
                rhs = write.get("rhs") or ""
                if write["op"] == "|=":
                    mapped, _missing, _unmapped, value = self._fields_for_expr(rhs, periph, reg, defines)
                    for _macro, field, _info in mapped:
                        sets.add((periph.name.upper(), reg.name.upper(), field.name.upper()))
                        if periph.name.upper() == "RCC":
                            rcc_enabled.add(field.name.upper())
                    if value is not None and value >= 0:
                        for field in reg.fields:
                            if value & (field.mask << field.lsb):
                                sets.add((periph.name.upper(), reg.name.upper(), field.name.upper()))
                                if periph.name.upper() == "RCC":
                                    rcc_enabled.add(field.name.upper())
                elif write["op"] == "=":
                    value = cscan.eval_int(rhs, defines) if rhs else None
                    if value is not None and value >= 0:
                        for field in reg.fields:
                            if value & (field.mask << field.lsb):
                                sets.add((periph.name.upper(), reg.name.upper(), field.name.upper()))
                                if periph.name.upper() == "RCC":
                                    rcc_enabled.add(field.name.upper())
                    else:
                        unknown_set_regs.add((periph.name.upper(), reg.name.upper()))

        # 文件级规则：E07 时钟使能（在第二遍之前算好，便于归入对应写入的"报"桶）
        clock_lines = set()
        if self.clock_check:
            for item in self._clock_findings(periph_first, rcc_enabled, hal_enables):
                findings.append({
                    "class": "E07", "bucket": "报",
                    "severity": _SEVERITY["E07"], "label": _LABELS["E07"],
                    "line": item["line"], "code": item["code"],
                    "message": item["message"], "suggestion": item["suggestion"],
                    "peripheral": item["peripheral"], "register": None, "field": None,
                    "lookup": item.get("lookup"),
                })
                clock_lines.add(item["line"])

        # 第二遍：逐条核验
        index = 0
        for write in parsed["writes"]:
            if write["kind"] == "macro" and write["op"] == "read_reg":
                continue
            state["report"] = write["line"] in clock_lines
            state["undet"] = False
            self._check_write(
                write, defines, add_finding, add_undet,
                sets, unknown_set_regs, defaults, periph_first)
            if state["report"]:
                write_buckets.append("报")
            elif state["undet"]:
                write_buckets.append("未判定")
            else:
                write_buckets.append("通过")
            write_lines.append(write["line"])
            index += 1

        if len(parsed["grouping_lines"]) > 1:
            lines_text = "、".join(str(n) for n in parsed["grouping_lines"])
            findings.append({
                "class": "E09", "bucket": "报",
                "severity": _SEVERITY["E09"], "label": _LABELS["E09"],
                "line": parsed["grouping_lines"][0], "code": "NVIC_SetPriorityGrouping(...)",
                "message": "本文件有 %d 处 NVIC_SetPriorityGrouping（第 %s 行），中断分组应只设置一次" % (
                    len(parsed["grouping_lines"]), lines_text),
                "suggestion": "保留一处分组设置；多处设置会互相覆盖，需确认哪一处生效。",
                "peripheral": None, "register": None, "field": None,
                "lookup": None,
            })

        # 文件级规则：E11 使能后写 DMA 计数/地址寄存器（文本级，不依赖外设名能否解析）
        for item in self._enable_order_findings(parsed["writes"], defines):
            findings.append({
                "class": "E11", "bucket": "报",
                "severity": _SEVERITY["E11"], "label": _LABELS["E11"],
                "line": item["line"], "code": item["code"],
                "message": "使能 %s 后（第 %d 行）又写 %s.%s（第 %d 行）；"
                           "DMA 的计数/地址寄存器通常需在 EN=0 时写，写入可能被硬件忽略" % (
                               item["periph"], item["en_line"], item["periph"],
                               item["reg"], item["line"]),
                "suggestion": "调整顺序：先写 %s，再置 EN；或先清 EN、改完配置再置回。" % item["reg"],
                "peripheral": item["periph"], "register": item["reg"], "field": None,
                "lookup": _lookup_hint("lookup", path="%s.%s" % (item["periph"], item["reg"]),
                                       reason="查看该寄存器的复位值与写约束"),
            })

        findings.sort(key=lambda f: (f["line"], f["class"]))
        total = index
        report = write_buckets.count("报")
        undetermined_writes = write_buckets.count("未判定")
        passed = write_buckets.count("通过")
        checklist = None
        if getattr(self, "checklist", False):
            default_lines = {item["line"] for item in defaults}
            verified = sum(
                1 for line, bucket in zip(write_lines, write_buckets)
                if bucket == "通过" and line not in default_lines)
            checklist = {
                "chip_default": defaults,
                "verified": verified,
                "manual": [f for f in findings if f["label"] == "需查手册"] + [
                    {"line": u["line"], "code": u["code"], "reason": u["reason"]} for u in undetermined
                ],
                "measured": [
                    {"line": w["line"], "code": w["code"]}
                    for w in parsed["writes"]
                    if self._measured_write(w)
                ],
            }
        return {
            "kind": "verify",
            "file": name,
            "counts": {
                "writes": total,
                "report": report,
                "undetermined": undetermined_writes,
                "passed": passed,
                "findings": len(findings),
            },
            "findings": findings[: self.limit],
            "findings_truncated": len(findings) > self.limit,
            "undetermined": undetermined[: self.limit],
            "undetermined_truncated": len(undetermined) > self.limit,
            "checklist": checklist,
            "source": source_meta(self.device),
        }

    # ---------- 单条写入核验 ----------

    def _check_write(self, write, defines, add_finding, add_undet, sets,
                     unknown_set_regs, defaults, periph_first):
        op = write["op"]
        periph, reg, problem = self._target(write)
        if problem:
            if "core" in problem:
                add_undet(write, "%s 是 Cortex-M 内核外设，不在设备 SVD 中，未检查" % problem["core"])
            elif "core_reg" in problem:
                add_undet(write, "%s 是内核外设寄存器（设备 SVD 中通常不完整），未检查" % problem["core_reg"])
            elif "clusterish" in problem:
                add_undet(write, "%s 可能对应 SVD 中的簇寄存器（如 DMA1 的 CHx），命名无法自动对应，未检查" % problem["clusterish"])
            elif "unknown" in problem:
                names = [p.name for p in self.device.peripherals]
                suggestion = self._suggest_names(problem["unknown"], names)
                add_finding(write, "E01",
                            "外设 %s 在设备 %s 的 SVD 中不存在" % (problem["unknown"], self.device.name),
                            suggestion=("你可能要找：" + "、".join(suggestion)) if suggestion else None,
                            periph=problem["unknown"],
                            lookup=_lookup_hint("search", keyword=problem["unknown"],
                                                reason="按名字搜索相近外设"))
            elif "cluster_reg" in problem:
                add_undet(write, "%s 是簇寄存器（SVD 中命名为 %s.x），未检查" % (
                    problem["cluster_reg"], problem["cluster_reg"]))
            elif "address" in problem:
                add_finding(write, "E08", "硬编码地址 0x%08X（SVD 中未找到对应寄存器）" % problem["address"],
                            lookup=_lookup_hint("addr", address="0x%08X" % problem["address"],
                                                reason="用地址反查寄存器"))
            elif "alias_addr" in problem:
                name, addr = problem["alias_addr"]
                add_undet(write, "别名 %s 的地址 0x%X 在 SVD 中找不到对应寄存器，未检查" % (name, addr))
            elif "addr_expr" in problem:
                add_undet(write, "地址表达式无法解析（%s），未检查" % problem["addr_expr"])
            elif "bad_arg" in problem:
                add_undet(write, "宏的第一个参数不是 外设->寄存器 形式：%r" % problem["bad_arg"])
            elif "esp_idf" in problem:
                add_undet(write, "ESP-IDF 风格寄存器宏（%s）：寄存器号来自头文件常量，无法定位，未检查"
                          % problem["esp_idf"])
            return
        if periph is None:
            return
        if reg is None:
            periph_label, reg_label = self._names(write)
            names = [r.name for r in periph.registers]
            suggestion = self._suggest_names(reg_label or "", names)
            add_finding(write, "E02",
                        "%s 中不存在寄存器 %s" % (periph.name, reg_label or "?"),
                        suggestion=("同外设寄存器：" + "、".join(suggestion)) if suggestion else None,
                        periph=periph.name, register=reg_label,
                        lookup=_lookup_hint("lookup", path=periph.name,
                                            reason="查看该外设的寄存器清单"))
            return
        if write["kind"] == "field_write":
            self._check_field_write(write, periph, reg, defines, add_finding)
            return
        if write["kind"] == "addr":
            hit = self._by_address()[write["address"]]
            add_finding(write, "E08",
                        "硬编码地址 0x%08X（= %s.%s），建议改用外设结构体或宏" % (
                            write["address"], hit[0].name, hit[1].name),
                        periph=hit[0].name, register=hit[1].name,
                        lookup=_lookup_hint("addr", address="0x%08X" % write["address"],
                                            reason="用地址反查寄存器（= %s.%s）" % (hit[0].name, hit[1].name)))
        if write["kind"] == "macro":
            self._check_macro(write, periph, reg, defines, add_finding, add_undet, sets, unknown_set_regs)
            return
        # member / addr 的直接读写
        register_read_only = reg.access == "read-only"
        if register_read_only:
            add_finding(write, "E10",
                        "%s.%s 是只读寄存器，写入不会生效" % (periph.name, reg.name),
                        periph=periph.name, register=reg.name,
                        lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                            reason="查看该寄存器的完整定义"))
        rhs = write.get("rhs") or ""
        mapped, missing, unmapped, value = self._fields_for_expr(rhs, periph, reg, defines)
        for macro_name, info in missing:
            self._report_macro_mismatch(write, periph, reg, macro_name, info, add_finding)
        for macro_name, field, info in mapped:
            if self._report_register_mismatch(write, periph, reg, macro_name, info, add_finding):
                continue
            if field.access == "read-only" and not register_read_only and op in ("=", "|=", "^="):
                add_finding(write, "E10",
                            "位域 %s.%s.%s 是只读，写入不会生效" % (periph.name, reg.name, field.name),
                            periph=periph.name, register=reg.name, field=field.name,
                            lookup=_lookup_hint("lookup", path="%s.%s.%s" % (periph.name, reg.name, field.name),
                                                reason="查看该位域的访问属性"))
        if unmapped:
            add_undet(write, "无法映射的标识符（按 CMSIS 命名约定找不到位域）：%s" % "、".join(sorted(set(unmapped))[:6]))
        if value is not None and value >= 0:
            limit_value = (1 << reg.size) - 1
            if value > limit_value:
                add_finding(write, "E04",
                            "值 0x%X 超出 %s.%s 的 %d 位宽度（最大 0x%X）" % (
                                value, periph.name, reg.name, reg.size, limit_value),
                            periph=periph.name, register=reg.name,
                            lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                                reason="查看该寄存器宽度与位域"))
            if not register_read_only:
                for field in reg.fields:
                    field_bits = value & (field.mask << field.lsb)
                    if field_bits and field.access == "read-only":
                        add_finding(write, "E10",
                                    "%s.%s 中的只读位域 %s 被写入（值 0x%X）" % (
                                        periph.name, reg.name, field.name, value),
                                    periph=periph.name, register=reg.name, field=field.name,
                                    lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                        periph.name, reg.name, field.name),
                                        reason="查看该位域的访问属性"))
            if op == "=" and value == reg.reset_value:
                defaults.append({"line": write["line"], "code": write["code"],
                                 "note": "写入值与复位值相同，可能等于没写"})
        if op == "&=" and reg is not None:
            m = TILDE_MACRO_RE.match(rhs.strip())
            if m:
                info = self._map_macro(m.group(1), periph, reg)
                field = info.get("field") if info else None
                if field is not None:
                    reset_bits = (reg.reset_value >> field.lsb) & field.mask
                    key = (periph.name.upper(), reg.name.upper(), field.name.upper())
                    if reset_bits == 0 and key not in sets and (periph.name.upper(), reg.name.upper()) not in unknown_set_regs:
                        add_finding(write, "E06",
                                    "清除位域 %s.%s.%s，但其复位值为 0 且本文件未见置位，可能是无效清位" % (
                                        periph.name, reg.name, field.name),
                                    periph=periph.name, register=reg.name, field=field.name,
                                    lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                        periph.name, reg.name, field.name),
                                        reason="查看该位域的复位值"))

    def _measured_write(self, write):
        text = " ".join([
            write.get("peripheral") or "",
            write.get("register") or "",
            " ".join(write.get("args") or []),
            write["code"],
        ]).upper()
        if "SYSTICK" in text:
            return True
        return any(prefix in text for prefix in MEASURED_PREFIXES)

    def _names(self, write):
        """取写入的 (外设名, 寄存器名) 文本（宏形态从第一个参数解析）。"""
        if write["kind"] == "macro":
            args = write.get("args") or []
            m = MEMBER_ARG_RE.match(args[0]) if args else None
            if m:
                return m.group(2), m.group(3)
            return None, None
        if write["kind"] == "addr":
            return None, None
        return write.get("peripheral"), write.get("register")

    def _find_field_by_macro(self, reg, macro):
        """字段宏文本 → reg 中的位域（从严到宽）。

        1) 整名 / 各段后缀精确匹配（CMSIS 命名）；
        2) 后缀词集合 ⊆ 位域名词集合（容忍 SVD 多出/插入词，如
           SENS_FORCE_XPD_SAR → SAR_FORCE_XPD_SAR、RTC_CNTL_SDIO_PD_EN → SDIO_REG_PD_EN）；
           该级必须唯一命中，否则继续放宽；词数少于 2 时不再放宽（避免乱撞）；
        3) 仍无 → None（上层报 E03）。
        """
        text = (macro or "").strip().upper()
        if not text:
            return None
        lowered = {f.name.upper(): f for f in reg.fields}
        parts = text.split("_")
        for i in range(len(parts)):
            hit = lowered.get("_".join(parts[i:]))
            if hit is not None:
                return hit
        field_tokens = {name: set(name.split("_")) for name in lowered}
        for i in range(1, len(parts)):
            want = set(parts[i:])
            if len(want) < 2:
                break
            hits = [lowered[name] for name, tokens in field_tokens.items()
                    if want <= tokens and len(tokens) - len(want) <= 2]
            if len(hits) == 1:
                return hits[0]
        return None

    def _check_field_write(self, write, periph, reg, defines, add_finding):
        """REG_SET_FIELD / REG_CLR_FIELD（地址已由 --headers 解析）：字段存在性、只读、值位宽。"""
        macro = write.get("field_macro") or ""
        field = self._find_field_by_macro(reg, macro)
        if field is None:
            add_finding(write, "E03",
                        "字段宏 %s 在 %s.%s 中不存在（按 CMSIS 命名找不到对应位域）" % (
                            macro, periph.name, reg.name),
                        periph=periph.name, register=reg.name, field=macro,
                        lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                            reason="查看该寄存器的位域清单"))
            return
        if reg.access == "read-only":
            add_finding(write, "E10",
                        "%s.%s 是只读寄存器，写入不会生效" % (periph.name, reg.name),
                        periph=periph.name, register=reg.name, field=field.name,
                        lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                            reason="查看该寄存器的访问属性"))
            return
        if field.access == "read-only":
            add_finding(write, "E10",
                        "位域 %s.%s.%s 是只读，写入不会生效" % (periph.name, reg.name, field.name),
                        periph=periph.name, register=reg.name, field=field.name,
                        lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                            periph.name, reg.name, field.name),
                            reason="查看该位域的访问属性"))
        if write.get("op") != "set_field":
            return
        value_expr = write.get("value")
        value = cscan.eval_int(value_expr, defines) if value_expr else None
        if value is not None and value >= 0 and field.width < 64:
            limit_value = (1 << field.width) - 1
            if value > limit_value:
                add_finding(write, "E04",
                            "值 0x%X 超出位域 %s.%s.%s 的 %d 位宽（最大 0x%X）" % (
                                value, periph.name, reg.name, field.name, field.width, limit_value),
                            periph=periph.name, register=reg.name, field=field.name,
                            lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                periph.name, reg.name, field.name),
                                reason="查看该位域的宽度"))
            elif field.enums and not any((value & e.mask) == e.value for e in field.enums):
                options = "、".join(e.name for e in field.enums if e.name)
                add_finding(write, "E05",
                            "值 0x%X 不是位域 %s.%s.%s 的合法枚举（可选：%s）" % (
                                value, periph.name, reg.name, field.name, options),
                            periph=periph.name, register=reg.name, field=field.name,
                            lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                periph.name, reg.name, field.name),
                                reason="查看该位域的枚举取值"))

    def _report_register_mismatch(self, write, periph, reg, macro_name, info, add_finding):
        """宏映射到了同外设的另一个寄存器时返回 True（已报告 E03）。"""
        target = info.get("register")
        if target is None or target.name.upper() == reg.name.upper():
            return False
        add_finding(write, "E03",
                    "宏 %s 属于 %s.%s，而此处写入的是 %s" % (
                        macro_name, periph.name, target.name, reg.name),
                    periph=periph.name, register=reg.name,
                    lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                        reason="查看此处写入的寄存器与宏所属寄存器"))
        return True

    def _report_macro_mismatch(self, write, periph, reg, macro_name, info, add_finding):
        target = info.get("register")
        if target is not None and target.name.upper() != reg.name.upper():
            add_finding(write, "E03",
                        "宏 %s 属于 %s.%s，而此处写入的是 %s" % (
                            macro_name, periph.name, target.name, reg.name),
                        periph=periph.name, register=reg.name,
                        lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                            reason="查看此处写入的寄存器与宏所属寄存器"))
            return
        fields = [f.name for f in reg.fields]
        suggestion = self._suggest_names(info.get("missing") or macro_name, fields)
        if info.get("extra"):
            message = "宏 %s 中位域名 %s 与 %s.%s 的位域不匹配（可能拼写错误）" % (
                macro_name, info.get("missing") or "?", periph.name, reg.name)
        else:
            message = "宏 %s 对应的位域 %s 在 %s.%s 中不存在" % (
                macro_name, info.get("missing") or "?", periph.name, reg.name)
        add_finding(write, "E03", message,
                    suggestion=("同寄存器位域：" + "、".join(suggestion)) if suggestion else None,
                    periph=periph.name, register=reg.name,
                    lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                        reason="查看该寄存器的全部位域"))

    def _check_macro(self, write, periph, reg, defines, add_finding, add_undet, sets, unknown_set_regs):
        op = write["op"]
        args = write.get("args") or []
        reported = set()  # 一条语句内 E10 只读位域去重（宏参数与数值两条路径）
        if reg.access == "read-only":
            add_finding(write, "E10", "%s.%s 是只读寄存器，写入不会生效" % (periph.name, reg.name),
                        periph=periph.name, register=reg.name,
                        lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                            reason="查看该寄存器的访问属性"))
        if op in ("set_bit", "clear_bit"):
            if len(args) < 2:
                add_undet(write, "宏参数不足，无法核验")
                return
            self._check_macro_mask(write, periph, reg, args[1], op, defines,
                                   add_finding, add_undet, sets, unknown_set_regs, reported)
        elif op == "modify_reg":
            if len(args) < 3:
                add_undet(write, "宏参数不足，无法核验")
                return
            self._check_macro_mask(write, periph, reg, args[1], "modify_clear", defines,
                                   add_finding, add_undet, sets, unknown_set_regs, reported)
            self._check_modify_value(write, periph, reg, args[1], args[2], defines,
                                     add_finding, add_undet, reported)
        elif op == "write_reg":
            if len(args) < 2:
                add_undet(write, "宏参数不足，无法核验")
                return
            self._check_macro_mask(write, periph, reg, args[1], "write_reg", defines,
                                   add_finding, add_undet, sets, unknown_set_regs, reported)

    def _check_macro_mask(self, write, periph, reg, expr, mode, defines,
                          add_finding, add_undet, sets, unknown_set_regs, reported):
        mapped, missing, unmapped, value = self._fields_for_expr(expr, periph, reg, defines)
        for macro_name, _info in missing:
            self._report_macro_mismatch(write, periph, reg, macro_name, _info, add_finding)
        mapped_names = set()
        for macro_name, field, _info in mapped:
            mapped_names.add(field.name.upper())
            if self._report_register_mismatch(write, periph, reg, macro_name, _info, add_finding):
                continue
            if field.access == "read-only" and reg.access != "read-only":
                reported.add(field.name.upper())
                add_finding(write, "E10",
                            "位域 %s.%s.%s 是只读，写入不会生效" % (periph.name, reg.name, field.name),
                            periph=periph.name, register=reg.name, field=field.name,
                            lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                periph.name, reg.name, field.name), reason="查看该位域的访问属性"))
        if unmapped:
            add_undet(write, "无法映射的标识符（%s 参数）：%s" % (
                mode, "、".join(sorted(set(unmapped))[:6])))
        if value is not None and value >= 0:
            if value > (1 << reg.size) - 1:
                add_finding(write, "E04",
                            "掩码/值 0x%X 超出 %s.%s 的 %d 位宽度" % (value, periph.name, reg.name, reg.size),
                            periph=periph.name, register=reg.name,
                            lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                                reason="查看该寄存器宽度"))
            if mode != "modify_clear":  # MODIFY_REG 的清除掩码不算写入，置位值在 _check_modify_value 里查
                self._report_readonly_value(write, periph, reg, value, add_finding, reported, mapped_names)
            if mode in ("clear_bit", "modify_clear") and value and not any(
                    field.mask << field.lsb & value for field in reg.fields):
                add_undet(write, "清位掩码 0x%X 不覆盖任何 SVD 位域" % value)
        if mode == "clear_bit":
            for macro_name, field, _info in mapped:
                reset_bits = (reg.reset_value >> field.lsb) & field.mask
                key = (periph.name.upper(), reg.name.upper(), field.name.upper())
                if reset_bits == 0 and key not in sets and (periph.name.upper(), reg.name.upper()) not in unknown_set_regs:
                    add_finding(write, "E06",
                                "清除位域 %s.%s.%s，但其复位值为 0 且本文件未见置位，可能是无效清位" % (
                                    periph.name, reg.name, field.name),
                                periph=periph.name, register=reg.name, field=field.name,
                                lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                    periph.name, reg.name, field.name), reason="查看该位域的复位值"))

    def _check_modify_value(self, write, periph, reg, clear_expr, set_expr, defines,
                            add_finding, add_undet, reported):
        mapped, _missing, _unmapped, _v = self._fields_for_expr(clear_expr, periph, reg, defines)
        value = cscan.eval_int(set_expr, defines)
        if value is None:
            return
        if value < 0:
            add_undet(write, "MODIFY_REG 的置位值为负/无法确定，未检查宽度与枚举")
            return
        if len(mapped) == 1:
            field = mapped[0][1]
            if value > field.mask:
                add_finding(write, "E04",
                            "置位值 0x%X 超出位域 %s 的 %d 位宽度（最大 0x%X）" % (
                                value, field.name, field.width, field.mask),
                            periph=periph.name, register=reg.name, field=field.name,
                            lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                periph.name, reg.name, field.name), reason="查看该位域宽度与枚举"))
            elif field.enums and not any((value & e.mask) == e.value for e in field.enums):
                options = "、".join(e.name for e in field.enums if e.name)
                add_finding(write, "E05",
                            "值 0x%X 不是位域 %s 的合法枚举（可选：%s）" % (value, field.name, options),
                            periph=periph.name, register=reg.name, field=field.name,
                            lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                                periph.name, reg.name, field.name), reason="查看该位域的枚举取值"))
        elif value > (1 << reg.size) - 1:
            add_finding(write, "E04",
                        "置位值 0x%X 超出 %s.%s 的 %d 位宽度" % (value, periph.name, reg.name, reg.size),
                        periph=periph.name, register=reg.name,
                        lookup=_lookup_hint("lookup", path="%s.%s" % (periph.name, reg.name),
                                            reason="查看该寄存器宽度"))
        mapped_names = {item[1].name.upper() for item in mapped}
        self._report_readonly_value(write, periph, reg, value, add_finding, reported, mapped_names)

    def _report_readonly_value(self, write, periph, reg, value, add_finding, reported, mapped_names=None):
        """数值参数触碰到只读位域 → E10（与结构体写路径同一口径；一条语句内去重）。"""
        if value is None or value < 0 or reg.access == "read-only":
            return
        skip = set(mapped_names or ())
        for field in reg.fields:
            if field.access != "read-only":
                continue
            key = field.name.upper()
            if key in skip or key in reported:
                continue
            if not (value & (field.mask << field.lsb)):
                continue
            reported.add(key)
            add_finding(write, "E10",
                        "%s.%s 中的只读位域 %s 被写入（值 0x%X）" % (
                            periph.name, reg.name, field.name, value),
                        periph=periph.name, register=reg.name, field=field.name,
                        lookup=_lookup_hint("lookup", path="%s.%s.%s" % (
                            periph.name, reg.name, field.name), reason="查看该位域的访问属性"))

    def _enable_order_findings(self, writes, defines):
        """E11：使能后写 DMA 计数/地址寄存器。

        文件级、文本级判定（不依赖外设名能否解析，簇命名如 DMA1_Channel1 也覆盖）：
        - 使能：语句里出现 `..._EN` / `..._ENABLE` 宏（=/|= 或 SET_BIT/WRITE_REG），
          或对 DMA 控制寄存器（CCR/CR/CHCTL/CTL）写入的数值 bit0=1；
        - 关闭：`&=` / CLEAR_BIT 上述宏，或数值清除 bit0（掩码 bit0=0 或 =0 写）；
        - 配置：写 CNDTR/NDTR/CMAR/CPAR（任何形态）；
        - 同外设前缀下，配置写发生在最近一次使能之后且中间没有关闭 → 报。
        """
        events = []
        for write in writes:
            periph, reg = self._names(write)
            if not periph or not reg:
                continue
            text = " ".join([
                " ".join(write.get("args") or []),
                write.get("rhs") or "",
                write.get("code") or "",
            ])
            op = write["op"]
            reg_key = reg.upper()
            is_ctrl = reg_key in _DMA_CTRL_REGS
            has_en = bool(_EN_MACRO_RE.search(text))
            value = None
            if not has_en and is_ctrl:
                value_expr = None
                if write["kind"] == "macro":
                    args = write.get("args") or []
                    if op in ("set_bit", "write_reg") and len(args) >= 2:
                        value_expr = args[1]
                else:
                    value_expr = write.get("rhs")
                if value_expr:
                    value = cscan.eval_int(value_expr, defines)
            if has_en and op in ("=", "|=", "set_bit", "write_reg"):
                events.append(("enable", periph.upper(), reg, write["line"], write["code"]))
            elif has_en and op in ("&=", "clear_bit"):
                events.append(("disable", periph.upper(), reg, write["line"], write["code"]))
            elif is_ctrl and value is not None:
                if op in ("=", "|=", "set_bit", "write_reg") and value & 1:
                    events.append(("enable", periph.upper(), reg, write["line"], write["code"]))
                elif op == "=" and not (value & 1):
                    events.append(("disable", periph.upper(), reg, write["line"], write["code"]))
                elif op in ("&=", "clear_bit") and not (value & 1):
                    events.append(("disable", periph.upper(), reg, write["line"], write["code"]))
            elif reg_key in _DMA_CONFIG_REGS:
                events.append(("config", periph.upper(), reg, write["line"], write["code"]))
        events.sort(key=lambda item: item[3])
        out = []
        enabled = {}
        for kind, periph_key, reg, line, code in events:
            if kind == "enable":
                enabled[periph_key] = (line, reg)
            elif kind == "disable":
                enabled.pop(periph_key, None)
            else:
                state = enabled.get(periph_key)
                if state and state[0] < line:
                    out.append({"periph": periph_key, "reg": reg, "line": line, "code": code,
                                "en_line": state[0], "en_reg": state[1]})
        return out

    # ---------- E07 ----------

    def _clock_findings(self, periph_first, rcc_enabled, hal_enables):
        rcc = self._periph("RCC")
        if rcc is None:
            return []
        out = []
        for periph_name, (line, code) in sorted(periph_first.items()):
            if periph_name in ("RCC",) or periph_name in CORE_PERIPHERALS:
                continue
            enable_field = None
            enable_reg = None
            for reg in rcc.registers:
                for field in reg.fields:
                    if field.name.upper() == periph_name + "EN":
                        enable_field = field
                        enable_reg = reg
                        break
                if enable_field is not None:
                    break
            if enable_field is None:
                continue
            if enable_field.name.upper() in rcc_enabled or periph_name in hal_enables:
                continue
            out.append({
                "line": line,
                "code": code,
                "message": "写入 %s 前未见该外设时钟使能（%s.%s 未置位）；若在其它文件使能请忽略" % (
                    periph_name, enable_reg.name, enable_field.name),
                "suggestion": "用 --no-clock-check 可关闭本项检查。",
                "peripheral": periph_name,
                "lookup": _lookup_hint("lookup", path="RCC.%s" % enable_reg.name,
                                       reason="查看时钟使能位 %s" % enable_field.name),
            })
        return out
