"""核验器量化基准的 CI 化测试（规格 §2.8）：召回、误报、回归集、性能、用例新鲜度。

基准本体在 tools/verify_bench.py；用例是入库的生成物（tests/inject、tests/normal）。
"""

import importlib.util
import os

from helpers import ROOT


def _load_bench():
    path = os.path.join(ROOT, "tools", "verify_bench.py")
    spec = importlib.util.spec_from_file_location("verify_bench", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_bench = _load_bench()


def test_fixtures_fresh():
    issues = _bench.drift_issues()
    assert issues == [], "用例与生成器不一致（运行 python tools/verify_bench.py generate）：%s" % issues


def test_injection_recall_meets_target():
    metrics = _bench.evaluate_injections()
    assert metrics["total"] >= 200, "注入集规模不足：%d" % metrics["total"]
    bad = [row for row in metrics["by_rule"] if not row["ok"]]
    assert bad == [], "召回未达标：%s" % bad
    for row in metrics["by_rule"]:
        assert row["cases"] >= 20, "%s 注入数不足 20：%d" % (row["rule"], row["cases"])


def test_normal_false_positive_rate():
    metrics = _bench.evaluate_normal()
    assert metrics["files"] >= 50, "正样本集不足 50 个文件：%d" % metrics["files"]
    assert metrics["fp_file_ratio"] <= _bench.FP_TARGET, "误报文件：%s" % metrics["offenders"]
    assert metrics["fp_findings_ratio"] <= _bench.FP_TARGET, "误报写入：%s" % metrics["offenders"]


def test_regress_corpus_clean():
    issues = _bench.evaluate_regress()
    assert issues == [], "回归集出现报（误报修复回退）：%s" % issues


def test_performance_1000_lines():
    seconds = _bench.measure_perf()
    assert seconds <= _bench.PERF_TARGET, "1000 行核验耗时 %.3fs 超过 %.1fs" % (
        seconds, _bench.PERF_TARGET)
