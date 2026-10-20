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
    """检索评测：全部场景查询命中期望的树/坑位（召回 100% 硬门禁）；
    p@1 设 0.9 下限（排序口径与 CLI 一致），并回归"USB 识别不到"必须排第 1。"""
    rows, hit, total, miss, p1, mrr = knowledge_bench.evaluate()
    assert total >= 100, "用例数不应缩水：%d" % total
    assert hit == total, "未命中：%s" % [(m[0], m[1], m[2]) for m in miss]
    assert 0.0 <= p1 <= 1.0 and 0.0 <= mrr <= 1.0, \
        "p@1/MRR 应为 0..1（p@1=%.4f, MRR=%.4f）" % (p1, mrr)
    assert p1 >= 0.9, "p@1 低于下限 0.9：%.4f（检查 bench 与 CLI 排序是否同源）" % p1
    usb = [r for r in rows if r[0] == "debug-trees" and r[1] == "USB 识别不到"]
    assert usb and usb[0][3] == 1, "排序回归：'USB 识别不到' 应排第 1，实际 %s" % (
        usb[0][3] if usb else "用例缺失")
    r = run_py(TREES_CLI, "search", "USB 识别不到", "--format", "json")
    res = json.loads(r.stdout)
    assert res["hits"][0]["tree"] == "usb", "CLI 排序与评测不一致"


def test_next_fields_are_executable_commands():
    """所有 next 都必须是 <skill-id> <subcommand> [--flag <占位符>] 形式的命令。"""
    problems = []
    for skill in knowledge_check.SKILLS:
        db = knowledge_check._load(skill)
        if skill == "embedded-debug-trees":
            for tree in db["trees"]:
                for node in knowledge_check._iter_nodes(tree):
                    knowledge_check._lint_next(node, problems, 2)
        else:
            for cat in db["categories"]:
                for p in cat["pitfalls"]:
                    knowledge_check._lint_next(p, problems, 2)
    assert problems == [], problems


def test_next_lint_rejects_prose_and_unknown_cli():
    """next 校验必须拦住散文、未知技能、未知子命令和 CLI 不支持的参数。"""
    cases = [
        ({"id": "ok1", "next": "embedded-timing-calc i2c-rp --bus fast --cb <Cb_pF>"}, False),
        ({"id": "ok2", "next": "embedded-register-lookup lookup <USB>.EP0R --chip <芯片>"}, False),
        ({"id": "bad-prose", "next": "用 embedded-timing-calc 算一下采样点"}, True),
        ({"id": "bad-skill", "next": "timing-calc uart --pclk 48 --baud 115200"}, True),
        ({"id": "bad-sub", "next": "embedded-timing-calc no-such-sub --clk 48"}, True),
        ({"id": "bad-flag", "next": "embedded-timing-calc can-bit --clk 48 --no-such-flag 1"}, True),
        ({"id": "bad-prose2", "next": "embedded-timing-calc uart --pclk 48 --baud 115200 核对误差"}, True),
    ]
    for node, should_fail in cases:
        problems = []
        knowledge_check._lint_next(node, problems, 2)
        assert bool(problems) == should_fail, (node["next"], problems)


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
