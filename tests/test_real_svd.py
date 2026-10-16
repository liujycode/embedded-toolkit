"""真实厂商 SVD 测试。仓库不内置厂商文件，需要设置环境变量 ETK_TEST_SVD_DIR 指向存放 .svd 的目录。

验证方式：
1. 已知事实：数值来自对原始 XML 的 grep 核对（见 benchmarks/real-svd-facts.md）。
2. 独立遍历对照：用一个不依赖 etk_core 的简单遍历读取非派生、非数组、非簇的外设，
   比较 寄存器名、偏移、宽度、复位值、位域位置，与解析器输出逐项一致。
"""

import glob
import os
import re
import time
import xml.etree.ElementTree as ET

import pytest

from etk_core import query
from etk_core.svd import load_device

SVD_DIRS = [d for d in os.environ.get("ETK_TEST_SVD_DIR", "").split(os.pathsep) if d]
pytestmark = pytest.mark.skipif(not SVD_DIRS, reason="未设置 ETK_TEST_SVD_DIR，跳过真实 SVD 测试")


def _find(name):
    for root in SVD_DIRS:
        hits = glob.glob(os.path.join(root, "**", name), recursive=True)
        if hits:
            return hits[0]
    pytest.skip("%s 不在 ETK_TEST_SVD_DIR 中" % name)


def _num(text):
    s = text.strip()
    return int(s[2:], 16) if s.lower().startswith("0x") else int(s, 10)


def _text(el, tag):
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _bits(field_el):
    off, wid = _text(field_el, "bitOffset"), _text(field_el, "bitWidth")
    if off is not None and wid is not None:
        return _num(off), _num(wid)
    rng = _text(field_el, "bitRange")
    if rng:
        m = re.match(r"\[(\d+):(\d+)\]", rng)
        lsb = int(m.group(2))
        return lsb, int(m.group(1)) - lsb + 1
    lsb, msb = _num(_text(field_el, "lsb")), _num(_text(field_el, "msb"))
    return lsb, msb - lsb + 1


def _parse_root(path):
    """测试侧独立解析：容忍 XML 声明前的空白（GD32F3x0 SVD 有此问题），不依赖 etk_core。"""
    with open(path, "rb") as fh:
        data = fh.read()
    idx = 0
    while idx < len(data) and data[idx] in b" \t\r\n":
        idx += 1
    return ET.fromstring(data[idx:])


def _independent_walk(path):
    root = _parse_root(path)
    dev_size = _num(_text(root, "width")) if _text(root, "width") else 32
    dev_reset = _num(_text(root, "resetValue")) if _text(root, "resetValue") else 0
    out = {}
    for p in root.iter("peripheral"):
        regs_el = p.find("registers")
        if p.get("derivedFrom") or p.find("dim") is not None or regs_el is None:
            continue
        if any(c.tag == "cluster" or c.find("dim") is not None or c.get("derivedFrom") for c in regs_el):
            continue
        psize = _num(_text(p, "size")) if _text(p, "size") else dev_size
        preset = _num(_text(p, "resetValue")) if _text(p, "resetValue") else dev_reset
        regs = {}
        for r in regs_el.findall("register"):
            size = _num(_text(r, "size")) if _text(r, "size") else psize
            reset = _num(_text(r, "resetValue")) if _text(r, "resetValue") else preset
            fields_el = r.find("fields")
            fields = []
            if fields_el is not None:
                for f in fields_el.findall("field"):
                    lsb, width = _bits(f)
                    fields.append((_text(f, "name"), lsb, width))
            regs[_text(r, "name")] = (_num(_text(r, "addressOffset") or "0"), size, reset, tuple(sorted(fields)))
        out[_text(p, "name")] = regs
    return out


def _parser_view(device):
    out = {}
    for p in device.peripherals:
        if p.derived_from or any("." in r.name for r in p.registers):
            continue
        out[p.name] = {
            r.name: (r.offset, r.size, r.reset_value,
                     tuple(sorted((f.name, f.lsb, f.width) for f in r.fields)))
            for r in p.registers
        }
    return out


def test_stm32g431_known_facts():
    dev = load_device(_find("STM32G431xx.svd"))
    usart1 = dev.peripheral("USART1")
    assert usart1.base_address == 0x40013800
    ue = usart1.register("CR1").field("UE")
    assert (ue.lsb, ue.width, ue.description) == (0, 1, "USART enable")
    usart2 = dev.peripheral("USART2")
    assert usart2.derived_from == "USART1"
    assert usart2.base_address == 0x40004400
    res = query.lookup(dev, "USART2.CR1")
    assert res["register"]["address"] == "0x40004400"


# 非空守卫：防止对照范围为零导致测试空转；不是覆盖率指标。
MIN_COMPARED_PERIPHERALS = 10


def _assert_matches_walk(path, min_count=MIN_COMPARED_PERIPHERALS):
    expected = _independent_walk(path)
    got = _parser_view(load_device(path))
    checked = [name for name in expected if name in got]
    assert len(checked) >= min_count, "对照外设仅 %d 个，检查测试条件" % len(checked)
    for name in checked:
        assert got[name] == expected[name], "外设 %s 与独立遍历结果不一致" % name
    return len(checked)


def test_stm32g431_matches_independent_walk():
    _assert_matches_walk(_find("STM32G431xx.svd"))


def test_nrf52840_matches_independent_walk():
    _assert_matches_walk(_find("nrf52840.svd"))


def _assert_derived_mirror_base(path):
    root = _parse_root(path)
    dev = load_device(path)
    checked = 0
    for p in root.iter("peripheral"):
        base_name = p.get("derivedFrom")
        if not base_name or p.find("registers") is not None:
            continue
        name = _text(p, "name")
        ours = dev.peripheral(name)
        base = dev.peripheral(base_name)
        if ours is None or base is None:
            continue
        mine = [(r.name, r.offset, r.size, r.reset_value) for r in ours.registers]
        theirs = [(r.name, r.offset, r.size, r.reset_value) for r in base.registers]
        assert mine == theirs, "派生外设 %s 与基础外设 %s 的寄存器不一致" % (name, base_name)
        checked += 1
    assert checked > 0, "没有可检查的派生外设"
    return checked


def test_stm32g431_derived_peripherals_mirror_base():
    _assert_derived_mirror_base(_find("STM32G431xx.svd"))


def test_nrf52840_derived_peripherals_mirror_base():
    _assert_derived_mirror_base(_find("nrf52840.svd"))


def test_nrf52840_uarte0_address():
    dev = load_device(_find("nrf52840.svd"))
    assert dev.peripheral("UARTE0").base_address == 0x40002000


def test_large_svd_loads_within_budget():
    path = _find("STM32G431xx.svd")
    started = time.time()
    load_device(path)
    assert time.time() - started < 5.0


def test_gd32f3x0_known_facts():
    dev = load_device(_find("GD32F3x0.svd"))
    assert dev.name == "GD32F3x0"
    gpioa = dev.peripheral("GPIOA")
    assert gpioa.base_address == 0x48000000
    assert gpioa.address_span >= 0x400


def test_gd32f3x0_matches_independent_walk():
    _assert_matches_walk(_find("GD32F3x0.svd"), min_count=5)


def test_gd32f3x0_derived_peripherals_mirror_base():
    _assert_derived_mirror_base(_find("GD32F3x0.svd"))


def test_real_g431_set_and_fields_masks():
    dev = load_device(_find("STM32G431xx.svd"))
    res = query.set_fields(dev, "USART1.CR1", ["UE=1", "RE=1"])
    assert res["value"] == 0x00000005
    fields = query.register_fields(dev, "USART1.CR1")
    by_name = {f["name"]: f for f in fields["fields"]}
    assert by_name["UE"]["mask"] == "0x00000001"
    assert by_name["RE"]["mask"] == "0x00000004"


def test_real_f103_usart1_ue_is_bit13():
    dev = load_device(_find("STM32F103xx.svd"))
    ue = dev.peripheral("USART1").register("CR1").field("UE")
    assert (ue.lsb, ue.width) == (13, 1)
    res = query.set_fields(dev, "USART1.CR1", ["UE=1"])
    assert res["value"] == 0x00002000


def test_real_diff_f103_vs_g431_usart_cr1():
    f103 = load_device(_find("STM32F103xx.svd"))
    g431 = load_device(_find("STM32G431xx.svd"))
    res = query.diff_registers(f103, g431, "USART1.CR1")
    assert res["identical"] is False
    rows = {r["name"]: r for r in res["fields"]}
    assert rows["UE"]["status"] == "diff"
    assert rows["UE"]["a"]["bits"] == "13"
    assert rows["UE"]["b"]["bits"] == "0"


def test_real_info_sha256_matches_file():
    import hashlib
    path = _find("STM32G431xx.svd")
    res = query.device_info(load_device(path))
    with open(path, "rb") as fh:
        assert res["sha256"] == hashlib.sha256(fh.read()).hexdigest()
    assert res["counts"]["peripherals"] > 20
    assert res["counts"]["registers"] > 100


def test_real_f103_usart1_irq_number():
    dev = load_device(_find("STM32F103xx.svd"))
    irq_map = {i.name.upper(): i.value for p in dev.peripherals for i in p.interrupts}
    # ST 的 SVD 里中断名就是 "USART1"（无 _IRQn 后缀），向量号 37 是硬件事实
    assert irq_map.get("USART1") == 37


def test_real_g431_irq_lookup_and_macros():
    dev = load_device(_find("STM32G431xx.svd"))
    res = query.find_interrupts(dev, "USART1")
    assert any(m["name"].upper().startswith("USART1") for m in res["matches"])
    assert any(m["value"] == 37 for m in res["matches"])
    macros = query.macros_for(dev, "USART1.CR1")
    assert "#define USART1_CR1_UE_Pos 0U" in macros["code"]
    assert "#define USART1_CR1_UE_Msk (0x1UL << USART1_CR1_UE_Pos)" in macros["code"]


def test_real_f103_macros_ue_is_bit13():
    dev = load_device(_find("STM32F103xx.svd"))
    res = query.macros_for(dev, "USART1.CR1")
    assert "#define USART1_CR1_UE_Pos 13U" in res["code"]


def test_real_f103_write_notes_on_read_only_idr():
    dev = load_device(_find("STM32F103xx.svd"))
    res = query.decode(dev, "GPIOA.IDR", 0xFFFF, as_write=True)
    assert any("read-only" in n for n in res["write_notes"])
