"""lint 子命令测试：夹具中植入了各类问题，逐项核对。"""

import json

import pytest

from etk_core import query
from etk_core.errors import E_PERIPH_NOT_FOUND, EtkError
from etk_core.svd import load_device
from helpers import LINT, SYNTH, run_cli


@pytest.fixture(scope="module")
def device():
    return load_device(LINT)


def test_lint_finds_every_planted_issue(device):
    res = query.lint(device)
    codes = sorted({f["code"] for f in res["findings"]})
    assert codes == [
        "duplicate_field", "duplicate_register", "field_out_of_range",
        "field_overlap", "interrupt_value_conflict", "register_alias",
        "register_overlap", "reset_out_of_range",
    ]
    assert res["counts"] == {"error": 6, "warning": 1, "info": 1, "total": 8}
    assert res["truncated"] is False


def test_lint_scope_limits_to_peripheral(device):
    res = query.lint(device, "REG")
    assert res["scope"] == "REG"
    assert res["counts"]["warning"] == 0
    assert all(f["peripheral"] == "REG" for f in res["findings"])


def test_lint_unknown_peripheral_is_reported(device):
    with pytest.raises(EtkError) as info:
        query.lint(device, "NOPE")
    assert info.value.code == E_PERIPH_NOT_FOUND


def test_lint_limit_truncates_findings(device):
    res = query.lint(device, limit=2)
    assert res["truncated"] is True
    assert len(res["findings"]) == 2
    assert res["counts"]["total"] == 8


def test_lint_clean_synthetic_fixture_reports_nothing():
    res = query.lint(load_device(SYNTH))
    assert res["counts"]["total"] == 0


def test_lint_alias_same_offset_is_info_not_error(device):
    res = query.lint(device, "REG")
    alias = [f for f in res["findings"] if f["code"] == "register_alias"]
    assert len(alias) == 1
    assert alias[0]["severity"] == "info"
    assert "ALIAS_A" in alias[0]["message"] and "ALIAS_B" in alias[0]["message"]


def test_lint_cli_json_counts():
    r = run_cli("lint", "--svd", LINT, "--format", "json")
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)["results"][0]
    assert res["kind"] == "lint"
    assert res["counts"] == {"error": 6, "warning": 1, "info": 1, "total": 8}


def test_lint_cli_text_and_scope():
    r = run_cli("lint", "--svd", LINT, "--peripheral", "REG")
    assert r.returncode == 0, r.stderr
    assert "仅外设 REG" in r.stdout
    assert "register_overlap" in r.stdout


def test_lint_cli_limit_must_be_positive():
    r = run_cli("lint", "--svd", LINT, "--limit", "0", "--format", "json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["errors"][0]["code"] == "E_INPUT_INVALID"
