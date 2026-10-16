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
    assert res["count"] == 10
    by_name = {p["name"]: p for p in res["peripherals"]}
    assert by_name["USART2"]["derived_from"] == "USART1"
    assert by_name["USART1"]["register_count"] == 3
    assert by_name["GPIOB"]["base_address"] == "0x48000400"


def test_search_kind_filters_results(device):
    all_res = query.search(device, "USART")
    only = query.search(device, "USART", kind="peripheral")
    assert only["total"] == 3
    assert only["total"] < all_res["total"]
    assert all(m["kind"] == "peripheral" for m in only["matches"])


def test_lookup_reports_semantics_and_mask(device):
    res = query.lookup(device, "EXTI.PR.P0")
    f = res["field"]
    assert f["modified_write_values"] == "oneToClear"
    assert f["write_semantics"] == "写 1 清零"
    assert f["read_semantics"] == "读后清零"
    assert f["mask"] == "0x00000001"
    reg = res["register"]
    assert reg["write_semantics"] == "写 1 清零"
    assert reg["read_semantics"] == ""


def test_bit_ranges_compresses():
    assert query.bit_ranges([1, 2, 4, 5, 6]) == [[1, 2], [4, 6]]
    assert query.bit_ranges([]) == []
    assert query.bit_ranges([0]) == [[0, 0]]


def test_register_fields_masks_and_undefined(device):
    res = query.register_fields(device, "USART1.CR1")
    assert res["kind"] == "fields"
    by_name = {f["name"]: f for f in res["fields"]}
    assert by_name["UE"]["mask"] == "0x00000001"
    assert by_name["TE"]["mask"] == "0x00000008"
    assert by_name["PS"]["mask"] == "0x00000200"
    assert by_name["M0"]["mask"] == "0x00001000"
    assert by_name["OVER8"]["mask"] == "0x00008000"
    assert res["undefined_bits"] == [1, 2, 4, 5, 6, 7, 8, 10, 11, 13, 14] + list(range(16, 32))


def test_register_fields_mask_width_follows_register_size(device):
    res = query.register_fields(device, "GPIOC.ODR")
    assert res["fields"][0]["mask"] == "0x0001"


def test_diagram_cells_legend_and_owner(device):
    res = query.diagram(device, "USART1.CR1")
    assert res["kind"] == "diagram"
    assert len(res["cells"]) == 32
    chars = {c["bit"]: c["char"] for c in res["cells"]}
    assert chars[0] == "U" and chars[3] == "T" and chars[9] == "P"
    assert chars[12] == "M" and chars[15] == "O" and chars[1] == "."
    assert res["cells"][0]["field"] == "UE"
    assert res["cells"][1]["field"] is None
    assert [item["char"] for item in res["legend"]] == ["U", "T", "P", "M", "O"]
    assert res["reset_bits"] == []


def test_diagram_reset_bits(device):
    res = query.diagram(device, "USART1.SR")
    assert res["reset_bits"] == [6, 7]


def test_set_fields_defaults_to_reset_and_enums(device):
    res = query.set_fields(device, "TIM1.CR1", ["CEN=1", "DIR=UP"])
    assert res["kind"] == "set"
    assert res["from"]["label"] == "复位值"
    assert (res["value"], res["value_hex"]) == (1, "0x0001")
    rows = {a["field"]: a for a in res["assignments"]}
    assert rows["CEN"]["changed"] is True
    assert rows["DIR"]["changed"] is False
    assert rows["DIR"]["via_enum"] == "UP"


def test_set_fields_accepts_numeric_and_from_value(device):
    res = query.set_fields(device, "TIM1.CR1", ["DIR=0x1", "CEN=0b1"], 0x0000)
    assert res["value"] == 0x11
    assert res["from"]["label"] == "指定值"


def test_set_fields_unknown_field_suggests(device):
    with pytest.raises(EtkError) as info:
        query.set_fields(device, "TIM1.CR1", ["CENN=1"])
    assert info.value.code == E_FIELD_NOT_FOUND
    assert "CEN" in info.value.details["suggestions"]


def test_set_fields_value_out_of_width_is_rejected(device):
    with pytest.raises(EtkError) as info:
        query.set_fields(device, "TIM1.CR1", ["CEN=2"])
    assert info.value.code == E_INPUT_INVALID
    assert "宽度" in info.value.message


def test_set_fields_unknown_word_suggests_enum_names(device):
    with pytest.raises(EtkError) as info:
        query.set_fields(device, "TIM1.CR1", ["DIR=SIDEWAYS"])
    assert info.value.code == E_INPUT_INVALID
    assert "UP" in info.value.hint


def test_set_fields_read_only_gets_note(device):
    res = query.set_fields(device, "USART1.SR", ["TXE=0"])
    assert any("read-only" in n for n in res["notes"])


def test_set_fields_bad_assignment_format(device):
    with pytest.raises(EtkError) as info:
        query.set_fields(device, "TIM1.CR1", ["CEN"])
    assert info.value.code == E_INPUT_INVALID


def test_set_fields_source_value_out_of_range(device):
    with pytest.raises(EtkError) as info:
        query.set_fields(device, "TIM1.CR1", ["CEN=1"], 0x10000)
    assert info.value.code == E_INPUT_INVALID


def test_set_fields_reports_undefined_bits_set(device):
    res = query.set_fields(device, "TIM1.CR1", ["CEN=1"], 0x0002)
    assert res["value"] == 0x0003
    assert res["undefined_bits_set"] == [1]


def test_diff_registers_reports_all_statuses(device, device_b):
    res = query.diff_registers(device, device_b, "USART1.CR1")
    assert res["kind"] == "diff"
    assert res["identical"] is False
    assert "外设基地址 0x40013800 → 0x40013C00" in res["register_differences"]
    assert "复位 0x00000000 → 0x00000200" in res["register_differences"]
    rows = {r["name"]: r for r in res["fields"]}
    assert rows["UE"]["status"] == "same"
    assert rows["TE"]["status"] == "diff"
    assert rows["TE"]["differences"] == ["位 3 → 4"]
    assert "访问 read-write → read-only" in rows["PS"]["differences"]
    assert "复位 0 → 1" in rows["PS"]["differences"]
    assert "枚举仅 A 侧有：ODD" in rows["PS"]["differences"]
    assert rows["M0"]["status"] == "only_a"
    assert rows["M0"]["b"] is None
    assert rows["NEWF"]["status"] == "only_b"
    assert rows["NEWF"]["b"]["bits"] == "21:20"


def test_diff_identical_when_both_sides_same(device):
    res = query.diff_registers(device, device, "USART1.CR1")
    assert res["identical"] is True
    assert res["register_differences"] == []
    assert all(r["status"] == "same" for r in res["fields"])


def test_diff_error_names_the_side(device, device_b):
    with pytest.raises(EtkError) as info:
        query.diff_registers(device, device_b, "USART1.BRR")
    assert info.value.code == E_REG_NOT_FOUND
    assert "B 侧" in info.value.message


def test_find_in_range_lists_sorted_matches(device):
    res = query.find_in_range(device, 0x40013800, 0x4001381F)
    assert res["kind"] == "range"
    assert res["count"] == 3
    assert [m["path"] for m in res["registers"]] == ["USART1.CR1", "USART1.BRR", "USART1.SR"]


def test_find_in_range_truncates(device):
    res = query.find_in_range(device, 0x40000000, 0x50000000, limit=2)
    assert res["truncated"] is True
    assert len(res["registers"]) == 2


def test_find_in_range_reversed_bounds_is_error(device):
    with pytest.raises(EtkError) as info:
        query.find_in_range(device, 0x100, 0x10)
    assert info.value.code == E_INPUT_INVALID


def test_device_info_counts_vendor_and_hash(device):
    import hashlib

    from helpers import SYNTH

    res = query.device_info(device)
    assert res["kind"] == "info"
    assert (res["device"], res["vendor"], res["cpu"]) == ("SYNTH32", "SYNTH-Corp", "CM4")
    assert res["counts"]["peripherals"] == 10
    assert res["counts"]["derived_peripherals"] == 2
    assert res["counts"]["registers"] == 31
    assert res["counts"]["fields"] == 52
    assert res["counts"]["enums"] == 25
    with open(SYNTH, "rb") as fh:
        assert res["sha256"] == hashlib.sha256(fh.read()).hexdigest()
    assert res["file_size"] > 0
