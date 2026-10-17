"""命令行入口测试：通过子进程调用 skills/.../lookup.py，检查输出格式、退出码与错误处理。"""

import json
import re

from helpers import AVR_SVD, LOOKUP, SYNTH, SYNTH_B, UNION_SVD, run_cli


def _script_version():
    with open(LOOKUP, encoding="utf-8") as fh:
        return re.search(r'__version__ = "([^"]+)"', fh.read()).group(1)


def test_lookup_sibling_registers():
    """相关寄存器（置位/清位/翻转视图）按命名自动关联：PORT.OUT0 → OUTSET0/OUTCLR0/OUTTGL0。"""
    r = run_cli("lookup", "PORT.OUT0", "--svd", UNION_SVD, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    sib = {(s["name"], s["kind"]) for s in res["siblings"]}
    assert ("OUTSET0", "置位") in sib
    assert ("OUTCLR0", "清位") in sib
    assert ("OUTTGL0", "翻转") in sib
    assert ("OUT0_XOR", "翻转") in sib  # RP2040 风格 _XOR 视图
    # 人类可读输出里也带提示
    r2 = run_cli("lookup", "PORT.OUT0", "--svd", UNION_SVD)
    assert "相关寄存器" in r2.stdout
    assert "OUTSET0（置位）" in r2.stdout


def test_lookup_json_envelope_and_field(tmp_path):
    r = run_cli("lookup", "USART1.CR1.UE", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    env = json.loads(r.stdout)
    assert env["ok"] is True
    assert env["tool"] == "embedded-register-lookup"
    assert env["version"] == _script_version()
    res = env["results"][0]
    assert res["kind"] == "field"
    assert res["field"]["bits"] == "0"
    assert res["source"]["file"] == "synthetic.svd"
    assert res["source"]["selected_by"] == "参数 --svd"


def test_lookup_text_is_chinese_with_label_and_source():
    r = run_cli("lookup", "USART1.CR1", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "USART1.CR1" in r.stdout
    assert "[已核验]" in r.stdout
    assert "来源：synthetic.svd" in r.stdout
    assert "位域：" in r.stdout


def test_text_error_has_code_hint_and_no_traceback():
    r = run_cli("lookup", "USART9", "--svd", SYNTH)
    assert r.returncode == 1
    combined = r.stdout + r.stderr
    assert "E_PERIPH_NOT_FOUND" in combined
    assert "USART1" in combined
    assert "Traceback" not in combined


def test_json_error_envelope():
    r = run_cli("lookup", "USART1.CR9", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    env = json.loads(r.stdout)
    assert env["ok"] is False
    assert env["errors"][0]["code"] == "E_REG_NOT_FOUND"
    assert "CR1" in env["errors"][0]["details"]["suggestions"]


def test_missing_svd_is_reported_with_attempts(tmp_path):
    r = run_cli("list", "--project-dir", str(tmp_path), "--format", "json")
    assert r.returncode == 1
    env = json.loads(r.stdout)
    assert env["errors"][0]["code"] == "E_SVD_NOT_FOUND"
    assert env["errors"][0]["details"]["tried"]


def test_address_text_inside_register():
    r = run_cli("addr", "0x40013801", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "位于寄存器 USART1.CR1 内部" in r.stdout


def test_decode_text_shows_undefined_bits():
    r = run_cli("decode", "USART1.CR1", "0x109", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "未定义位" in r.stdout
    assert "bit 8" in r.stdout


def test_search_json_total():
    r = run_cli("search", "baud", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["results"][0]["total"] == 6


def test_list_text_shows_derivation():
    r = run_cli("list", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "派生自 USART1" in r.stdout


def test_out_option_writes_file(tmp_path):
    out = tmp_path / "result.json"
    r = run_cli("search", "TXE", "--svd", SYNTH, "--format", "json", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert "已写入" in r.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["results"][0]["total"] == 3


def test_bad_number_is_input_error():
    r = run_cli("addr", "zzz", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_INPUT_INVALID"


def test_search_limit_must_be_positive():
    r = run_cli("search", "USART", "--limit", "0", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_INPUT_INVALID"


def test_unknown_subcommand_exits_with_usage_error():
    r = run_cli("frobnicate")
    assert r.returncode == 2


def test_help_exits_zero():
    r = run_cli("--help")
    assert r.returncode == 0
    assert "lookup" in r.stdout


def test_fields_command_lists_masks():
    r = run_cli("fields", "USART1.CR1", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "掩码 0x00008000" in r.stdout
    assert "未定义位" in r.stdout


def test_diagram_command_draws_symbols_and_legend():
    r = run_cli("diagram", "USART1.CR1", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "O..M..P." in r.stdout
    assert "O=OVER8 b15" in r.stdout


def test_set_command_computes_register_value():
    r = run_cli("set", "TIM1.CR1", "CEN=1", "DIR=DOWN", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "结果：0x0011" in r.stdout


def test_set_command_json_reports_enum():
    r = run_cli("set", "TIM1.CR1", "DIR=DOWN", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "set"
    assert res["value"] == 0x10
    assert res["assignments"][0]["via_enum"] == "DOWN"


def test_set_unknown_field_is_error():
    r = run_cli("set", "TIM1.CR1", "CENN=1", "--svd", SYNTH)
    assert r.returncode == 1
    assert "E_FIELD_NOT_FOUND" in r.stdout


def test_diff_self_compare_warns_and_is_identical():
    r = run_cli("diff", "USART1.CR1", "--svd-a", SYNTH, "--svd-b", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "自比对" in r.stdout
    assert "两侧寄存器定义一致" in r.stdout


def test_diff_reports_differences_between_fixtures():
    r = run_cli("diff", "USART1.CR1", "--svd-a", SYNTH, "--svd-b", SYNTH_B, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["a"]["source"]["file"] == "synthetic.svd"
    assert res["b"]["source"]["file"] == "synthetic_b.svd"
    assert res["identical"] is False
    text = run_cli("diff", "USART1.CR1", "--svd-a", SYNTH, "--svd-b", SYNTH_B)
    assert "位 3 → 4" in text.stdout
    assert "仅 B 侧有" in text.stdout


def test_range_command_lists_registers():
    r = run_cli("range", "0x40013800", "0x4001381F", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "共 3 个" in r.stdout
    assert "USART1.BRR" in r.stdout


def test_range_reversed_bounds_is_error():
    r = run_cli("range", "0x100", "0x10", "--svd", SYNTH)
    assert r.returncode == 1
    assert "E_INPUT_INVALID" in r.stdout


def test_info_command_reports_hash_and_counts():
    r = run_cli("info", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "info"
    assert res["vendor"] == "SYNTH-Corp"
    assert res["counts"]["registers"] == 36
    assert len(res["sha256"]) == 64


def test_decode_accepts_multiple_values():
    r = run_cli("decode", "USART1.CR1", "0x109", "0x200", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    env = json.loads(r.stdout)
    assert [res["value"] for res in env["results"]] == [0x109, 0x200]


def test_search_kind_filter():
    r = run_cli("search", "USART", "--kind", "peripheral", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["total"] == 3
    assert all(m["kind"] == "peripheral" for m in res["matches"])


def test_irq_command_filters_by_name():
    r = run_cli("irq", "USART", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "irq"
    assert res["total"] == 3


def test_irq_command_by_number():
    r = run_cli("irq", "39", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "USART3_IRQn" in r.stdout


def test_irq_command_lists_all_without_query():
    r = run_cli("irq", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["results"][0]["total"] == 5


def test_macros_command_emits_c_defines():
    r = run_cli("macros", "TIM1.CR1", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "#define TIM1_CR1_CEN_Pos 0U" in r.stdout
    assert "#define TIM1_CR1_ADDR 0x40012C00UL" in r.stdout


def test_macros_unknown_path_is_error():
    r = run_cli("macros", "TIM1.CR9", "--svd", SYNTH)
    assert r.returncode == 1
    assert "E_REG_NOT_FOUND" in r.stdout


def test_decode_write_flag_text():
    r = run_cli("decode", "TIM1.CNT", "5", "--write", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "写入提示" in r.stdout


def test_lookup_accepts_multiple_paths():
    r = run_cli("lookup", "USART1.CR1", "USART1.BRR", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    env = json.loads(r.stdout)
    assert [res["kind"] for res in env["results"]] == ["register", "register"]
    assert [res["register"]["name"] for res in env["results"]] == ["CR1", "BRR"]


def test_lookup_partial_failure_keeps_other_results():
    r = run_cli("lookup", "USART1.CR1", "USART1.CR9", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 1
    env = json.loads(r.stdout)
    assert env["ok"] is False
    assert len(env["results"]) == 1
    assert env["errors"][0]["code"] == "E_REG_NOT_FOUND"


def test_fields_accepts_multiple_registers():
    r = run_cli("fields", "USART1.CR1", "USART1.BRR", "--svd", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["results"]) == 2


def test_diff_accepts_multiple_registers():
    r = run_cli("diff", "USART1.CR1", "USART1.BRR", "--svd-a", SYNTH, "--svd-b", SYNTH, "--format", "json")
    assert r.returncode == 0, r.stderr
    env = json.loads(r.stdout)
    assert [res["path"] for res in env["results"]] == ["USART1.CR1", "USART1.BRR"]
    assert all(res["identical"] for res in env["results"])


def test_format_md_produces_tables():
    r = run_cli("fields", "USART1.CR1", "--svd", SYNTH, "--format", "md")
    assert r.returncode == 0, r.stderr
    assert "| 位 | 位域 | 访问 | 复位 | 掩码 | 说明 |" in r.stdout
    assert "_已核验" in r.stdout


def test_format_md_register_lookup_with_enums():
    r = run_cli("lookup", "USART1.CR1", "--svd", SYNTH, "--format", "md")
    assert r.returncode == 0, r.stderr
    assert "## USART1.CR1" in r.stdout
    assert "**枚举**" in r.stdout


def test_format_md_error_block():
    r = run_cli("lookup", "USART9", "--svd", SYNTH, "--format", "md")
    assert r.returncode == 1
    assert "## 错误" in r.stdout
    assert "E_PERIPH_NOT_FOUND" in r.stdout


def test_format_md_macros_uses_code_fence():
    r = run_cli("macros", "TIM1.CR1", "--svd", SYNTH, "--format", "md")
    assert r.returncode == 0, r.stderr
    assert "```c" in r.stdout
    assert "#define TIM1_CR1_CEN_Pos 0U" in r.stdout


def test_devices_cli_reports_sources(tmp_path):
    r = run_cli("devices", "--project-dir", str(tmp_path), "--filter", "ZZ_NO_SUCH_CHIP", "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "devices"
    assert res["total"] == 0
    assert res["sources"][0]["name"] == "项目内扫描"
    assert res["sources"][0]["count"] == 0


def test_doctor_cli_reports_checks_and_advice():
    r = run_cli("doctor", "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "doctor"
    assert res["python"].count(".") == 2
    assert any("演示" in c["name"] for c in res["checks"])
    assert res["advice"]


def test_demo_cli_quickstart():
    r = run_cli("set", "GPIOA.MODER", "MODE0=OUTPUT", "MODE1=ALTERNATE", "--demo")
    assert r.returncode == 0, r.stderr
    assert "结果：0x00000009" in r.stdout


def test_diff_peripheral_cli_hides_identical_by_default():
    r = run_cli("diff", "USART1", "--svd-a", SYNTH, "--svd-b", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "外设整体对比" in r.stdout
    assert "[相同]" not in r.stdout
    assert "已省略" in r.stdout
    assert "两侧外设定义一致" in r.stdout


def test_diff_peripheral_cli_all_flag_shows_identical():
    r = run_cli("diff", "USART1", "--svd-a", SYNTH, "--svd-b", SYNTH, "--all")
    assert r.returncode == 0, r.stderr
    assert "[相同] CR1" in r.stdout


def test_diff_peripheral_cli_reports_differences():
    r = run_cli("diff", "USART1", "--svd-a", SYNTH, "--svd-b", SYNTH_B)
    assert r.returncode == 0, r.stderr
    assert "[有差异] CR1" in r.stdout
    assert "[仅 A 侧有] BRR" in r.stdout
    assert "外设基地址已变化" in r.stdout


def test_diff_peripheral_cli_json():
    r = run_cli("diff", "USART1", "--svd-a", SYNTH, "--svd-b", SYNTH_B, "--format", "json")
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "diff_peripheral"
    assert res["counts"]["only_a"] == 2
    assert res["show_all"] is False


def test_search_cli_peripheral_scope():
    r = run_cli("search", "MODE", "--peripheral", "GPIOA", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "GPIOA." in r.stdout
    assert "USART" not in r.stdout


def test_irq_cli_shows_nvic_hint():
    r = run_cli("irq", "37", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "NVIC：使能 NVIC.ISER1 bit 5" in r.stdout
    assert "清挂起 NVIC.ICPR1 bit 5" in r.stdout
    assert "优先级 NVIC.IPR9 第 1 字节" in r.stdout


def test_set_cli_shows_rmw_hazard():
    r = run_cli("set", "EXTI.PR", "P1=1", "--svd", SYNTH)
    assert r.returncode == 0, r.stderr
    assert "reg |=" in r.stdout


def test_set_cli_shows_read_action_note():
    """readAction=modifyExternal（读后由硬件修改）时，读改写提示一并给出。"""
    r = run_cli("decode", "PORTB.STAT", "0x01", "--write", "--svd", AVR_SVD)
    assert r.returncode == 0, r.stderr
    assert "modifyExternal" in r.stdout
    assert "读改写" in r.stdout


def test_macros_default_enum_comment():
    """macros 输出：isDefault 默认项显示为"默认项：其余取值"，不写成位模式注释。"""
    r = run_cli("macros", "PORTB.CTRL.SEL", "--svd", AVR_SVD)
    assert r.returncode == 0, r.stderr
    assert "默认项 OTHER" in r.stdout
    assert "含任意位" not in r.stdout
