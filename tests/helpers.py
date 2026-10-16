"""测试公共路径与 CLI 调用助手。"""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
SYNTH = os.path.join(FIXTURES, "synthetic.svd")
SYNTH_B = os.path.join(FIXTURES, "synthetic_b.svd")
LINT = os.path.join(FIXTURES, "synthetic_lint.svd")
BROKEN = os.path.join(FIXTURES, "broken.svd")
NOT_DEVICE = os.path.join(FIXTURES, "not_device.xml")
LOOKUP = os.path.join(ROOT, "skills", "embedded-register-lookup", "scripts", "lookup.py")

# 测试用的解析缓存目录：避免污染真实用户缓存
TEST_CACHE_DIR = os.path.join(tempfile.gettempdir(), "etk-test-cache")


def run_py(script, *args, env=None):
    merged = dict(os.environ)
    merged.setdefault("ETK_CACHE_DIR", TEST_CACHE_DIR)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, script] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged,
    )


def run_cli(*args, env=None):
    return run_py(LOOKUP, *args, env=env)
