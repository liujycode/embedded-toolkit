"""SVD 查找测试：--svd、项目配置、本机 CMSIS-Pack。"""

import os
import shutil

import pytest

from etk_core.discovery import _chip_keys, _choose, find_svd, read_config
from etk_core.errors import E_INPUT_INVALID, E_SVD_NOT_FOUND, EtkError
from helpers import SYNTH


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no-local"))
    monkeypatch.delenv("ETK_PACKS_DIR", raising=False)
    monkeypatch.delenv("ETK_SVD_DIR", raising=False)
    return tmp_path


def _copy_svd(directory, name="SYNTH32.svd"):
    os.makedirs(str(directory), exist_ok=True)
    dst = os.path.join(str(directory), name)
    shutil.copy(SYNTH, dst)
    return dst


def test_explicit_svd_path_wins(isolated):
    svd = _copy_svd(isolated / "x")
    path, how, notes = find_svd(svd=svd, chip="ANYTHING", project_dir=str(isolated))
    assert path == os.path.abspath(svd)
    assert how == "参数 --svd"
    assert notes == []


def test_explicit_missing_svd_is_not_found(isolated):
    with pytest.raises(EtkError) as info:
        find_svd(svd=str(isolated / "none.svd"), project_dir=str(isolated))
    assert info.value.code == E_SVD_NOT_FOUND


def test_config_svd_is_relative_to_project_root_and_found_from_subdir(isolated):
    project = isolated / "proj"
    _copy_svd(project / "svd", "x.svd")
    (project / ".etk").mkdir()
    (project / ".etk" / "config.json").write_text('{"svd": "svd/x.svd"}', encoding="utf-8")
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    path, how, _ = find_svd(project_dir=str(nested))
    assert path.endswith(os.path.join("svd", "x.svd"))
    assert how.startswith("项目配置")


def test_config_svd_missing_is_reported(isolated):
    project = isolated / "proj"
    (project / ".etk").mkdir(parents=True)
    (project / ".etk" / "config.json").write_text('{"svd": "nope.svd"}', encoding="utf-8")
    with pytest.raises(EtkError) as info:
        find_svd(project_dir=str(project))
    assert info.value.code == E_SVD_NOT_FOUND


def test_invalid_config_json_is_input_error(isolated):
    project = isolated / "proj"
    (project / ".etk").mkdir(parents=True)
    (project / ".etk" / "config.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(EtkError) as info:
        find_svd(project_dir=str(project))
    assert info.value.code == E_INPUT_INVALID


def test_config_is_not_a_json_object(isolated):
    cfg = isolated / "c.json"
    cfg.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(EtkError) as info:
        read_config(str(cfg))
    assert info.value.code == E_INPUT_INVALID


def test_pack_lookup_strips_package_suffix(isolated, monkeypatch):
    packs = isolated / "packs"
    _copy_svd(packs / "Keil" / "STM32G4xx_DFP" / "1.0.0" / "SVD", "STM32G431xx.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    project = isolated / "proj"
    project.mkdir()
    path, how, _ = find_svd(chip="STM32G431RB", project_dir=str(project))
    assert path.endswith("STM32G431xx.svd")
    assert how == "本机 CMSIS-Pack"


def test_pack_prefers_newer_version_and_notes_the_rest(isolated, monkeypatch):
    packs = isolated / "packs"
    _copy_svd(packs / "Vendor" / "Pack" / "1.0.0" / "SVD", "CHIPX.svd")
    _copy_svd(packs / "Vendor" / "Pack" / "2.0.0" / "SVD", "CHIPX.svd")
    _copy_svd(packs / "Vendor" / "Pack" / "10.0.0" / "SVD", "CHIPX.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    project = isolated / "proj"
    project.mkdir()
    path, _, notes = find_svd(chip="CHIPX", project_dir=str(project))
    assert os.sep.join(["10.0.0", "SVD", "CHIPX.svd"]) in path
    assert notes and "已选用" in notes[0]


def test_chip_config_key_is_used_when_flag_absent(isolated, monkeypatch):
    packs = isolated / "packs"
    _copy_svd(packs / "V" / "P" / "1" / "SVD", "CHIPY.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    project = isolated / "proj"
    (project / ".etk").mkdir(parents=True)
    (project / ".etk" / "config.json").write_text('{"chip": "CHIPY"}', encoding="utf-8")
    path, how, _ = find_svd(project_dir=str(project))
    assert path.endswith("CHIPY.svd")
    assert how == "本机 CMSIS-Pack"


def test_unknown_chip_lists_attempted_locations(isolated):
    with pytest.raises(EtkError) as info:
        find_svd(chip="XYZ999", project_dir=str(isolated))
    assert info.value.code == E_SVD_NOT_FOUND
    assert any("XYZ999" in item for item in info.value.details["tried"])


def test_no_chip_and_no_config_explains_how_to_fix(isolated):
    with pytest.raises(EtkError) as info:
        find_svd(project_dir=str(isolated))
    assert info.value.code == E_SVD_NOT_FOUND
    assert "--chip" in info.value.hint


def test_chip_key_candidates():
    assert _chip_keys("stm32g431rb") == ["STM32G431RB", "STM32G431"]
    assert _chip_keys("NRF52840") == ["NRF52840"]
    assert _chip_keys("STM32F103C8T6") == ["STM32F103C8T6", "STM32F103"]


def test_choose_prefers_exact_stem():
    chosen, others = _choose(["/p/STM32G431xx.svd", "/p/STM32G431.svd"], "STM32G431")
    assert chosen == "/p/STM32G431.svd"
    assert others == ["/p/STM32G431xx.svd"]


def test_real_keil_pack_when_installed(tmp_path, monkeypatch):
    monkeypatch.delenv("ETK_SVD_DIR", raising=False)
    packs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arm", "Packs")
    if not os.path.isdir(os.path.join(packs, "Keil")):
        pytest.skip("本机没有 Keil CMSIS-Pack")
    try:
        path, how, _ = find_svd(chip="STM32F103C8", project_dir=str(tmp_path))
    except EtkError as exc:
        if exc.code == E_SVD_NOT_FOUND:
            pytest.skip("本机 Keil 包中没有 STM32F103 的 SVD")
        raise
    assert os.path.basename(path).upper().startswith("STM32F103")
    assert how == "本机 CMSIS-Pack"


def test_pack_lookup_finds_cmsis_svd_subdir(isolated, monkeypatch):
    """Keil 的 STM32F4/G4 包把 SVD 放在 CMSIS/SVD/ 下，必须能找到。"""
    packs = isolated / "packs"
    _copy_svd(packs / "Keil" / "STM32G4xx_DFP" / "1.4.0" / "CMSIS" / "SVD", "STM32G431xx.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    project = isolated / "proj"
    project.mkdir()
    path, how, _ = find_svd(chip="STM32G431RB", project_dir=str(project))
    assert path.endswith("STM32G431xx.svd")
    assert how == "本机 CMSIS-Pack"


def test_pack_lookup_matches_wildcard_stem(isolated, monkeypatch):
    packs = isolated / "packs"
    svd_dir = packs / "Keil" / "STM32F4xx_DFP" / "2.7.0" / "CMSIS" / "SVD"
    _copy_svd(svd_dir, "STM32F40x.svd")
    _copy_svd(svd_dir, "STM32F401x.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    project = isolated / "proj"
    project.mkdir()
    path, _, _ = find_svd(chip="STM32F407VE", project_dir=str(project))
    assert path.endswith("STM32F40x.svd")
    # 更具体的文件优先：F401 走前缀匹配，不应落到通配的 F40x
    path2, _, _ = find_svd(chip="STM32F401CC", project_dir=str(project))
    assert path2.endswith("STM32F401x.svd")


def test_pack_lookup_wildcard_requires_same_length(isolated, monkeypatch):
    packs = isolated / "packs"
    _copy_svd(packs / "V" / "P" / "1" / "SVD", "WCHIPXY.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    project = isolated / "proj"
    project.mkdir()
    with pytest.raises(EtkError) as info:
        find_svd(chip="WCHIP123", project_dir=str(project))
    assert info.value.code == E_SVD_NOT_FOUND


def test_project_scan_finds_unique_svd_without_chip(isolated):
    project = isolated / "proj"
    _copy_svd(project / "svd", "ONLYONE.svd")
    path, how, _ = find_svd(project_dir=str(project))
    assert path.endswith("ONLYONE.svd")
    assert how == "项目内扫描"


def test_project_scan_matches_chip_name(isolated):
    project = isolated / "proj"
    _copy_svd(project / "deps", "CHIPZ.svd")
    _copy_svd(project / "deps", "OTHERC.svd")
    path, how, _ = find_svd(chip="CHIPZ", project_dir=str(project))
    assert path.endswith("CHIPZ.svd")
    assert how == "项目内扫描"


def test_project_scan_multiple_without_chip_asks_to_disambiguate(isolated):
    project = isolated / "proj"
    _copy_svd(project, "A.svd")
    _copy_svd(project, "B.svd")
    with pytest.raises(EtkError) as info:
        find_svd(project_dir=str(project))
    assert info.value.code == E_SVD_NOT_FOUND
    assert "无法确定" in info.value.message
    assert sorted(info.value.details["found"]) == ["A.svd", "B.svd"]


def test_project_scan_prefers_over_packs(isolated, monkeypatch):
    project = isolated / "proj"
    _copy_svd(project / "svd", "STM32G431xx.svd")
    packs = isolated / "packs"
    _copy_svd(packs / "Keil" / "P" / "1" / "SVD", "STM32G431xx.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    path, how, _ = find_svd(chip="STM32G431", project_dir=str(project))
    assert path.startswith(str(project))
    assert how == "项目内扫描"


def test_env_svd_dir_is_searched(isolated, monkeypatch):
    extra = isolated / "my-svds"
    _copy_svd(extra, "CHIPQ.svd")
    monkeypatch.setenv("ETK_SVD_DIR", str(extra))
    project = isolated / "proj"
    project.mkdir()
    path, how, _ = find_svd(chip="CHIPQ", project_dir=str(project))
    assert path.endswith("CHIPQ.svd")
    assert how == "环境变量 ETK_SVD_DIR"


def test_project_scan_skips_hidden_and_heavy_dirs(isolated):
    from etk_core.discovery import project_svds

    project = isolated / "proj"
    _copy_svd(project / "svd", "VISIBLE.svd")
    _copy_svd(project / ".hidden", "HIDDEN.svd")
    _copy_svd(project / "node_modules", "DEP.svd")
    files, truncated = project_svds(str(project))
    assert [os.path.basename(p) for p in files] == ["VISIBLE.svd"]
    assert truncated is False


def test_list_devices_reports_sources_and_filter(isolated, monkeypatch):
    from etk_core.discovery import list_devices

    project = isolated / "proj"
    _copy_svd(project / "svd", "ALPHA123.svd")
    packs = isolated / "packs"
    _copy_svd(packs / "V" / "P" / "1" / "SVD", "BETA456.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    res = list_devices(str(project))
    names = [e["file"] for e in res["entries"]]
    assert "ALPHA123.svd" in names and "BETA456.svd" in names
    by_source = {e["file"]: e["source"] for e in res["entries"]}
    assert by_source["ALPHA123.svd"] == "项目内扫描"
    assert by_source["BETA456.svd"] == "CMSIS-Pack"
    res2 = list_devices(str(project), keyword="alpha")
    assert [e["file"] for e in res2["entries"]] == ["ALPHA123.svd"]
    assert res2["entries"][0]["device"] == "SYNTH32"


def test_doctor_reports_sources_and_advice(isolated):
    from etk_core.discovery import doctor_report

    project = isolated / "proj"
    _copy_svd(project / "svd", "X.svd")
    res = doctor_report(str(project), demo_path=None)
    assert res["kind"] == "doctor"
    project_check = next(c for c in res["checks"] if "项目内扫描" in c["name"])
    assert project_check["count"] == 1
    assert res["total_svds"] >= 1
    assert res["advice"]
    assert any(not c["exists"] for c in res["checks"])


def test_wildcard_equal_unit():
    from etk_core.discovery import _wildcard_equal

    assert _wildcard_equal("STM32F407", "STM32F40X")
    assert _wildcard_equal("STM32F411VE", "STM32F411XX")
    assert not _wildcard_equal("STM32F407", "STM32F40")
    assert not _wildcard_equal("STM32F407", "STM32F46X")
    assert not _wildcard_equal("STM32F407", "STM32F401X")
