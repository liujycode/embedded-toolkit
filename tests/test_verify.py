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
from helpers import AVR_SVD, FIXTURES, FSP_SVD, MW_SVD, SILABS_SVD, SYNTH, UNION_SVD, WOSYNTH, run_py  # noqa: E402

VERIFY_BAD = os.path.join(FIXTURES, "verify_bad.c")
VERIFY_OK = os.path.join(FIXTURES, "verify_ok.c")
VERIFY_PATCH = os.path.join(FIXTURES, "verify_patch.diff")
ENUM_DEFAULT_SVD = os.path.join(FIXTURES, "enum_default.svd")
CLOCK_ALIAS_SVD = os.path.join(FIXTURES, "clock_alias.svd")
FILE_LEVEL_E09 = os.path.join(FIXTURES, "file_level_e09.c")
FILE_LEVEL_E11 = os.path.join(FIXTURES, "file_level_e11.c")
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
    counts = res["counts"]
    assert {k: counts[k] for k in ("writes", "report", "undetermined", "passed", "findings")} == {
        "writes": 20, "report": 12, "undetermined": 3, "passed": 5, "findings": 13}
    assert sum(counts["report_by_class"].values()) == 13
    assert sum(counts["undetermined_by_category"].values()) == 3
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
    counts = res["counts"]
    assert {k: counts[k] for k in ("writes", "report", "undetermined", "passed", "findings")} == {
        "writes": 1, "report": 0, "undetermined": 0, "passed": 1, "findings": 0}


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
    counts = res["counts"]
    assert {k: counts[k] for k in ("writes", "report", "undetermined", "passed", "findings")} == {
        "writes": 1, "report": 0, "undetermined": 1, "passed": 0, "findings": 0}
    assert counts["undetermined_by_category"] == {"内核外设": 1}
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


def test_enum_constants_resolve_values(tmp_path):
    """文件内 enum 常量：值参与核验（E04 宽度），隐式自增按 C 语义。"""
    code = tmp_path / "enum_vals.c"
    code.write_text(
        "enum { MODE_FAST = 0x2, MODE_SLOW, MODE_MAX = 0x10000 };\n"
        "void f(void)\n{\n"
        "    TIM1->CR1 = MODE_FAST;\n"     # 通过：2 在 16 位内
        "    TIM1->CR1 = MODE_SLOW;\n"     # 通过：隐式自增 = 3
        "    TIM1->CR1 = MODE_MAX;\n"      # E04：0x10000 超 16 位
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 1
    assert res["counts"]["passed"] == 2
    assert res["counts"]["undetermined"] == 0
    assert res["findings"][0]["class"] == "E04"
    assert "0x10000" in res["findings"][0]["message"]


def test_enum_constants_from_headers(tmp_path):
    """--headers 里的 enum 常量同样可求值（typedef enum 形式）。"""
    hdr = tmp_path / "vals.h"
    hdr.write_text("typedef enum { LEVEL_LOW = 1, LEVEL_HIGH = 0x10000 } adc_level_t;\n",
                   encoding="utf-8")
    code = tmp_path / "use.c"
    code.write_text("void f(void)\n{\n    TIM1->CR1 = LEVEL_LOW;\n    TIM1->CR1 = LEVEL_HIGH;\n}\n",
                    encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(hdr), "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 1
    assert res["counts"]["passed"] == 1
    assert res["findings"][0]["class"] == "E04"


def test_patch_mode_uses_full_file_context(tmp_path):
    """补丁模式：磁盘上有完整文件时，E07/E06 能看到未改动的上下文（不误报）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    full = (
        "void init(void)\n"
        "{\n"
        "    RCC->APB2ENR |= RCC_APB2ENR_USART1EN;\n"
        "    USART1->CR1 |= USART_CR1_UE;\n"
        "    USART1->CR1 |= USART_CR1_XXX;\n"
        "}\n")
    (repo / "uart.c").write_text(full, encoding="utf-8")
    diff = (
        "diff --git a/uart.c b/uart.c\n"
        "--- a/uart.c\n"
        "+++ b/uart.c\n"
        "@@ -3,3 +3,4 @@\n"
        "     RCC->APB2ENR |= RCC_APB2ENR_USART1EN;\n"
        "     USART1->CR1 |= USART_CR1_UE;\n"
        "+    USART1->CR1 |= USART_CR1_XXX;\n"
        " }\n")
    patch_file = repo / "changes.diff"
    patch_file.write_text(diff, encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    classes = [f["class"] for f in res["findings"]]
    assert classes == ["E03"]  # 只有新增行的 E03；E07 不报（使能在整文件里可见）
    assert res["counts"]["writes"] == 1
    assert res["findings"][0]["line"] == 5  # 行号对齐新文件


def test_patch_mode_warns_when_full_file_missing(tmp_path):
    """补丁模式找不到完整文件时给出提示（文件级检查可能有误报）。"""
    patch_file = tmp_path / "changes.diff"
    patch_file.write_text(
        "diff --git a/nope.c b/nope.c\n--- a/nope.c\n+++ b/nope.c\n"
        "@@ -1,1 +1,2 @@\n void f(void) {\n+    USART1->CR1 |= USART_CR1_XXX;\n }\n",
        encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH)
    assert r.returncode == 1
    assert "未找到完整文件" in r.stdout


def test_cli_patch_mode():
    r = run_py(VERIFY_CLI, "check", "--patch", VERIFY_PATCH, "--svd", SYNTH)
    assert r.returncode == 1
    assert "uart.c (patch)" in r.stdout
    assert "第 13 行" in r.stdout and "第 14 行" in r.stdout


def test_e13_one_clear_read_modify_write(tmp_path):
    """E13：写 1 清零位域未被掩码覆盖时，读改写会把当前已置位标志顺带清零。"""
    code = tmp_path / "e13.c"
    code.write_text(
        "void f(void)\n{\n"
        "    UART0->UARTICR |= 0x10;\n"                    # E13：RTIC（bit6）未被覆盖
        "    UART0->UARTICR = 0x10;\n"                     # 通过：直写（正确写法）
        "    CLEAR_BIT(UART0->UARTICR, 0x10);\n"           # E13：RTIC 未被覆盖
        "    MODIFY_REG(UART0->UARTICR, 0x10, 0x10);\n"    # E13：RTIC 未被覆盖
        "    UART0->UARTICR &= ~0x10;\n"                   # E13：RTIC 未被覆盖
        "    UART0->ADSR |= 0x1;\n"                        # 通过：唯一 W1C 位域 ADF 被掩码覆盖
        "    UART0->ADSR |= 0x100;\n"                      # E13：ADF 未被覆盖（VALID 是普通位域）
        "    UART0->PERF = 0x1;\n"                         # 通过：寄存器级 oneToClear 的直写
        "    UART0->UARTDR = 0x55;\n"                      # 通过：普通读写寄存器
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", MW_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert [f["class"] for f in res["findings"]] == ["E13"] * 5
    assert res["counts"]["passed"] == 4
    assert "写 1 清零" in res["findings"][0]["message"]
    assert "不在本次写入掩码内" in res["findings"][0]["message"]
    # 文本输出带 next 命令（查看写语义）
    r2 = run_py(VERIFY_CLI, "check", str(code), "--svd", MW_SVD)
    assert "E13" in r2.stdout and "modifiedWriteValues" in r2.stdout


def test_e13_mask_unknown_undetermined(tmp_path):
    """E13：读改写掩码无法静态求值 → 未判定（不猜覆盖范围）。"""
    code = tmp_path / "e13v.c"
    code.write_text(
        "void f(uint32_t flags)\n{\n"
        "    UART0->UARTICR |= flags;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", MW_SVD, "--format", "json")
    assert r.returncode == 0
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 0
    assert res["counts"]["undetermined"] == 1
    assert "掩码无法静态求值" in res["undetermined"][0]["reason"]


def test_e13_conditional_block_downgraded(tmp_path):
    """E13 与其他访问属性类规则一致：条件编译块内 → 未判定（不误报）。"""
    code = tmp_path / "e13c.c"
    code.write_text(
        "void f(void)\n{\n"
        "#ifdef SOME_CONFIG\n"
        "    UART0->UARTICR |= 0x10;\n"
        "#endif\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", MW_SVD, "--format", "json")
    assert r.returncode == 0  # 只有未判定、没有"报"时退出码为 0
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 0
    assert res["counts"]["undetermined"] == 1
    assert "条件编译块" in res["undetermined"][0]["reason"]


def test_modify_reg_positioned_value_not_flagged(tmp_path):
    """ST 风格 MODIFY_REG(reg, Msk, VALUE << Pos)：带位置取值不报 E04；位域之外才报。"""
    code = tmp_path / "modify_pos.c"
    code.write_text(
        "void f(void)\n{\n"
        "    MODIFY_REG(USART1->CR1, USART_CR1_PS_Msk, 0x200);\n"   # 通过：0x200 = 1 << PS_Pos
        "    MODIFY_REG(USART1->CR1, USART_CR1_PS_Msk, 0x1);\n"     # 通过：字段相对写法
        "    MODIFY_REG(USART1->CR1, USART_CR1_PS_Msk, 0x400);\n"   # E04：位 10 不在 PS（bit 9）内
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert [f["class"] for f in res["findings"]] == ["E04"]
    assert res["counts"]["passed"] == 2


def test_e12_writeonly_read_modify_write(tmp_path):
    """E12：只写寄存器上的读改写（|= / SET_BIT）报；直接赋值与读写寄存器不报。"""
    code = tmp_path / "wo.c"
    code.write_text(
        "void f(void)\n{\n"
        "    PORTX->BSRR |= 0x0001;\n"           # E12
        "    PORTX->BSRR = 0x0002;\n"            # 通过（直接赋值）
        "    SET_BIT(PORTX->BSRR, 0x0004);\n"    # E12（宏形式）
        "    CLEAR_BIT(PORTX->ODR, 0x0001);\n"   # 通过（ODR 是读写）
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", WOSYNTH, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 4
    assert res["counts"]["passed"] == 2
    assert [f["class"] for f in res["findings"]] == ["E12", "E12"]
    assert all(f["register"] == "BSRR" for f in res["findings"])


def test_cmsis_union_chain_writes(tmp_path):
    """Microchip SAMD 风格：PORT->Group[0].DIRSET.reg、SERCOM0->USART.CTRLA.reg、EIC->CONFIG[0].reg。"""
    code = tmp_path / "samd.c"
    code.write_text(
        "void f(void)\n{\n"
        "    PORT->Group[0].DIRSET.reg = 0x00000001;\n"     # DIRSET0
        "    PORT->Group[1].DIRSET.reg |= 0x00000002;\n"    # DIRSET1
        "    PORT->Group[0].PINCFG[4].reg = 0x01;\n"        # PINCFG0_4
        "    PORT->Group[1].PINCFG[4].reg = 0x01;\n"        # PINCFG1_4
        "    SERCOM0->USART.CTRLA.reg = 0x1;\n"             # USART.CTRLA
        "    EIC->CONFIG[0].reg |= 0x1;\n"                  # CONFIG0
        "    PORT->Group[ulPort].DIRSET.reg = 1;\n"         # 未判定：组号运行时
        "    EIC->CONFIG[ulIdx].reg |= 0x1;\n"              # 未判定：索引运行时
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", UNION_SVD, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 8
    assert res["counts"]["passed"] == 6
    assert res["counts"]["undetermined"] == 2
    assert res["counts"]["report"] == 0
    reasons = " ".join(u["reason"] for u in res["undetermined"])
    assert "数字后缀" in reasons


def test_dim_field_group_macros(tmp_path):
    """带编号的位域组宏：编号为字面量时直接映射（EXTINT(3)→EXTINT3），运行时编号记未判定。"""
    code = tmp_path / "dim.c"
    code.write_text(
        "void f(void)\n{\n"
        "    EIC->INTENSET.reg = EIC_INTENSET_EXTINT(3);\n"
        "    EIC->INTENSET.reg |= EIC_INTENSET_EXTINT(inMask);\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", UNION_SVD, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 2
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 1
    assert "位域组宏" in res["undetermined"][0]["reason"]


def test_pointer_cast_expression_writes(tmp_path):
    """指针表达式写入：*(volatile uint32_t *)(表达式) = x（具名/字面量/运行时三种）。"""
    code = tmp_path / "ptr.c"
    code.write_text(
        "#define PORT_BASE 0x41004400\n"
        "void f(void)\n{\n"
        "    *(volatile uint32_t *)(PORT_BASE + 0x04) = 0x1;\n"      # 通过（具名）
        "    *(volatile uint32_t *)(0x41004400 + 0x04) = 0x1;\n"     # E08（纯字面量）
        "    *(volatile uint32_t *)(base + 0x04) = 0x1;\n"           # 未判定（运行时基址）
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", UNION_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 3
    assert res["counts"]["passed"] == 1
    assert res["counts"]["report"] == 1
    assert res["counts"]["undetermined"] == 1
    assert res["findings"][0]["class"] == "E08"
    assert "PORT.DIRSET0" in res["findings"][0]["message"]


def test_fsp_bitfield_view_and_conditional(tmp_path):
    """Renesas FSP 风格：REG_b 位域视图、数字后缀组、占位符位域组（SADMACn）、条件编译块降级。"""
    code = tmp_path / "fsp.c"
    code.write_text(
        "void f(void)\n{\n"
        "    R_ICU->IELSR_b[0].IR = 1U;\n"                        # 通过：IELSR0
        "    R_ICU->IELSR_b[irq].IR = 1U;\n"                     # 未判定：运行时下标
        "    R_CPSCU->ICUSARC = ~R_CPSCU_ICUSARC_SADMACn_Msk;\n"  # 未判定：占位符位域组
        "#if BSP_FEATURE_ICU_HAS_INTSELR\n"
        "    R_ICU->INTSELR[0] = 1U;\n"                          # 未判定：条件块内、SVD 无此寄存器
        "    R_FOO->REG = 1U;\n"                                # 未判定：条件块内、外设不存在
        "#endif\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", FSP_SVD, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 5
    assert res["counts"]["report"] == 0
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 4
    reasons = " ".join(u["reason"] for u in res["undetermined"])
    assert "条件编译块" in reasons
    assert "位域组宏" in reasons


def test_fsp_periph_pointer_macro_by_address(tmp_path):
    """外设指针宏按地址解析：R_GPT0 → GPT320、R_TSN_CTRL → TSN（需 --headers）。"""
    hdr = tmp_path / "dev.h"
    hdr.write_text(
        "#define R_GPT0_BASE 0x40169000UL\n"
        "#define R_GPT0 ((R_GPT0_Type *) R_GPT0_BASE)\n"
        "#define R_TSN_CTRL_BASE 0x400F3000UL\n"
        "#define R_TSN_CTRL ((R_TSN_CTRL_Type *) R_TSN_CTRL_BASE)\n", encoding="utf-8")
    code = tmp_path / "app.c"
    code.write_text(
        "void f(void)\n{\n"
        "    R_GPT0->GTWP = 0x0000A500;\n"   # 通过：GPT320.GTWP
        "    R_TSN_CTRL->TSCR = 0x80;\n"     # 通过：TSN.TSCR
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", FSP_SVD,
               "--headers", str(hdr), "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 2
    assert res["counts"]["passed"] == 2
    assert res["counts"]["report"] == 0


def test_conditional_field_macro_not_reported(tmp_path):
    """条件编译块内的位域宏缺失记未判定；条件块外的仍然报 E03（召回不降）。"""
    code = tmp_path / "cond.c"
    code.write_text(
        "void f(void)\n{\n"
        "#if BOARD_V2\n"
        "    USART1->CR1 |= USART_CR1_ZZZ;\n"
        "#endif\n"
        "    USART1->CR1 |= USART_CR1_ZZZ;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 1
    assert res["counts"]["undetermined"] == 1
    assert res["findings"][0]["class"] == "E03"


def test_silabs_port_letter_field_split_and_s_alias(tmp_path):
    """Silicon Labs 风格：端口字母命名（P[3]→PD_DOUT）、REG.FIELD 直写拆分、_S 安全别名。"""
    code = tmp_path / "silabs.c"
    code.write_text(
        "void f(void)\n{\n"
        "    GPIO->P[3].DOUT = 0x1;\n"               # 通过：PD_DOUT（端口字母）
        "    GPIO->CMUROUTE.CLKOUT0ROUTE = 0x2;\n"   # 通过：REG.FIELD 拆分（寄存器 + 字段）
        "    GPIO->P[port].DOUT = 0x1;\n"            # 未判定：端口号为运行时变量
        "    GPIO->CMUROUTE.BOGUS = 0x1;\n"          # 未判定：字段不存在（REG.FIELD 直写）
        "    CMU->CALCNT = 100U;\n"                  # E10：CMU_S.CALCNT 只读（_S 别名）
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SILABS_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 5
    assert res["counts"]["report"] == 1
    assert res["counts"]["passed"] == 2
    assert res["counts"]["undetermined"] == 2
    finding = res["findings"][0]
    assert finding["class"] == "E10"
    assert "CMU_S.CALCNT" in finding["message"]
    reasons = " ".join(u["reason"] for u in res["undetermined"])
    assert "运行时下标" in reasons
    assert "位域直写" in reasons


def test_conditional_readonly_write_downgraded(tmp_path):
    """条件编译块内的只读寄存器写入记未判定（访问属性随型号/配置而异）；块外仍报 E10。"""
    code = tmp_path / "cond_ro.c"
    code.write_text(
        "void f(void)\n{\n"
        "#if EFM32_SERIES1\n"
        "    CMU->CALCNT = 100U;\n"
        "#endif\n"
        "    CMU->CALCNT = 100U;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SILABS_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 1
    assert res["counts"]["undetermined"] == 1
    assert res["findings"][0]["class"] == "E10"
    assert "条件编译块" in res["undetermined"][0]["reason"]


def test_sfr_io_accessor_and_avr_address_space(tmp_path):
    """AVR：_SFR_IO8 按 __SFR_OFFSET 换算；SVD 的 0x800000 口径自动探测；缺偏移记未判定。"""
    code = tmp_path / "avr_io.c"
    code.write_text(
        "#define __SFR_OFFSET 0x20\n"
        "void f(void)\n{\n"
        "    _SFR_IO8(0x05) = 0xFF;\n"
        "    _SFR_MEM8(0x25) = 0x0F;\n"
        "    *(volatile uint8_t *)0x25 = 0x01;\n"
        "    *(volatile unsigned char *)0x25 = 0x02;\n"
        "    *(char *)0x30 = 0x04;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", AVR_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 5
    assert res["counts"]["report"] == 5
    msgs = [f["message"] for f in res["findings"]]
    assert all("PORTB." in m for m in msgs)
    assert sum("SVD 地址 0x00800025" in m for m in msgs) == 4
    assert any("PORTB.CTRL" in m for m in msgs)

    # 缺 __SFR_OFFSET：不猜地址，记未判定（仍计入统计）
    code2 = tmp_path / "avr_io2.c"
    code2.write_text("void f(void)\n{\n    _SFR_IO8(0x05) = 0xFF;\n}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code2), "--svd", AVR_SVD, "--format", "json")
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 1
    assert res["counts"]["undetermined"] == 1
    assert "__SFR_OFFSET" in res["undetermined"][0]["reason"]


def test_field_direct_write_enum_checks(tmp_path):
    """位域直写的枚举核验：不匹配报 E05；带 isDefault 默认项的位域不报。"""
    code = tmp_path / "enum_direct.c"
    code.write_text(
        "void f(void)\n{\n"
        "    PORTB->CTRL.MODE = 1;\n"
        "    PORTB->CTRL.MODE = 2;\n"
        "    PORTB->CTRL.SEL = 2;\n"
        "    PORTB->CTRL.SEL = 3;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", AVR_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 4
    assert res["counts"]["report"] == 1
    assert res["counts"]["passed"] == 3
    finding = res["findings"][0]
    assert finding["class"] == "E05"
    assert "MODE" in finding["message"] and "OFF" in finding["message"]
    assert res["counts"]["report_by_class"] == {"E05": 1}
    # 文本输出带按类计数
    r2 = run_py(VERIFY_CLI, "check", str(code), "--svd", AVR_SVD)
    assert "报 1（E05 1）" in r2.stdout


def test_bitfield_direct_write_value_checks(tmp_path):
    """.bit.FIELD / REG_b.FIELD 直写：值按位域宽度核验（E04）、字段缺失记未判定。"""
    first = tmp_path / "bitfield_union.c"
    first.write_text(
        "void f(void)\n{\n"
        "    PORT->Group[0].PINCFG[4].bit.PMUXEN = 1;\n"
        "    PORT->Group[0].PINCFG[4].bit.PMUXEN = 3;\n"
        "    PORT->Group[0].PINCFG[4].bit.NOPE = 1;\n"
        "    PORT->Group[0].PINCFG[4].bit.LOCK = 1;\n"   # E10：只读位域直写
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(first), "--svd", UNION_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 4
    assert res["counts"]["report"] == 2
    assert res["counts"]["undetermined"] == 1
    assert res["counts"]["passed"] == 1
    classes = sorted(f["class"] for f in res["findings"])
    assert classes == ["E04", "E10"]
    e10 = [f for f in res["findings"] if f["class"] == "E10"][0]
    assert "LOCK" in e10["message"]
    assert "位域直写" in res["undetermined"][0]["reason"]

    second = tmp_path / "bitfield_fsp.c"
    second.write_text(
        "void f(void)\n{\n"
        "    R_ICU->IELSR_b[0].IR = 2;\n"
        "    R_ICU->IELSR_b[0].IR = 1;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(second), "--svd", FSP_SVD, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 1
    assert res["counts"]["passed"] == 1
    assert res["findings"][0]["class"] == "E04"
    assert "IELSR0" in res["findings"][0]["message"]


def test_explain_includes_siblings(tmp_path):
    """--explain：内联寄存器定义，含相关置位/清位寄存器建议。"""
    code = tmp_path / "explain.c"
    code.write_text(
        "void f(void)\n{\n"
        "    PORT->OUT0 = 0x100000000;\n"   # E04：33 位值 → explain 指向 PORT.OUT0
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", UNION_SVD, "--explain", "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    finding = res["findings"][0]
    assert finding["class"] == "E04"
    text = " ".join(finding["explain"])
    assert "OUTSET0（置位）" in text


def test_fuzz_random_snippets_do_not_crash(device):
    """模糊测试：随机拼接的片段不应让解析/核验崩溃（只要求不抛异常、结构完整）。"""
    import random
    rng = random.Random(20261016)
    pool = [
        "PORTX", "USART1", "CR1", "SR", "BRR", "GPIOA", "MODER", "ODR", "DMA1", "CCR1",
        "foo", "x", "bar_1", "MMIO32", "HWREG", "REG_WRITE", "SET_BIT", "BIT", "_SFR_MEM8",
        "=", "|=", "&=", "^=", "(", ")", "{", "}", ";", ",", "~", "<<", ">>", "&", "|",
        "0x1", "1", "0", "255", "0xFFFF0000", "\n", "\t", "#define", "RCC_APB1ENR",
        "TIMG_RTCCALIFG_REG(0)", "HWREGBITW(&v, 3)", "GPIO_ODR(GPIOA)", "\\", "\"s\"",
        "//comment\n", "/*c*/", "->", ".", "[0]", "main(void)", "while(1)",
    ]
    verifier = crules.Verifier(device)
    for i in range(150):
        n = rng.randint(3, 40)
        text = " ".join(rng.choice(pool) for _ in range(n))
        res = verifier.check_file("fuzz_%d.c" % i, text)
        assert set(res["counts"]) >= {"writes", "report", "undetermined", "passed"}
        for f in res["findings"]:
            assert f["class"].startswith("E")
            assert f["line"] >= 1


def test_cli_rules_subcommand():
    r = run_py(VERIFY_CLI, "rules", "--format", "json")
    assert r.returncode == 0
    env = json.loads(r.stdout)
    assert env["results"][0]["rules"][0]["class"] == "E01"
    assert len(env["results"][0]["rules"]) == 13


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
    defines = {"F": {"params": ["i"], "expr": "(0x1000 * (i)) + 0x40"}}
    assert cscan.eval_int("F(3)", defines) == 0x3040
    assert cscan.eval_int("F(1) + F(2)", defines) == 0x3080
    assert cscan.eval_int("F(N)", defines) is None
    assert cscan.eval_int("G(1)", {"G": {"params": ["x"], "expr": "G(x)"}}) is None
    # 旧单参数形式（param）仍兼容
    assert cscan.eval_int("F(3)", {"F": {"param": "i", "expr": "(0x1000 * (i)) + 0x40"}}) == 0x3040


def test_eval_int_multi_param_function_macro():
    defines = {
        "BASE": "0x1000",
        "PAIR": {"params": ["a", "b"], "expr": "(a) * 0x10 + (b)"},
        "GPIOA": "0x48000000",
        "GPIO_ODR": {"params": ["port"], "expr": "MMIO32((port) + 0x14)"},
    }
    assert cscan.eval_int("PAIR(3, 4)", defines) == 0x34
    assert cscan.eval_int("PAIR(BASE / 0x1000, 2)", defines) == 0x12
    assert cscan.eval_int("GPIO_ODR(GPIOA)", defines) == 0x48000014


def test_eval_int_accessor_functions():
    assert cscan.eval_int("MMIO32(0x40000000 + 0x14)", {}) == 0x40000014
    assert cscan.eval_int("REG32(0x40021058)", {}) == 0x40021058
    assert cscan.eval_int("HWREGBITW(0x40000000, 3)", {}) == 0x40000000
    assert cscan.eval_int("_SFR_MEM8(0xC1)", {}) == 0xC1
    assert cscan.eval_int("HWREG(UART0_BASE + UART_O_CTL)", {"UART0_BASE": "0x4000C000", "UART_O_CTL": "0x30"}) == 0x4000C030


def test_alias_define_via_accessor_macro(tmp_path):
    """libopencm3/GD32 风格：#define RCC_APB1ENR MMIO32(RCC_BASE + 0x58) 的别名写入。"""
    code = tmp_path / "rcc.c"
    code.write_text(
        "#define RCC_BASE 0x40021000\n"
        "#define RCC_APB1ENR MMIO32(RCC_BASE + 0x58)\n"
        "void f(void)\n{\n"
        "    RCC_APB1ENR |= (1 << 17);\n"
        "    RCC_APB1ENR = 0x00020000;\n"
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["passed"] == 2
    assert res["counts"]["undetermined"] == 0


def test_function_macro_call_as_lvalue(tmp_path):
    """函数宏调用作左值：GPIO_ODR(GPIOA) |= x（libopencm3 头文件风格）。"""
    code = tmp_path / "gpio.c"
    code.write_text(
        "#define GPIOA 0x48000000\n"
        "#define GPIO_ODR(port) MMIO32((port) + 0x14)\n"
        "void f(void)\n{\n"
        "    GPIO_ODR(GPIOA) |= 0x0001;\n"
        "    GPIO_ODR(0x48000400) = 0x0002;\n"  # 字面量实参也可解析（GPIOB）
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["passed"] == 2
    assert res["counts"]["undetermined"] == 0


def test_bare_register_names(tmp_path):
    """AVR/MSP430 风格裸寄存器名：唯一寄存器名才核验，重名/未知静默忽略。"""
    code = tmp_path / "avr_style.c"
    code.write_text(
        "void f(void)\n{\n"
        "    APB1ENR = 0x00020000;\n"      # RCC.APB1ENR（唯一）→ 通过
        "    CNT = 5;\n"                  # TIM1.CNT（唯一、只读）→ E10
        "    MODER = 0x1;\n"              # GPIOA/B/C 重名 → 静默忽略
        "    LOCAL_VAR = 3;\n"            # 不与寄存器重名 → 静默忽略
        "    ISR |= 0x1;\n"               # DMA1.ISR（唯一）→ 通过
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["writes"] == 3
    assert res["counts"]["passed"] == 2
    assert res["counts"]["report"] == 1
    assert res["counts"]["undetermined"] == 0
    assert res["findings"][0]["class"] == "E10"


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


def test_headers_follow_includes(tmp_path):
    """--headers 给搜索根即可：被核验文件的 #include 会被解析并优先加载（含嵌套包含链）。"""
    root = tmp_path / "inc"
    (root / "soc").mkdir(parents=True)
    (root / "soc" / "soc.h").write_text("#define DR_REG_UART_BASE 0x40013800\n", encoding="utf-8")
    (root / "soc" / "uart_reg.h").write_text(
        '#include "soc/soc.h"\n#define USART1_CR1_REG (DR_REG_UART_BASE + 0x0)\n', encoding="utf-8")
    (root / "decoy.h").write_text("#define DECOY_MACRO 0x1\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    code = src / "main.c"
    code.write_text('#include "soc/uart_reg.h"\n'
                    "void f(void)\n{\n    REG_WRITE(USART1_CR1_REG, 0x00000001);\n}\n",
                    encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(root), "--format", "json")
    assert r.returncode == 0, r.stdout
    env = json.loads(r.stdout)
    res = env["results"][0]
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 0
    assert any("按被核验文件的 #include 优先加载" in w for w in env["warnings"])


def test_headers_follow_includes_basename_fallback(tmp_path):
    """#include 不带目录时按文件名唯一匹配（在搜索根里找）。"""
    root = tmp_path / "inc"
    (root / "soc").mkdir(parents=True)
    (root / "soc" / "uart_reg.h").write_text(
        "#define USART1_CR1_REG (0x40013800)\n", encoding="utf-8")
    code = tmp_path / "main.c"
    code.write_text('#include "uart_reg.h"\n'
                    "void f(void)\n{\n    REG_WRITE(USART1_CR1_REG, 0x00000001);\n}\n",
                    encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(root), "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["passed"] == 1
    assert res["counts"]["undetermined"] == 0


def test_headers_missing_path_is_input_error(tmp_path):
    code = tmp_path / "x.c"
    code.write_text("REG_WRITE(REG_X, 0x1);\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", str(tmp_path / "nope.h"), "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_INPUT_INVALID"


def test_headers_accepts_semicolon_separated_paths(tmp_path):
    """一个 --headers 参数里用分号写多个路径（真实工程多 include 目录）。"""
    inc1 = tmp_path / "inc1"
    inc2 = tmp_path / "inc2"
    inc1.mkdir()
    inc2.mkdir()
    (inc1 / "a.h").write_text("#define REG_A (*(volatile uint32_t *)0x40013800)\n", encoding="utf-8")
    (inc2 / "b.h").write_text("#define REG_B (*(volatile uint32_t *)0x40004400)\n", encoding="utf-8")
    code = tmp_path / "multi.c"
    code.write_text("void f(void)\n{\n    REG_A = 0x1;\n    REG_B = 0x2;\n}\n", encoding="utf-8")
    joined = "%s;%s" % (inc1, inc2)
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", SYNTH,
               "--headers", joined, "--no-clock-check", "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    # REG_A → USART1.CR1（地址别名宏），REG_B → USART2.CR1；两处都解析为"通过"
    assert res["counts"]["writes"] == 2
    assert res["counts"]["passed"] == 2
    assert res["counts"]["undetermined"] == 0


def test_e12_modify_reg_and_clear_field(tmp_path):
    """E12 补齐：MODIFY_REG（modify_reg）与 REG_CLR_FIELD（clear_field）也是读改写。"""
    hdr = tmp_path / "wo.h"
    hdr.write_text("#define WOBASE (*(volatile uint32_t *)0x50000000)\n", encoding="utf-8")
    code = tmp_path / "wo2.c"
    code.write_text(
        "void f(void)\n{\n"
        "    MODIFY_REG(PORTX->BSRR, 0x0001, 0x0001);\n"   # E12：MODIFY_REG 也是读改写
        "    REG_CLR_FIELD(WOBASE, 0x0001);\n"              # E12：REG_CLR_FIELD（clear_field）
        "    MODIFY_REG(PORTX->ODR, 0x0001, 0x0001);\n"     # 通过：ODR 是读写寄存器
        "}\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(code), "--svd", WOSYNTH,
               "--headers", str(hdr), "--format", "json")
    assert r.returncode == 1, r.stdout
    res = json.loads(r.stdout)["results"][0]
    classes = [f["class"] for f in res["findings"]]
    assert classes.count("E12") == 2
    assert res["counts"]["passed"] >= 1
    msgs = " ".join(f["message"] for f in res["findings"])
    assert "MODIFY_REG" in msgs and "REG_CLR_FIELD" in msgs
    # 文本汇总：一处写入命中多条问题时，写清"条问题"
    r2 = run_py(VERIFY_CLI, "check", str(code), "--svd", WOSYNTH, "--headers", str(hdr))
    assert "条问题" in r2.stdout


def test_cli_collects_cpp_and_ino(tmp_path):
    (tmp_path / "main.cpp").write_text("USART1->CR1 |= USART_CR1_XXX;\n", encoding="utf-8")
    (tmp_path / "sketch.ino").write_text("USART1->CR1 |= USART_CR1_ZZZ;\n", encoding="utf-8")
    (tmp_path / "view.hxx").write_text("USART1->CR1 |= USART_CR1_YYY;\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("USART1->CR1 |= USART_CR1_XXX;\n", encoding="utf-8")
    r = run_py(VERIFY_CLI, "check", str(tmp_path), "--svd", SYNTH, "--format", "json")
    env = json.loads(r.stdout)
    names = sorted(os.path.basename(res["path"]) for res in env["results"])
    assert names == ["main.cpp", "sketch.ino", "view.hxx"]
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


# ---------- 文件级规则退出码 / 补丁过滤 / 时钟顺序 / 枚举默认项 ----------

def test_cli_file_level_findings_set_exit_code():
    """E09/E11 只进 findings（counts.report=0），退出码仍须为 1；JSON 结构不变。"""
    expected_counts = {"writes", "report", "undetermined", "passed", "findings",
                       "report_by_class", "undetermined_by_category"}
    for path, cls in ((FILE_LEVEL_E09, "E09"), (FILE_LEVEL_E11, "E11")):
        r = run_py(VERIFY_CLI, "check", path, "--svd", SYNTH, "--format", "json")
        assert r.returncode == 1, r.stdout
        res = json.loads(r.stdout)["results"][0]
        assert set(res["counts"]) == expected_counts
        assert res["counts"]["report"] == 0
        assert [f["class"] for f in res["findings"]] == [cls]
        assert res["findings"][0]["bucket"] == "报"
    r = run_py(VERIFY_CLI, "check", VERIFY_OK, "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stdout
    assert json.loads(r.stdout)["results"][0]["findings"] == []


def test_e05_is_default_is_fallback_only():
    """显式枚举先匹配；没有显式命中时，只有存在 isDefault 项才放行。"""
    device = load_device(ENUM_DEFAULT_SVD)
    res = crules.Verifier(device).check_file(
        "t.c",
        "MOD->CTRL.WITH_DEFAULT = 3;\n"   # 有默认项：放行
        "MOD->CTRL.NO_DEFAULT = 3;\n")    # 无默认项、3 不匹配 A/B：E05
    assert res["counts"]["report"] == 1
    assert res["counts"]["passed"] == 1
    finding = res["findings"][0]
    assert (finding["class"], finding["line"]) == ("E05", 2)
    assert "NO_DEFAULT" in finding["message"]
    assert "OTHER" not in finding["message"]
    # 显式枚举仍然能命中
    res2 = crules.Verifier(device).check_file("t2.c", "MOD->CTRL.WITH_DEFAULT = 1;\n")
    assert res2["findings"] == []


def test_clock_access_before_enable_is_reported(device):
    text = ("USART2->CR1 |= USART_CR1_UE;\n"
            "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;\n")
    res = _check(device, text)
    e07 = [f for f in res["findings"] if f["class"] == "E07"]
    assert len(e07) == 1
    assert e07[0]["line"] == 1
    assert "第 2 行" in e07[0]["message"]


def test_clock_enable_before_access_is_not_reported(device):
    text = ("RCC->APB1ENR |= RCC_APB1ENR_USART2EN;\n"
            "USART2->CR1 |= USART_CR1_UE;\n")
    assert not any(f["class"] == "E07" for f in _check(device, text)["findings"])


def test_clock_enable_underscore_alias_is_conservative():
    """<PERIPH>_EN 别名可用于核验，但不做前缀模糊匹配。"""
    device = load_device(CLOCK_ALIAS_SVD)
    verifier = crules.Verifier(device)
    # 别名被识别：没有使能就访问 → E07（此前因精确匹配不到使能位而静默跳过）
    res = verifier.check_file("t.c", "USART2->CR1 |= USART_CR1_UE;\n")
    assert [f["class"] for f in res["findings"]] == ["E07"]
    # 先使能后访问 → 不报
    res = verifier.check_file(
        "t.c",
        "RCC->APB1ENR |= RCC_APB1ENR_USART2_EN;\n"
        "USART2->CR1 |= USART_CR1_UE;\n")
    assert res["findings"] == []
    # USART10EN 不能当作 USART1 的使能位
    res = verifier.check_file(
        "t.c",
        "RCC->APB1ENR |= RCC_APB1ENR_USART10EN;\n"
        "USART1->CR1 |= USART_CR1_UE;\n")
    assert [f["class"] for f in res["findings"]] == ["E07"]


def _write_patch_repo(tmp_path, name, full, diff):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / name).write_bytes(full.encode("utf-8"))
    patch_file = repo / "changes.diff"
    patch_file.write_bytes(diff.encode("utf-8"))
    return patch_file


def test_patch_mode_ignores_grouping_outside_patch(tmp_path):
    full = (
        "void init(void)\n"
        "{\n"
        "    NVIC_SetPriorityGrouping(3);\n"
        "    NVIC_SetPriorityGrouping(2);\n"
        "    USART1->CR1 |= USART_CR1_UE;\n"
        "    USART1->CR1 |= USART_CR1_TE;\n"
        "}\n")
    diff = (
        "diff --git a/uart.c b/uart.c\n"
        "--- a/uart.c\n"
        "+++ b/uart.c\n"
        "@@ -5,2 +5,3 @@ void init(void)\n"
        "     USART1->CR1 |= USART_CR1_UE;\n"
        "+    USART1->CR1 |= USART_CR1_TE;\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "uart.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert not any(f["class"] == "E09" for f in res["findings"])
    assert res["counts"]["writes"] == 1


def test_patch_mode_reports_grouping_added_in_patch(tmp_path):
    full = (
        "void init(void)\n"
        "{\n"
        "    NVIC_SetPriorityGrouping(3);\n"
        "    NVIC_SetPriorityGrouping(2);\n"
        "    USART1->CR1 |= USART_CR1_UE;\n"
        "    NVIC_SetPriorityGrouping(3);\n"
        "    NVIC_SetPriorityGrouping(2);\n"
        "}\n")
    diff = (
        "diff --git a/uart.c b/uart.c\n"
        "--- a/uart.c\n"
        "+++ b/uart.c\n"
        "@@ -5,2 +5,4 @@ void init(void)\n"
        "     USART1->CR1 |= USART_CR1_UE;\n"
        "+    NVIC_SetPriorityGrouping(3);\n"
        "+    NVIC_SetPriorityGrouping(2);\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "uart.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 0
    assert [f["class"] for f in res["findings"]] == ["E09"]
    assert res["findings"][0]["line"] == 6


def test_patch_mode_reports_second_grouping_added_to_existing(tmp_path):
    """旧文件已有一处分组、补丁再加一处：要归因给补丁（只筛补丁行会漏掉）。"""
    full = (
        "void init(void)\n"
        "{\n"
        "    NVIC_SetPriorityGrouping(3);\n"
        "    USART1->CR1 |= USART_CR1_UE;\n"
        "    NVIC_SetPriorityGrouping(2);\n"
        "}\n")
    diff = (
        "diff --git a/uart.c b/uart.c\n"
        "--- a/uart.c\n"
        "+++ b/uart.c\n"
        "@@ -3,3 +3,4 @@ void init(void)\n"
        "     NVIC_SetPriorityGrouping(3);\n"
        "     USART1->CR1 |= USART_CR1_UE;\n"
        "+    NVIC_SetPriorityGrouping(2);\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "uart.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert [f["class"] for f in res["findings"]] == ["E09"]
    assert res["findings"][0]["line"] == 5


def test_patch_mode_ignores_dma_order_outside_patch(tmp_path):
    full = (
        "void dma_init(void)\n"
        "{\n"
        "    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "    DMA1_Channel1->CNDTR = 0x00000100;\n"
        "    USART1->CR1 |= USART_CR1_TE;\n"
        "}\n")
    diff = (
        "diff --git a/dma.c b/dma.c\n"
        "--- a/dma.c\n"
        "+++ b/dma.c\n"
        "@@ -4,2 +4,3 @@ void dma_init(void)\n"
        "     DMA1_Channel1->CNDTR = 0x00000100;\n"
        "+    USART1->CR1 |= USART_CR1_TE;\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "dma.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert not any(f["class"] == "E11" for f in res["findings"])
    assert res["counts"]["writes"] == 1


def test_patch_mode_reports_dma_order_added_in_patch(tmp_path):
    full = (
        "void dma_init(void)\n"
        "{\n"
        "    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "    DMA1_Channel1->CNDTR = 0x00000100;\n"
        "}\n")
    diff = (
        "diff --git a/dma.c b/dma.c\n"
        "--- a/dma.c\n"
        "+++ b/dma.c\n"
        "@@ -2,1 +2,3 @@ void dma_init(void)\n"
        " {\n"
        "+    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "+    DMA1_Channel1->CNDTR = 0x00000100;\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "dma.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert res["counts"]["report"] == 0
    assert [f["class"] for f in res["findings"]] == ["E11"]
    assert res["findings"][0]["line"] == 4


def test_patch_mode_reports_dma_config_added_after_existing_enable(tmp_path):
    """补丁只加配置写、使能在补丁外：用整文件判先后仍应报 E11。"""
    full = (
        "void dma_init(void)\n"
        "{\n"
        "    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "    DMA1_Channel1->CNDTR = 0x00000100;\n"
        "}\n")
    diff = (
        "diff --git a/dma.c b/dma.c\n"
        "--- a/dma.c\n"
        "+++ b/dma.c\n"
        "@@ -2,2 +2,3 @@ void dma_init(void)\n"
        " {\n"
        "     DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "+    DMA1_Channel1->CNDTR = 0x00000100;\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "dma.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert [f["class"] for f in res["findings"]] == ["E11"]
    assert res["findings"][0]["line"] == 4


def test_patch_mode_reports_dma_enable_added_before_existing_config(tmp_path):
    """补丁只加使能、配置在补丁外：使能行落在补丁内，也应报 E11。"""
    full = (
        "void dma_init(void)\n"
        "{\n"
        "    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "    DMA1_Channel1->CNDTR = 0x00000100;\n"
        "}\n")
    diff = (
        "diff --git a/dma.c b/dma.c\n"
        "--- a/dma.c\n"
        "+++ b/dma.c\n"
        "@@ -2,2 +2,3 @@ void dma_init(void)\n"
        " {\n"
        "+    DMA1_Channel1->CCR |= DMA_CCR_EN;\n"
        "     DMA1_Channel1->CNDTR = 0x00000100;\n"
        " }\n")
    patch_file = _write_patch_repo(tmp_path, "dma.c", full, diff)
    r = run_py(VERIFY_CLI, "check", "--patch", str(patch_file), "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1, r.stdout
    res = json.loads(r.stdout)["results"][0]
    assert [f["class"] for f in res["findings"]] == ["E11"]
    assert res["findings"][0]["line"] == 4


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
