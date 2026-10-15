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
    path, how, _ = find_svd(chip="STM32G431RB", project_dir=str(isolated))
    assert path.endswith("STM32G431xx.svd")
    assert how == "本机 CMSIS-Pack"


def test_pack_prefers_newer_version_and_notes_the_rest(isolated, monkeypatch):
    packs = isolated / "packs"
    _copy_svd(packs / "Vendor" / "Pack" / "1.0.0" / "SVD", "CHIPX.svd")
    _copy_svd(packs / "Vendor" / "Pack" / "2.0.0" / "SVD", "CHIPX.svd")
    _copy_svd(packs / "Vendor" / "Pack" / "10.0.0" / "SVD", "CHIPX.svd")
    monkeypatch.setenv("ETK_PACKS_DIR", str(packs))
    path, _, notes = find_svd(chip="CHIPX", project_dir=str(isolated))
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


def test_real_keil_pack_when_installed():
    packs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arm", "Packs")
    if not os.path.isdir(os.path.join(packs, "Keil")):
        pytest.skip("本机没有 Keil CMSIS-Pack")
    try:
        path, how, _ = find_svd(chip="STM32F103C8", project_dir=os.path.dirname(packs))
    except EtkError as exc:
        if exc.code == E_SVD_NOT_FOUND:
            pytest.skip("本机 Keil 包中没有 STM32F103 的 SVD")
        raise
    assert os.path.basename(path).upper().startswith("STM32F103")
    assert how == "本机 CMSIS-Pack"
