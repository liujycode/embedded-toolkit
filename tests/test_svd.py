"""SVD 解析器测试。期望值全部按 tests/fixtures/synthetic.svd 手算，不是从代码输出复制的。"""

import pytest

from etk_core.errors import E_SVD_NOT_FOUND, E_SVD_PARSE, EtkError
from etk_core.svd import load_device
from helpers import BROKEN, NOT_DEVICE


def _svd(tmp_path, peripherals, device_extra=""):
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<device><name>T</name><version>1</version>%s"
        "<peripherals>%s</peripherals></device>" % (device_extra, peripherals)
    )
    path = tmp_path / "t.svd"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_device_metadata(device):
    assert device.name == "SYNTH32"
    assert device.version == "1.0"
    assert device.warnings == []


def test_peripheral_instances_in_document_order(device):
    assert [p.name for p in device.peripherals] == [
        "USART1", "USART2", "USART3", "GPIOA", "GPIOB", "GPIOC", "DMA1", "TIM1", "RCC", "EXTI", "NVIC"]


def test_register_offsets_sizes_and_resets(device):
    usart1 = device.peripheral("USART1")
    cr1 = usart1.register("CR1")
    assert (cr1.offset, cr1.size, cr1.access, cr1.reset_value) == (0x00, 32, "read-write", 0)
    brr = usart1.register("BRR")
    assert (brr.offset, brr.size, brr.access, brr.reset_value) == (0x0C, 32, "read-write", 0)
    sr = usart1.register("SR")
    assert (sr.offset, sr.access, sr.reset_value) == (0x1C, "read-only", 0xC0)


def test_bit_position_forms(device):
    cr1 = device.peripheral("USART1").register("CR1")
    ue = cr1.field("UE")
    assert (ue.lsb, ue.msb, ue.width, ue.bit_text) == (0, 0, 1, "0")
    ps = cr1.field("PS")
    assert (ps.lsb, ps.width, ps.bit_text) == (9, 1, "9")
    assert cr1.field("M0").lsb == 12
    over8 = cr1.field("OVER8")
    assert (over8.lsb, over8.width) == (15, 1)
    div = device.peripheral("USART1").register("BRR").field("DIV")
    assert (div.lsb, div.width, div.bit_text) == (0, 16, "15:0")


def test_enumerated_values_keep_default_entries(device):
    """无 value 的枚举项：默认项（isDefault）保留为 is_default（mask=0 匹配任意值），其余跳过。"""
    ps = device.peripheral("USART1").register("CR1").field("PS")
    assert [(e.name, e.value, e.mask) for e in ps.enums] == [
        ("EVEN", 0, 1), ("ODD", 1, 1), ("DEFAULT", 0, 0)]
    assert ps.enums[-1].is_default is True
    assert ps.enums[0].is_default is False


def test_field_access_inherits_register_unless_overridden(device):
    sr = device.peripheral("USART1").register("SR")
    assert sr.field("TXE").access == "read-only"
    assert sr.field("TC").access == "read-write"


def test_derived_peripheral_inherits_registers_and_description(device):
    usart2 = device.peripheral("USART2")
    assert usart2.base_address == 0x40004400
    assert usart2.derived_from == "USART1"
    assert [r.name for r in usart2.registers] == ["CR1", "BRR", "SR"]
    assert usart2.description == "Synthetic USART 1"
    assert usart2.register("SR").field("TXE").access == "read-only"


def test_derived_peripheral_register_override_replaces_definition(device):
    usart3 = device.peripheral("USART3")
    sr = usart3.register("SR")
    assert sr.reset_value == 0x40
    assert sr.access == "read-write"
    assert [f.name for f in sr.fields] == ["TXE"]
    assert usart3.register("BRR") is not None


def test_dim_peripheral_expands_instances(device):
    bases = {p.name: p.base_address for p in device.peripherals if p.name.startswith("GPIO")}
    assert bases == {"GPIOA": 0x48000000, "GPIOB": 0x48000400, "GPIOC": 0x48000800}


def test_peripheral_level_reset_and_size_are_inherited(device):
    gpiob = device.peripheral("GPIOB")
    assert gpiob.register("MODER").reset_value == 0x1
    assert gpiob.register("MODER").size == 32
    assert gpiob.register("ODR").reset_value == 0
    assert gpiob.register("ODR").size == 16


def test_enum_values_from_bit_strings(device):
    moder = device.peripheral("GPIOA").register("MODER").field("MODE0")
    assert [(e.name, e.value, e.mask) for e in moder.enums] == [
        ("INPUT", 0, 3), ("OUTPUT", 1, 3), ("ALTERNATE", 2, 3), ("ANALOG", 3, 3)]


def test_cluster_registers_are_prefixed_and_offset(device):
    got = {r.name: r.offset for r in device.peripheral("DMA1").registers}
    assert got == {"ISR": 0x00, "CH1.CCR": 0x08, "CH1.CNDTR": 0x0C, "CH2.CCR": 0x1C, "CH2.CNDTR": 0x20}


def test_register_dim_expands_with_increment(device):
    offsets = {r.name: r.offset for r in device.peripheral("TIM1").registers if r.name.startswith("CCR")}
    assert offsets == {"CCR1": 0x34, "CCR2": 0x38, "CCR3": 0x3C, "CCR4": 0x40}


def test_register_derived_from_sibling_inherits_fields_and_size(device):
    cr1s = device.peripheral("TIM1").register("CR1S")
    assert (cr1s.offset, cr1s.size, cr1s.reset_value) == (0x10, 16, 0)
    assert [f.name for f in cr1s.fields] == ["CEN", "DIR"]
    assert cr1s.description == "TIM1 control register 1"


def test_enum_with_dont_care_bits(device):
    mms = device.peripheral("TIM1").register("CR2").field("MMS")
    assert [(e.name, e.value, e.mask) for e in mms.enums] == [
        ("RESET", 0, 7), ("ENABLE", 1, 7), ("COMPARE", 4, 4)]


def test_read_only_register_and_reset_mask(device):
    assert device.peripheral("TIM1").register("CNT").access == "read-only"
    rcc_cr = device.peripheral("RCC").register("CR")
    assert rcc_cr.reset_value == 0x500
    assert rcc_cr.reset_mask == 0xFFFF
    assert rcc_cr.field("HSION").lsb == 8
    assert rcc_cr.field("HSIRDY").access == "read-only"


def test_address_span_from_block_or_registers(device):
    assert device.peripheral("USART1").address_span == 0x400
    assert device.peripheral("RCC").address_span == 0x5C


def test_register_and_field_with_same_name_both_kept(device):
    cnt = device.peripheral("TIM1").register("CNT")
    assert cnt.field("CNT") is not None


def test_names_are_case_insensitive(device):
    assert device.peripheral("usart1") is device.peripheral("USART1")
    assert device.peripheral("USART1").register("cr1") is device.peripheral("USART1").register("CR1")


def test_parse_error_reports_line(device):
    with pytest.raises(EtkError) as info:
        load_device(BROKEN)
    assert info.value.code == E_SVD_PARSE
    with open(BROKEN, encoding="utf-8") as fh:
        expected = next(i for i, line in enumerate(fh, 1) if "</registers>" in line)
    assert info.value.details["line"] == expected


def test_non_svd_root_is_rejected():
    with pytest.raises(EtkError) as info:
        load_device(NOT_DEVICE)
    assert info.value.code == E_SVD_PARSE
    assert "device" in info.value.message


def test_empty_file_is_rejected(tmp_path):
    empty = tmp_path / "empty.svd"
    empty.write_bytes(b"")
    with pytest.raises(EtkError) as info:
        load_device(str(empty))
    assert info.value.code == E_SVD_PARSE


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(EtkError) as info:
        load_device(str(tmp_path / "none.svd"))
    assert info.value.code == E_SVD_NOT_FOUND


def test_missing_peripherals_node_is_rejected(tmp_path):
    path = tmp_path / "x.svd"
    path.write_text("<device><name>T</name></device>", encoding="utf-8")
    with pytest.raises(EtkError) as info:
        load_device(str(path))
    assert info.value.code == E_SVD_PARSE


def test_namespace_prefix_is_accepted(tmp_path):
    path = tmp_path / "ns.svd"
    path.write_text(
        '<device xmlns="urn:example"><name>NS</name><version>2</version><peripherals>'
        "<peripheral><name>P</name><baseAddress>0x100</baseAddress>"
        "<registers><register><name>R</name><addressOffset>4</addressOffset></register></registers>"
        "</peripheral></peripherals></device>",
        encoding="utf-8",
    )
    dev = load_device(str(path))
    assert dev.peripheral("P").register("R").offset == 4


def test_cyclic_peripheral_derivation_is_reported_not_fatal(tmp_path):
    periphs = (
        '<peripheral derivedFrom="B"><name>A</name><baseAddress>0x1000</baseAddress></peripheral>'
        '<peripheral derivedFrom="A"><name>B</name><baseAddress>0x2000</baseAddress>'
        "<registers><register><name>R</name><addressOffset>0</addressOffset></register></registers>"
        "</peripheral>"
    )
    dev = load_device(_svd(tmp_path, periphs))
    assert {p.name for p in dev.peripherals} == {"A", "B"}
    assert any("循环" in w for w in dev.warnings)
    assert dev.peripheral("A").register("R") is not None


def test_derived_register_with_unknown_base_warns(tmp_path):
    periphs = (
        '<peripheral><name>P</name><baseAddress>0x100</baseAddress><registers>'
        '<register derivedFrom="NOPE"><name>X</name><addressOffset>4</addressOffset></register>'
        "</registers></peripheral>"
    )
    dev = load_device(_svd(tmp_path, periphs))
    assert dev.peripheral("P").register("X").offset == 4
    assert any("NOPE" in w for w in dev.warnings)


def test_field_without_position_is_skipped_with_warning(tmp_path):
    periphs = (
        "<peripheral><name>P</name><baseAddress>0</baseAddress><registers><register>"
        "<name>R</name><fields>"
        "<field><name>BAD</name></field>"
        "<field><name>GOOD</name><bitOffset>1</bitOffset><bitWidth>2</bitWidth></field>"
        "</fields></register></registers></peripheral>"
    )
    dev = load_device(_svd(tmp_path, periphs))
    reg = dev.peripheral("P").register("R")
    assert [f.name for f in reg.fields] == ["GOOD"]
    assert (reg.field("GOOD").lsb, reg.field("GOOD").width) == (1, 2)
    assert any("BAD" in w for w in dev.warnings)


def test_unparseable_address_offset_defaults_to_zero_with_warning(tmp_path):
    periphs = (
        "<peripheral><name>P</name><baseAddress>0x100</baseAddress><registers><register>"
        "<name>R</name><addressOffset>zz</addressOffset></register></registers></peripheral>"
    )
    dev = load_device(_svd(tmp_path, periphs))
    assert dev.peripheral("P").register("R").offset == 0
    assert any("zz" in w for w in dev.warnings)


def test_unknown_base_peripheral_warns_and_builds(tmp_path):
    periphs = '<peripheral derivedFrom="NOPE"><name>P</name><baseAddress>0x10</baseAddress></peripheral>'
    dev = load_device(_svd(tmp_path, periphs))
    assert dev.peripheral("P").base_address == 0x10
    assert any("NOPE" in w for w in dev.warnings)


def test_leading_whitespace_before_xml_declaration_is_tolerated(tmp_path):
    content = ('<?xml version="1.0" encoding="utf-8"?>\n<device><name>T</name><peripherals>'
               "<peripheral><name>P</name><baseAddress>0x100</baseAddress></peripheral>"
               "</peripherals></device>")
    path = tmp_path / "lead.svd"
    path.write_bytes(b"  \r\n" + content.encode("utf-8"))
    dev = load_device(str(path))
    assert dev.peripheral("P").base_address == 0x100
    assert any("自动忽略" in w for w in dev.warnings)


def test_nonspace_prefix_before_declaration_still_fails(tmp_path):
    path = tmp_path / "junk.svd"
    path.write_bytes(b"GARBAGE " + b'<?xml version="1.0"?><device><name>T</name></device>')
    with pytest.raises(EtkError) as info:
        load_device(str(path))
    assert info.value.code == E_SVD_PARSE


def test_device_vendor_and_cpu(device):
    assert device.vendor == "SYNTH-Corp"
    assert device.cpu == "CM4"


def test_modified_write_values_register_level_inherited_by_fields(device):
    pr = device.peripheral("EXTI").register("PR")
    assert pr.modified_write_values == "oneToClear"
    assert pr.field("P0").modified_write_values == "oneToClear"
    assert pr.field("P1").modified_write_values == "oneToSet"


def test_read_action_is_field_level(device):
    pr = device.peripheral("EXTI").register("PR")
    assert pr.field("P0").read_action == "clear"
    assert pr.field("P1").read_action == ""


def test_interrupt_entries_are_parsed(device):
    usart1 = device.peripheral("USART1")
    assert [(i.name, i.value, i.description) for i in usart1.interrupts] == [
        ("USART1_IRQn", 37, "USART1 global interrupt")]


def test_derived_peripheral_inherits_interrupts_when_absent(device):
    assert [(i.name, i.value) for i in device.peripheral("USART2").interrupts] == [("USART1_IRQn", 37)]


def test_derived_peripheral_declared_interrupts_replace_inherited(device):
    assert [(i.name, i.value) for i in device.peripheral("USART3").interrupts] == [("USART3_IRQn", 39)]


def test_multiple_interrupts_per_peripheral(device):
    assert [(i.name, i.value) for i in device.peripheral("DMA1").interrupts] == [
        ("DMA1_Channel1_IRQn", 11), ("DMA1_Channel2_IRQn", 12)]
