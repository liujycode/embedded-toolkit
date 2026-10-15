"""命令行入口测试：通过子进程调用 skills/.../lookup.py，检查输出格式、退出码与错误处理。"""

import json
import re

from helpers import LOOKUP, SYNTH, run_cli


def _script_version():
    with open(LOOKUP, encoding="utf-8") as fh:
        return re.search(r'__version__ = "([^"]+)"', fh.read()).group(1)


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
