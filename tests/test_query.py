"""查询层测试。期望值按 tests/fixtures/synthetic.svd 手算。"""

import pytest

from etk_core import query
from etk_core.errors import E_FIELD_NOT_FOUND, E_INPUT_INVALID, E_PERIPH_NOT_FOUND, E_REG_NOT_FOUND, EtkError


def test_lookup_peripheral_lists_registers(device):
    res = query.lookup(device, "USART1")
    assert res["kind"] == "peripheral"
    assert res["base_address"] == "0x40013800"
    assert [r["offset"] for r in res["registers"]] == ["0x00", "0x0C", "0x1C"]
    assert res["label"] == "已核验"


def test_lookup_register(device):
    res = query.lookup(device, "USART1.CR1")
    assert res["kind"] == "register"
    reg = res["register"]
    assert (reg["address"], reg["offset"], reg["size"], reg["reset"]) == ("0x40013800", "0x00", 32, "0x00000000")
    assert [f["name"] for f in res["fields"]] == ["UE", "TE", "PS", "M0", "OVER8"]


def test_lookup_field_with_arrow_and_lowercase(device):
    res = query.lookup(device, "usart1->cr1.ue")
    assert res["kind"] == "field"
    assert res["field"]["name"] == "UE"
    assert res["field"]["bits"] == "0"
    assert res["field"]["width"] == 1
    assert res["field"]["reset"] == 0
    assert res["register"]["address"] == "0x40013800"


def test_field_reset_and_enum_patterns(device):
    res = query.lookup(device, "GPIOB.MODER.MODE0")
    assert res["field"]["reset"] == 1
    assert res["register"]["reset"] == "0x00000001"
    assert [e["pattern"] for e in res["field"]["enums"]] == ["00", "01", "10", "11"]
    assert [e["name"] for e in res["field"]["enums"]] == ["INPUT", "OUTPUT", "ALTERNATE", "ANALOG"]


def test_register_with_16_bit_size_formats_reset_width(device):
    res = query.lookup(device, "GPIOC.ODR")
    assert res["register"]["size"] == 16
    assert res["register"]["address"] == "0x48000814"
    assert res["register"]["reset"] == "0x0000"


def test_cluster_query_lists_members(device):
    res = query.lookup(device, "DMA1.CH1")
    assert res["kind"] == "cluster"
    assert [r["name"] for r in res["registers"]] == ["CH1.CCR", "CH1.CNDTR"]


def test_nested_cluster_register_address(device):
    res = query.lookup(device, "DMA1.CH2.CNDTR")
    assert res["kind"] == "register"
    assert res["register"]["address"] == "0x40020020"
    assert res["register"]["offset"] == "0x20"


def test_field_inside_cluster_register(device):
    res = query.lookup(device, "DMA1.CH2.CCR.EN")
    assert res["kind"] == "field"
    assert res["register"]["address"] == "0x4002001C"


def test_register_name_equal_to_field_name_resolves_both_ways(device):
    as_register = query.lookup(device, "TIM1.CNT")
    as_field = query.lookup(device, "TIM1.CNT.CNT")
    assert as_register["kind"] == "register"
    assert as_field["kind"] == "field"
    assert as_field["field"]["bits"] == "15:0"


def test_dim_register_address(device):
    res = query.lookup(device, "TIM1.CCR3")
    assert res["register"]["offset"] == "0x3C"
    assert res["register"]["address"] == "0x40012C3C"


def test_unknown_peripheral_suggests_candidates(device):
    with pytest.raises(EtkError) as info:
        query.lookup(device, "USART9")
    assert info.value.code == E_PERIPH_NOT_FOUND
    assert "USART1" in info.value.details["suggestions"]


def test_unknown_register_suggests_candidates(device):
    with pytest.raises(EtkError) as info:
        query.lookup(device, "USART1.CR9")
    assert info.value.code == E_REG_NOT_FOUND
    assert "CR1" in info.value.details["suggestions"]


def test_unknown_field_is_reported(device):
    with pytest.raises(EtkError) as info:
        query.lookup(device, "USART1.CR1.XYZ")
    assert info.value.code == E_FIELD_NOT_FOUND


def test_field_name_used_as_register_gives_location_hint(device):
    with pytest.raises(EtkError) as info:
        query.lookup(device, "USART1.UE")
    assert info.value.code == E_REG_NOT_FOUND
    assert "USART1.CR1.UE" in info.value.hint


def test_missing_register_under_dotted_path(device):
    with pytest.raises(EtkError) as info:
        query.lookup(device, "USART1.CR9.UE")
    assert info.value.code == E_REG_NOT_FOUND
    assert "CR9" in info.value.message


@pytest.mark.parametrize("bad", ["", "USART1..CR1", "  ", "."])
def test_malformed_query_is_input_error(device, bad):
    with pytest.raises(EtkError) as info:
        query.lookup(device, bad)
    assert info.value.code == E_INPUT_INVALID


def test_address_exact_register(device):
    res = query.find_address(device, 0x4001381C)
    assert res["kind"] == "exact"
    assert [m["path"] for m in res["matches"]] == ["USART1.SR"]


def test_address_exact_on_derived_peripheral(device):
    res = query.find_address(device, 0x40004400)
    assert res["kind"] == "exact"
    assert [m["path"] for m in res["matches"]] == ["USART2.CR1"]


def test_address_inside_register_reports_byte_offset(device):
    res = query.find_address(device, 0x40013801)
    assert res["kind"] == "inside_register"
    assert res["nearest"]["path"] == "USART1.CR1"
    assert res["nearest"]["offset_in_register"] == 1


def test_address_in_gap_reports_nearest_register(device):
    res = query.find_address(device, 0x40013810)
    assert res["kind"] == "gap"
    assert res["peripheral"] == "USART1"
    assert res["nearest"]["path"] == "USART1.BRR"
    assert res["nearest"]["offset_in_register"] == 4


def test_address_outside_any_peripheral(device):
    assert query.find_address(device, 0x40030000)["kind"] == "unmapped"


def test_address_just_past_span_is_unmapped(device):
    assert query.find_address(device, 0x40013C00)["kind"] == "unmapped"


def test_search_ranks_description_matches(device):
    res = query.search(device, "baud")
    assert res["total"] == 6
    assert res["matches"][0]["path"] == "USART1.BRR"
    assert res["matches"][1]["path"] == "USART1.BRR.DIV"


def test_search_truncates_to_limit(device):
    res = query.search(device, "usart", limit=2)
    assert res["truncated"] is True
    assert len(res["matches"]) == 2
    assert res["total"] > 2


def test_search_exact_field_name_across_instances(device):
    res = query.search(device, "TXE")
    assert res["total"] == 3
    assert [m["path"] for m in res["matches"]] == ["USART1.SR.TXE", "USART2.SR.TXE", "USART3.SR.TXE"]


def test_search_without_match_is_not_an_error(device):
    res = query.search(device, "zzzz")
    assert res["total"] == 0
    assert res["matches"] == []


def test_search_empty_keyword_is_input_error(device):
    with pytest.raises(EtkError) as info:
        query.search(device, "   ")
    assert info.value.code == E_INPUT_INVALID


def test_decode_fields_and_enum_and_undefined_bits(device):
    res = query.decode(device, "USART1.CR1", 0x109)
    by_name = {f["name"]: f for f in res["fields"]}
    assert by_name["UE"]["value"] == 1
    assert by_name["TE"]["value"] == 1
    assert by_name["PS"]["value"] == 0
    assert by_name["PS"]["enum"] == "EVEN"
    assert res["undefined_bits"] == [8]


def test_decode_enum_for_set_parity_bit(device):
    res = query.decode(device, "USART1.CR1", 0x200)
    ps = next(f for f in res["fields"] if f["name"] == "PS")
    assert (ps["value"], ps["enum"]) == (1, "ODD")
    assert res["undefined_bits"] == []


def test_decode_bit_string_enum(device):
    res = query.decode(device, "GPIOA.MODER", 0x2)
    mode0 = res["fields"][0]
    assert (mode0["value_hex"], mode0["enum"]) == ("0x2", "ALTERNATE")


def test_decode_value_out_of_width_is_rejected(device):
    with pytest.raises(EtkError) as info:
        query.decode(device, "USART1.BRR", 0x1_0000_0000)
    assert info.value.code == E_INPUT_INVALID


def test_decode_rejects_field_path(device):
    with pytest.raises(EtkError) as info:
        query.decode(device, "USART1.CR1.UE", 1)
    assert info.value.code == E_INPUT_INVALID
    assert "位域" in info.value.message


def test_list_peripherals(device):
    res = query.list_peripherals(device)
    assert res["count"] == 9
    by_name = {p["name"]: p for p in res["peripherals"]}
    assert by_name["USART2"]["derived_from"] == "USART1"
    assert by_name["USART1"]["register_count"] == 3
    assert by_name["GPIOB"]["base_address"] == "0x48000400"
