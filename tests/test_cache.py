"""解析缓存测试：往返一致性、失效、损坏降级、开关与 CLI 落盘。"""

import json
import os
from dataclasses import asdict

import pytest

from etk_core import cache
from etk_core.svd import load_device
from helpers import SYNTH, run_cli


@pytest.fixture(autouse=True)
def cache_root(tmp_path, monkeypatch):
    target = tmp_path / "cache"
    monkeypatch.setenv(cache.ENV_CACHE_DIR, str(target))
    monkeypatch.delenv(cache.ENV_NO_CACHE, raising=False)
    return target


def _entries(directory):
    if not os.path.isdir(str(directory)):
        return []
    return sorted(f for f in os.listdir(str(directory)) if f.startswith("svd-"))


def test_roundtrip_matches_direct_parse():
    direct = load_device(SYNTH)
    first = cache.load_device_cached(SYNTH)   # 解析并写缓存
    second = cache.load_device_cached(SYNTH)  # 命中缓存
    assert asdict(direct) == asdict(first) == asdict(second)


def test_cache_file_is_written_atomically_and_once():
    cache_root = cache.cache_dir()
    cache.load_device_cached(SYNTH)
    cache.load_device_cached(SYNTH)
    names = os.listdir(cache_root)
    assert len(_entries(cache_root)) == 1
    assert not [n for n in names if n.startswith(".svd-cache-")], "不应残留临时文件"


def test_cache_invalidated_when_file_changes(tmp_path):
    svd = tmp_path / "CHIP.svd"
    svd.write_text(open(SYNTH, encoding="utf-8").read(), encoding="utf-8")
    assert cache.load_device_cached(str(svd)).version == "1.0"
    text = svd.read_text(encoding="utf-8").replace("<version>1.0</version>", "<version>2.0</version>")
    svd.write_text(text, encoding="utf-8")
    assert cache.load_device_cached(str(svd)).version == "2.0"


def test_corrupt_cache_falls_back_to_parse():
    cache.load_device_cached(SYNTH)
    entry = os.path.join(cache.cache_dir(), _entries(cache.cache_dir())[0])
    with open(entry, "w", encoding="utf-8") as fh:
        fh.write("{broken")
    device = cache.load_device_cached(SYNTH)
    assert device.name == "SYNTH32"


def test_stale_stamp_is_refreshed():
    svd = SYNTH
    cache.load_device_cached(svd)
    entry = os.path.join(cache.cache_dir(), _entries(cache.cache_dir())[0])
    with open(entry, encoding="utf-8") as fh:
        data = json.load(fh)
    data["stamp"] = ["elsewhere", 1, 2]
    with open(entry, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    assert cache.load_device_cached(svd).name == "SYNTH32"
    with open(entry, encoding="utf-8") as fh:
        assert json.load(fh)["stamp"][0] != "elsewhere", "回降解析后应立即刷新缓存"


def test_no_cache_env_disables_cache(monkeypatch):
    monkeypatch.setenv(cache.ENV_NO_CACHE, "1")
    assert cache.load_device_cached(SYNTH).name == "SYNTH32"
    assert _entries(cache.cache_dir()) == []


def test_cache_stats_reports_entries():
    cache.load_device_cached(SYNTH)
    stats = cache.cache_stats()
    assert stats["enabled"] is True
    assert stats["count"] == 1


def test_cli_writes_and_reuses_cache(tmp_path):
    env = {"ETK_CACHE_DIR": str(tmp_path)}
    r1 = run_cli("lookup", "USART1.CR1", "--svd", SYNTH, env=env)
    assert r1.returncode == 0, r1.stderr
    files = os.listdir(str(tmp_path))
    assert any(name.startswith("svd-") for name in files)
    r2 = run_cli("lookup", "USART1.CR1", "--svd", SYNTH, env=env)
    assert r2.returncode == 0
    assert json.loads(run_cli("info", "--svd", SYNTH, "--format", "json", env=env).stdout)["results"][0]["device"] == "SYNTH32"
