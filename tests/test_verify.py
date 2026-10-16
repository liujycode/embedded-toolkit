"""核验器测试：词法层（cscan）、规则（crules）与 CLI。"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY_SCRIPTS = os.path.join(ROOT, "skills", "embedded-register-verify", "scripts")
if VERIFY_SCRIPTS not in sys.path:
    sys.path.insert(0, VERIFY_SCRIPTS)

import cscan  # noqa: E402
import crules  # noqa: E402
from etk_core.svd import load_device  # noqa: E402
from helpers import FIXTURES, SYNTH, run_py  # noqa: E402

VERIFY_BAD = os.path.join(FIXTURES, "verify_bad.c")
VERIFY_OK = os.path.join(FIXTURES, "verify_ok.c")
VERIFY_PATCH = os.path.join(FIXTURES, "verify_patch.diff")
VERIFY_CLI = os.path.join(VERIFY_SCRIPTS, "verify.py")
DEMO_SVD = os.path.join(ROOT, "skills", "embedded-register-verify", "assets", "demo.svd")
DEMO_C = os.path.join(ROOT, "skills", "embedded-register-verify", "examples", "verify_demo.c")


@pytest.fixture(scope="module")
def device():
    return load_device(SYNTH)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _check(device, text, **kwargs):
    return crules.Verifier(device, **kwargs).check_file("t.c", text)


# ---------- cscan：词法层 ----------

def test_strip_comments_and_strings_is_length_preserving():
    text = 'int a = 1; // c->x = 1\nchar *s = "a\\"b"; /* c->y=2\ncontinued */ int b = 2;'
    clean = cscan.strip_comments_and_strings(text)
    assert len(clean) == len(text)
    assert "c->x" not in clean
    assert "c->y" not in clean
    assert clean.count("\n") == text.count("\n")
    assert "int a = 1;" in clean and "int b = 2;" in clean


def test_join_continuations_keeps_original_line_numbers():
    joined, line_map = cscan.join_continuations("a \\\n  b;\nc;\n")
    assert joined.split("\n")[0].strip() == "a  b;"
    assert line_map[:2] == [1, 3]


def test_split_statements_handles_parens_and_braces():
    clean = "void f(void) { for (i=0; i<2; i++) { USART1->CR1 = 1; } }"
    got = [clean[a:b].strip() for a, b in cscan.split_statements(clean)]
    assert got == ["USART1->CR1 = 1;"]
    clean2 = "for (i=0; i<3; i++) USART1->CR1 |= 1;"
    got2 = [clean2[a:b].strip() for a, b in cscan.split_statements(clean2)]
    assert got2 == ["for (i=0; i<3; i++) USART1->CR1 |= 1;"]


def test_extract_member_write_and_line():
    parsed = cscan.extract_all("x = 1;\nUSART1->CR1 |= A | B;\n")
    write = parsed["writes"][0]
    assert (write["kind"], write["peripheral"], write["register"], write["op"]) == (
        "member", "USART1", "CR1", "|=")
    assert write["rhs"] == "A | B"
    assert write["line"] == 2


def test_extract_ignores_reads_and_comparisons():
    parsed = cscan.extract_all("if (USART1->SR == 0) { }\nint y = P->X;\n")
    assert parsed["writes"] == []


def test_extract_addr_and_macro_writes():
    parsed = cscan.extract_all(
        "*(volatile uint32_t *)0x40013800 = 1;\n"
        "SET_BIT(USART1->CR1, USART_CR1_UE);\n"
        "MODIFY_REG(USART1->CR1, M_Msk, 2);\n")
    kinds = [(w["kind"], w["op"]) for w in parsed["writes"]]
    assert kinds == [("addr", "="), ("macro", "set_bit"), ("macro", "modify_reg")]
    assert parsed["writes"][0]["address"] == 0x40013800
    assert parsed["writes"][2]["args"] == ["USART1->CR1", "M_Msk", "2"]


def test_extract_hal_clock_enable():
    parsed = cscan.extract_all("__HAL_RCC_USART2_CLK_ENABLE();\n")
    assert parsed["enables"] == ["USART2"]


def test_eval_int_basics():
    defines = {"A": "1 << 3", "B": "A | 0x4", "C": "B"}
    assert cscan.eval_int("0x10 + 2", {}) == 18
    assert cscan.eval_int("0b101 << 2", {}) == 20
    assert cscan.eval_int("B", defines) == 12
    assert cscan.eval_int("C", defines) == 12
    assert cscan.eval_int("(uint32_t)(1) | 2", {}) == 3
    assert cscan.eval_int("~0xFF & 0xFFFF", {}) == 0xFF00
    assert cscan.eval_int("foo + 1", {}) is None
    assert cscan.eval_int("1 / 0", {}) is None
    assert cscan.eval_int("1 +", {}) is None
    assert cscan.eval_int("X", {"X": "Y + 1", "Y": "X + 1"}) is None


# ---------- crules：规则引擎 ----------

def test_bad_fixture_full_expectations(device):
    res = crules.Verifier(device).check_file("verify_bad.c", _read(VERIFY_BAD))
    assert res["counts"] == {"writes": 20, "report": 12, "undetermined": 3, "passed": 5, "findings": 13}
    codes = sorted({f["class"] for f in res["findings"]})
    assert codes == ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10"]
    by_line = {f["line"]: f["class"] for f in res["findings"]}
    assert by_line[10] == "E03" and by_line[11] == "E03" and by_line[12] == "E03"
    assert by_line[15] == "E10" and by_line[16] == "E04" and by_line[17] == "E01"
    assert by_line[18] == "E02" and by_line[19] == "E08" and by_line[20] == "E07"
    assert by_line[21] == "E06" and by_line[22] == "E05" and by_line[23] == "E10"
    reasons = [u["reason"] for u in res["undetermined"]]
    assert len(reasons) == 3
    assert any("Cortex-M" in r for r in reasons)
    assert any("簇寄存器" in r for r in reasons)
    assert any("无法映射" in r for r in reasons)


def test_ok_fixture_passes(device):
    res = crules.Verifier(device).check_file("verify_ok.c", _read(VERIFY_OK))
    assert res["counts"]["report"] == 0
    assert res["findings"] == []
    assert res["counts"]["passed"] == 5


def test_clock_check_reports_and_can_be_disabled(device):
    text = "void f(void)\n{\n    USART2->CR1 |= USART_CR1_UE;\n}\n"
    res = _check(device, text)
    assert any(f["class"] == "E07" for f in res["findings"])
    res2 = _check(device, text, clock_check=False)
    assert res2["findings"] == []


def test_clock_enabled_via_hal_macro(device):
    text = "__HAL_RCC_USART2_CLK_ENABLE();\nUSART2->CR1 |= USART_CR1_UE;\n"
    assert _check(device, text)["counts"]["report"] == 0


def test_clock_enabled_via_rcc_macro_write(device):
    text = "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;\nUSART2->CR1 |= USART_CR1_UE;\n"
    assert _check(device, text)["counts"]["report"] == 0


def test_clock_enabled_via_numeric_rcc_write(device):
    text = "RCC->APB1ENR = 0x00020000;\nUSART2->CR1 |= USART_CR1_UE;\n"
    assert _check(device, text)["counts"]["report"] == 0


def test_define_resolves_value_macro(device):
    text = "USART1->BRR = BAUD_VAL;\n"
    res = _check(device, text, extra_defines={"BAUD_VAL": "0x683"})
    assert res["counts"] == {"writes": 1, "report": 0, "undetermined": 0, "passed": 1, "findings": 0}


def test_read_only_hit_by_numeric_value(device):
    res = _check(device, "RCC->CR = 0x400;\n")  # bit10 = HSIRDY，只读
    assert [f["class"] for f in res["findings"]] == ["E10"]


def test_modify_reg_enum_invalid(device):
    res = _check(device, "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x2);\n")
    assert [f["class"] for f in res["findings"]] == ["E05"]


def test_modify_reg_value_out_of_width(device):
    res = _check(device, "MODIFY_REG(USART1->CR1, USART_CR1_PS_Msk, 0x4);\n")
    assert [f["class"] for f in res["findings"]] == ["E04"]


def test_field_macro_belongs_to_other_register(device):
    res = _check(device, "USART1->CR1 |= USART_BRR_DIV;\n")
    assert res["findings"][0]["class"] == "E03"
    assert "BRR" in res["findings"][0]["message"]


def test_e06_not_reported_when_field_set_elsewhere(device):
    text = "CLEAR_BIT(USART1->CR1, USART_CR1_M0);\nUSART1->CR1 |= USART_CR1_M0;\n"
    res = _check(device, text)
    assert not any(f["class"] == "E06" for f in res["findings"])


def test_e06_not_reported_for_modify_reg_clear(device):
    res = _check(device, "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, TIM_CR2_MMS_ENABLE);\n")
    assert res["findings"] == []


def test_limit_truncates_findings(device):
    res = crules.Verifier(device, limit=3).check_file("verify_bad.c", _read(VERIFY_BAD))
    assert len(res["findings"]) == 3
    assert res["findings_truncated"] is True
    assert res["counts"]["findings"] == 13


def test_checklist_groups(device):
    verifier = crules.Verifier(device)
    verifier.checklist = True
    res = verifier.check_file("t.c", "USART1->CR1 = 0;\nDMA1->ISR = 0x1;\nUSART2->CR1 |= USART_CR1_UE;\n")
    assert len(res["checklist"]["chip_default"]) == 1
    assert res["checklist"]["verified"] == 1
    assert res["checklist"]["measured"]
    assert any("USART2" in item.get("message", "") for item in res["checklist"]["manual"])


def test_core_peripheral_goes_undetermined(device):
    res = _check(device, "SysTick->CTRL = 0x5;\n")
    assert res["counts"] == {"writes": 1, "report": 0, "undetermined": 1, "passed": 0, "findings": 0}
    assert "内核外设" in res["undetermined"][0]["reason"]


def test_cluster_naming_goes_undetermined(device):
    res = _check(device, "DMA1_Channel1->CCR |= 0x1;\n")
    assert res["counts"]["undetermined"] == 1
    assert "簇寄存器" in res["undetermined"][0]["reason"]


def test_demo_example_reports_expected():
    device = load_device(DEMO_SVD)
    res = crules.Verifier(device).check_file("verify_demo.c", _read(DEMO_C))
    assert [f["class"] for f in res["findings"]] == ["E03", "E10", "E10"]
    assert res["counts"]["passed"] == 5


# ---------- CLI ----------

def test_cli_json_report_and_exit_code():
    r = run_py(VERIFY_CLI, "check", VERIFY_BAD, "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    env = json.loads(r.stdout)
    assert env["ok"] is True
    assert env["errors"] == []
    assert env["results"][0]["counts"]["report"] == 12


def test_cli_ok_file_exits_zero():
    r = run_py(VERIFY_CLI, "check", VERIFY_OK, "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "报 0" in r.stdout


def test_cli_directory_scan(tmp_path):
    (tmp_path / "a.c").write_text("USART1->CR1 |= USART_CR1_XXX;\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(tmp_path), "--svd", SYNTH, "--format", "json")
    assert json.loads(r.stdout)["results"][0]["counts"]["report"] == 1


def test_cli_patch_mode():
    r = run_py(VERIFY_CLI, "check", "--patch", VERIFY_PATCH, "--svd", SYNTH)
    assert r.returncode == 1
    assert "uart.c (patch)" in r.stdout
    assert "第 13 行" in r.stdout and "第 14 行" in r.stdout


def test_cli_rules_subcommand():
    r = run_py(VERIFY_CLI, "rules", "--format", "json")
    assert r.returncode == 0
    env = json.loads(r.stdout)
    assert env["results"][0]["rules"][0]["class"] == "E01"
    assert len(env["results"][0]["rules"]) == 11


def test_cli_demo_example():
    r = run_py(VERIFY_CLI, "check", DEMO_C, "--demo")
    assert r.returncode == 1
    assert "ETK-DEMO" in r.stdout
    assert "合成数据" in r.stdout


def test_cli_missing_svd_is_error(tmp_path):
    r = run_py(VERIFY_CLI, "check", VERIFY_OK, "--project-dir", str(tmp_path), "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_SVD_NOT_FOUND"


def test_cli_demo_conflicts_with_svd():
    r = run_py(VERIFY_CLI, "check", VERIFY_OK, "--demo", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_INPUT_INVALID"


def test_finding_carries_lookup_hint(device):
    res = crules.Verifier(device).check_file("t.c", "USART1->CR1 |= USART_CR1_XXX;\n")
    hint = res["findings"][0]["lookup"]
    assert hint["action"] == "lookup" and hint["path"] == "USART1.CR1"


def test_nrf_prefix_alias_resolves(device):
    res = crules.Verifier(device).check_file("nrf.c", "NRF_USART1->CR1 |= USART_CR1_UE;\n")
    assert res["counts"]["report"] == 0
    assert res["counts"]["passed"] == 1


def test_nrf_prefix_alias_still_checks_fields(device):
    res = crules.Verifier(device).check_file("nrf.c", "NRF_USART1->CR1 |= USART_CR1_XXX;\n")
    assert res["findings"][0]["class"] == "E03"


def test_nrf_prefix_alias_unknown_peripheral_still_reported(device):
    res = crules.Verifier(device).check_file("nrf.c", "NRF_TIM2->CR1 |= 0x1;\n")
    assert res["findings"][0]["class"] == "E01"


def test_numeric_readonly_field_in_macro_path(device):
    res = crules.Verifier(device).check_file("ro.c", "SET_BIT(RCC->CR, 0x00000400);\n")
    assert [f["class"] for f in res["findings"]] == ["E10"]
    assert "HSIRDY" in res["findings"][0]["message"]


def test_numeric_readonly_field_in_modify_set_value(device):
    res = crules.Verifier(device).check_file("ro.c", "MODIFY_REG(RCC->CR, 0xFFFF, 0x00000400);\n")
    assert [f["class"] for f in res["findings"]] == ["E10"]


def test_modify_clear_mask_alone_not_reported(device):
    res = crules.Verifier(device).check_file("ro.c", "MODIFY_REG(RCC->CR, 0xFFFF, 0x00000001);\n")
    assert res["counts"]["report"] == 0


def test_address_alias_define_checks_register(device):
    text = ("#define TIM1_CR1 (*(volatile uint32_t *)0x40012C00)\n"
            "void f(void) { TIM1_CR1 = 0x00010000; }\n")
    res = crules.Verifier(device).check_file("t.c", text)
    assert [f["class"] for f in res["findings"]] == ["E04"]


def test_address_alias_readonly_register(device):
    text = ("#define USART_SR (*(volatile uint32_t *)0x4001381C)\n"
            "void f(void) { USART_SR = 0x00000020; }\n")
    res = crules.Verifier(device).check_file("t.c", text)
    assert [f["class"] for f in res["findings"]] == ["E10"]


def test_address_alias_unknown_address_is_undetermined(device):
    text = ("#define REGX (*(volatile uint32_t *)0x40013804)\n"
            "void f(void) { REGX = 0x1; }\n")
    res = crules.Verifier(device).check_file("t.c", text)
    assert res["counts"]["report"] == 0
    assert any("别名 REGX" in item["reason"] for item in res["undetermined"])


def test_hwreg_known_address_is_e08(device):
    res = crules.Verifier(device).check_file("t.c", "HWREG(0x40013800) = 0x00000001;\n")
    assert [f["class"] for f in res["findings"]] == ["E08"]
    assert "USART1.CR1" in res["findings"][0]["message"]


def test_hwreg_unresolvable_expression_is_undetermined(device):
    res = crules.Verifier(device).check_file("t.c", "HWREG(UART0_BASE + UART0_CTL) = 0x1;\n")
    assert res["counts"]["report"] == 0
    assert any("地址表达式" in item["reason"] for item in res["undetermined"])


def test_hwreg_macro_composed_address_is_named(device):
    """TI TivaWare 风格：HWREG(外设_BASE + 寄存器偏移) 由宏组合，按具名地址核验、不报 E08。"""
    verifier = crules.Verifier(device, extra_defines={"USART1_BASE": "0x40013800"})
    res = verifier.check_file("t.c", "HWREG(USART1_BASE + 0x1C) = 0x00000001;\n")
    assert [f["class"] for f in res["findings"]] == ["E10"]  # 命中只读 SR → E10（若报 E08 则说明口径错）


def test_channel_suffix_register_naming(tmp_path):
    """通道号在寄存器后缀的 SVD（DMA1 + CCR3/CNDTR3），代码写 DMA1_Channel3->CCR 也要能对上。"""
    svd_text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<device schemaVersion="1.1"><name>CHIPG4</name><version>1.0</version>'
        '<description>channel suffix</description><width>32</width><peripherals>'
        '<peripheral><name>DMA1</name><baseAddress>0x40020000</baseAddress><registers>'
        '<register><name>CCR3</name><addressOffset>0x30</addressOffset><fields>'
        '<field><name>EN</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>'
        '</fields></register>'
        '<register><name>CNDTR3</name><addressOffset>0x34</addressOffset></register>'
        '</registers></peripheral></peripherals></device>\n')
    path = tmp_path / "suffix.svd"
    path.write_text(svd_text, encoding="utf-8")
    device = load_device(str(path))
    res = crules.Verifier(device).check_file(
        "dma.c", "DMA1_Channel3->CNDTR = 0x00000064;\nDMA1_Channel3->CCR |= DMA_CCR_EN;\n")
    assert res["counts"]["passed"] == 2
    assert res["counts"]["undetermined"] == 0
    assert res["findings"] == []


def test_channel_naming_variants(tmp_path):
    """DMA1_CH1 ↔ DMA1_Channel1 同义命名（各厂商 SVD 与头文件混用）。"""
    template = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<device schemaVersion="1.1"><name>CHCHIP</name><version>1.0</version>'
        '<description>channel naming</description><width>32</width><peripherals>'
        '<peripheral><name>%s</name><baseAddress>0x40020000</baseAddress><registers>'
        '<register><name>CCR</name><addressOffset>0x00</addressOffset><fields>'
        '<field><name>EN</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>'
        '</fields></register></registers></peripheral></peripherals></device>\n')
    ch_path = tmp_path / "ch.svd"
    ch_path.write_text(template % "DMA1_CH1", encoding="utf-8")
    res = crules.Verifier(load_device(str(ch_path))).check_file(
        "dma.c", "DMA1_Channel1->CCR |= 0x00000001;\n")
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 0
    full_path = tmp_path / "channel.svd"
    full_path.write_text(template % "DMA1_Channel1", encoding="utf-8")
    res = crules.Verifier(load_device(str(full_path))).check_file(
        "dma.c", "DMA1_CH1->CCR |= 0x00000001;\n")
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 0


def test_reinterpret_cast_address_write_is_e08(device):
    text = "*reinterpret_cast<volatile uint32_t *>(0x40013800) = 0x00000001;\n"
    res = crules.Verifier(device).check_file("t.cpp", text)
    assert [f["class"] for f in res["findings"]] == ["E08"]


def test_more_cast_types_recognized(device):
    for text in ("*(__I uint32_t *)0x40013800 = 0x1;",
                 "*(uint32_t volatile *)0x40013800 = 0x1;",
                 "*(u32 *)0x40013800 = 0x1;",
                 "*(unsigned long *)0x40013800 = 0x1;"):
        res = crules.Verifier(device).check_file("t.c", text)
        assert [f["class"] for f in res["findings"]] == ["E08"], text


def test_renesas_r_prefix_alias(device):
    res = crules.Verifier(device).check_file("ra.c", "R_USART1->CR1 |= USART_CR1_UE;\n")
    assert res["counts"]["report"] == 0
    assert res["counts"]["passed"] == 1


def test_esp_idf_style_macros_are_undetermined(device):
    res = crules.Verifier(device).check_file("idf.c", "REG_WRITE(UART_CONF0_REG, 0x1);\n")
    assert res["counts"]["report"] == 0
    assert res["counts"]["undetermined"] == 1
    assert any("ESP-IDF" in item["reason"] for item in res["undetermined"])


def test_underscore_peripheral_name_macro_mapping(tmp_path):
    """带下划线的外设名（如 RTC_CNTL）：宏前缀要整体消费，否则假字段宏会漏报。"""
    svd_text = """<?xml version="1.0" encoding="utf-8"?>
<device schemaVersion="1.1">
  <name>USCHIP</name>
  <version>1.0</version>
  <description>underscore peripheral test</description>
  <width>32</width>
  <peripherals>
    <peripheral>
      <name>RTC_CNTL</name>
      <baseAddress>0x60008000</baseAddress>
      <registers>
        <register>
          <name>RTC_ULP_CP_TIMER</name>
          <addressOffset>0x00</addressOffset>
          <fields>
            <field>
              <name>EN</name>
              <bitOffset>0</bitOffset>
              <bitWidth>1</bitWidth>
            </field>
          </fields>
        </register>
      </registers>
    </peripheral>
  </peripherals>
</device>
"""
    path = tmp_path / "underscore.svd"
    path.write_text(svd_text, encoding="utf-8")
    device = load_device(str(path))
    res = crules.Verifier(device).check_file(
        "idf.c", "RTC_CNTL->RTC_ULP_CP_TIMER |= RTC_CNTL_RTC_ULP_CP_TIMER_ZZZ;\n")
    assert [f["class"] for f in res["findings"]] == ["E03"]


def test_e11_enable_then_dma_config(device):
    text = ("void f(void)\n{\n"
            "    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
            "    DMA1_Channel1->CNDTR = 0x00000100;\n"
            "}\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    classes = [f["class"] for f in res["findings"]]
    assert classes == ["E11"]
    assert "EN=0" in res["findings"][0]["message"]


def test_e11_setbit_form(device):
    text = ("SET_BIT(DMA1_Channel1->CCR, DMA_CCR_EN);\n"
            "DMA1_Channel1->CMAR = 0x20000000;\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    assert [f["class"] for f in res["findings"]] == ["E11"]


def test_e11_not_when_disabled_between(device):
    text = ("DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
            "DMA1_Channel1->CCR &= ~DMA_CCR_EN;\n"
            "DMA1_Channel1->CNDTR = 0x00000100;\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    assert res["findings"] == []


def test_e11_not_before_enable(device):
    text = ("DMA1_Channel1->CNDTR = 0x00000100;\n"
            "DMA1_Channel1->CCR |= DMA_CCR_EN;\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    assert res["findings"] == []


def test_e11_numeric_enable_on_ctrl_register(device):
    text = ("DMA1_Channel1->CCR |= 0x00000001;\n"
            "DMA1_Channel1->CNDTR = 0x00000100;\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    assert [f["class"] for f in res["findings"]] == ["E11"]


def test_e11_numeric_other_bits_is_not_enable(device):
    text = ("DMA1_Channel1->CCR |= 0x00000010;\n"
            "DMA1_Channel1->CNDTR = 0x00000100;\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    assert res["findings"] == []


def test_e11_numeric_disable_between(device):
    text = ("DMA1_Channel1->CCR |= 0x00000001;\n"
            "DMA1_Channel1->CCR &= ~0x00000001;\n"
            "DMA1_Channel1->CNDTR = 0x00000100;\n")
    res = crules.Verifier(device).check_file("dma.c", text)
    assert res["findings"] == []


def test_eval_int_bit_functions():
    assert cscan.eval_int("BIT(3)", {}) == 8
    assert cscan.eval_int("BIT_MASK(3)", {}) == 7
    assert cscan.eval_int("_BV(5) | BIT(2)", {}) == 0x24
    assert cscan.eval_int("BIT(N)", {"N": "6"}) == 64
    assert cscan.eval_int("BIT(64)", {}) is None


def test_bit_function_in_register_write(device):
    res = crules.Verifier(device).check_file("bit.c", "USART1->CR1 |= BIT(32);\n")
    assert [f["class"] for f in res["findings"]] == ["E04"]
    res = crules.Verifier(device).check_file("bit.c", "USART1->CR1 |= BIT_MASK(8);\n")
    assert res["findings"] == []


def test_headers_resolve_esp_idf_macro(tmp_path):
    header = tmp_path / "regs.h"
    header.write_text("#define USART1_CR1_REG (0x40013800)\n", encoding="utf-8")
    code = tmp_path / "idf.c"
    code.write_text("REG_WRITE(USART1_CR1_REG, 0x00000001);\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(header), "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 0
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 0


def test_headers_esp_idf_set_bit_on_readonly_register(tmp_path):
    header = tmp_path / "regs.h"
    header.write_text("#define USART1_SR_REG 0x4001381C\n", encoding="utf-8")
    code = tmp_path / "idf.c"
    code.write_text("REG_SET_BIT(USART1_SR_REG, 0x00000001);\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(header), "--format", "json")
    res = json.loads(r.stdout)["results"][0]
    assert [f["class"] for f in res["findings"]] == ["E10"]


def test_headers_reg_set_field_checks(tmp_path):
    header = tmp_path / "regs.h"
    header.write_text("#define USART1_CR1_REG (0x40013800)\n"
                      "#define USART1_SR_REG 0x4001381C\n", encoding="utf-8")
    code = tmp_path / "idf.c"
    code.write_text(
        "REG_SET_FIELD(USART1_CR1_REG, USART1_CR1_TE, 0x1);\n"
        "REG_SET_FIELD(USART1_CR1_REG, USART1_CR1_UE, 0x3);\n"
        "REG_SET_FIELD(USART1_CR1_REG, USART1_CR1_ZZZ, 0x1);\n"
        "REG_SET_FIELD(USART1_SR_REG, USART1_SR_TXE, 0x0);\n"
        "REG_CLR_FIELD(USART1_CR1_REG, USART1_CR1_TE);\n",
        encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(header), "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert sorted(f["class"] for f in res["findings"]) == ["E03", "E04", "E10"]
    assert res["counts"]["writes"] == 5
    assert res["counts"]["passed"] == 2
    assert res["counts"]["report"] == 3


def test_eval_int_single_param_function_macro():
    defines = {"F": {"param": "i", "expr": "(0x1000 * (i)) + 0x40"}}
    assert cscan.eval_int("F(3)", defines) == 0x3040
    assert cscan.eval_int("F(1) + F(2)", defines) == 0x3080
    assert cscan.eval_int("F(N)", defines) is None
    assert cscan.eval_int("G(1)", {"G": {"param": "x", "expr": "G(x)"}}) is None


def test_headers_function_macro_address(tmp_path):
    header = tmp_path / "regs.h"
    header.write_text("#define USART1_CR1_REG(i) (0x40013800 + 0x0 * (i))\n", encoding="utf-8")
    code = tmp_path / "idf.c"
    code.write_text("REG_WRITE(USART1_CR1_REG(1), 0x00000001);\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(header), "--format", "json")
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 0


def test_headers_file_cap_note(tmp_path):
    regs = tmp_path / "hdrs"
    regs.mkdir()
    for i in range(520):
        (regs / ("h%03d.h" % i)).write_text("#define H_%03d 0x%X\n" % (i, i), encoding="utf-8")
    (regs / "zzz_regs.h").write_text("#define USART1_CR1_REG (0x40013800)\n", encoding="utf-8")
    code = tmp_path / "x.c"
    code.write_text("REG_WRITE(USART1_CR1_REG, 0x1);\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(regs), "--format", "json")
    assert r.returncode == 0, r.stdout
    env = json.loads(r.stdout)
    assert any("超过上限" in w for w in env["warnings"])


def test_headers_missing_path_is_input_error(tmp_path):
    code = tmp_path / "x.c"
    code.write_text("REG_WRITE(REG_X, 0x1);\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(tmp_path / "nope.h"), "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_INPUT_INVALID"


def test_cli_collects_cpp_and_ino(tmp_path):
    (tmp_path / "main.cpp").write_text("USART1->CR1 |= USART_CR1_XXX;\n", encoding="utf-8")
    (tmp_path / "sketch.ino").write_text("USART1->CR1 |= USART_CR1_ZZZ;\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("USART1->CR1 |= USART_CR1_XXX;\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(tmp_path), "--svd", SYNTH, "--format", "json")
    env = json.loads(r.stdout)
    names = sorted(os.path.basename(res["path"]) for res in env["results"])
    assert names == ["main.cpp", "sketch.ino"]
    assert all(res["counts"]["report"] == 1 for res in env["results"])


def test_cli_attaches_next_commands():
    r = run_py(VERIFY_CLI, "check", VERIFY_BAD, "--svd", SYNTH, "--format", "json")
    findings = json.loads(r.stdout)["results"][0]["findings"]
    e03 = next(f for f in findings if f["class"] == "E03" and "USART1.CR1" in f["message"])
    assert e03["next"][0]["tool"] == "embedded-register-lookup"
    assert e03["next"][0]["args"][:2] == ["lookup", "USART1.CR1"]
    assert "--svd" in e03["next"][0]["args"]
    e08 = next(f for f in findings if f["class"] == "E08")
    assert e08["next"][0]["args"][:2] == ["addr", "0x40013800"]
    e07 = next(f for f in findings if f["class"] == "E07")
    assert e07["next"][0]["args"][:2] == ["lookup", "RCC.APB1ENR"]


def test_cli_explain_inlines_register_facts():
    r = run_py(VERIFY_CLI, "check", VERIFY_BAD, "--svd", SYNTH, "--explain")
    assert "寄存器 USART1.CR1：地址 0x40013800" in r.stdout


def test_cli_without_explain_has_no_explain_field():
    r = run_py(VERIFY_CLI, "check", VERIFY_BAD, "--svd", SYNTH, "--format", "json")
    findings = json.loads(r.stdout)["results"][0]["findings"]
    assert all("explain" not in f for f in findings)


# ---------- 真实厂商 SVD（需要 ETK_TEST_SVD_DIR） ----------

def _find_real(name):
    import glob

    from test_real_svd import SVD_DIRS

    for root in SVD_DIRS:
        hits = glob.glob(os.path.join(root, "**", name), recursive=True)
        if hits:
            return hits[0]
    pytest.skip("%s 不在 ETK_TEST_SVD_DIR 中" % name)


def test_real_f103_snippet_checks():
    device = load_device(_find_real("STM32F103xx.svd"))
    text = (
        "void init(void)\n"
        "{\n"
        "    RCC->APB2ENR |= RCC_APB2ENR_USART1EN | RCC_APB2ENR_IOPAEN;\n"
        "    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;\n"
        "    USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;\n"
        "    GPIOA->CRL = 0x44444444;\n"
        "    GPIOA->IDR = 0x1;\n"        # F103 的 IDR 是只读 → E10
        "    TIM2->CR1 = 0x1FFFF;\n"     # TIM2.CR1 是 32 位 → 不超宽
        "}\n"
    )
    res = crules.Verifier(device).check_file("real.c", text)
    classes = [f["class"] for f in res["findings"]]
    assert classes == ["E10"]
    assert res["counts"]["undetermined"] == 0
    assert res["counts"]["passed"] == 5


def test_real_f103_missing_clock_is_reported():
    device = load_device(_find_real("STM32F103xx.svd"))
    res = crules.Verifier(device).check_file("real.c", "USART1->CR1 |= USART_CR1_UE;\n")
    assert [f["class"] for f in res["findings"]] == ["E07"]


def test_real_g431_hardcoded_address_and_field_macro():
    device = load_device(_find_real("STM32G431xx.svd"))
    res = crules.Verifier(device).check_file(
        "real.c",
        "RCC->APB2ENR |= RCC_APB2ENR_USART1EN;\n"
        "*(volatile uint32_t *)0x40013800 = 1;\n"
        "USART1->CR1 |= USART_CR1_UE;\n")
    assert [f["class"] for f in res["findings"]] == ["E08"]
