"""知识技能（排障决策树 / 外设配置坑）质量测试：schema、检索评测、CLI 行为。"""

import importlib.util
import json
import os
import sys

import pytest

from helpers import ROOT, run_py  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))

TREES_CLI = os.path.join(ROOT, "skills", "embedded-debug-trees", "scripts", "trees.py")
PITFALLS_CLI = os.path.join(ROOT, "skills", "embedded-peripheral-pitfalls", "scripts", "pitfalls.py")


def _load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


knowledge_check = None
knowledge_bench = None


def setup_module(module):
    global knowledge_check, knowledge_bench
    knowledge_check = _load_tool("knowledge_check")
    knowledge_bench = _load_tool("knowledge_bench")


def test_knowledge_schema_and_same_source():
    """schema 校验（必填字段/唯一 id）+ references 与 JSON 同源。"""
    assert knowledge_check.run_check() == []


def test_knowledge_retrieval_bench():
    """检索评测：106 条场景查询全部命中期望的树/坑位。"""
    rows, hit, total, miss = knowledge_bench.evaluate()
    assert total >= 100, "用例数不应缩水：%d" % total
    assert hit == total, "未命中：%s" % [(m[0], m[1], m[2]) for m in miss]


def test_cli_demo_self_check():
    """两技能 demo 自检（加载 + 典型检索探针）通过。"""
    r = run_py(TREES_CLI, "demo")
    assert r.returncode == 0 and "自检通过" in r.stdout
    r = run_py(PITFALLS_CLI, "demo")
    assert r.returncode == 0 and "自检通过" in r.stdout


def test_cli_search_json_and_not_found():
    """search 的 JSON 输出有效；未命中返回 1 并明说不编造。"""
    r = run_py(TREES_CLI, "search", "DMA 丢数据", "--format", "json")
    assert r.returncode == 0
    res = json.loads(r.stdout)
    assert res["kind"] == "search" and res["total"] > 0
    assert res["hits"][0]["tree"] == "dma"
    r = run_py(PITFALLS_CLI, "search", "上拉电阻", "--format", "json")
    res = json.loads(r.stdout)
    assert res["hits"] and any(
        h["id"] in ("i2c-pullup", "gpio-i2c-pushpull") for h in res["hits"])
    r = run_py(TREES_CLI, "search", "完全无关的查询词组")
    assert r.returncode == 1 and "E_NOT_FOUND" in r.stdout
    r = run_py(PITFALLS_CLI, "search", "完全无关的查询词组", "--format", "json")
    assert r.returncode == 1
    res = json.loads(r.stdout)
    assert res["total"] == 0


def test_cli_version_matches_metadata():
    """脚本 __version__ 与 SKILL.md metadata.version 一致。"""
    for cli, skill in ((TREES_CLI, "embedded-debug-trees"),
                       (PITFALLS_CLI, "embedded-peripheral-pitfalls")):
        r = run_py(cli, "--version")
        assert r.returncode == 0
        script_ver = r.stdout.strip()
        with open(os.path.join(ROOT, "skills", skill, "SKILL.md"), encoding="utf-8") as fh:
            md = fh.read()
        meta = md.split("---")[1]
        assert 'version: "%s"' % script_ver in meta, "%s 版本不一致" % skill


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
