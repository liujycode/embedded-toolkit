"""测试公共路径与 CLI 调用助手。"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
SYNTH = os.path.join(FIXTURES, "synthetic.svd")
SYNTH_B = os.path.join(FIXTURES, "synthetic_b.svd")
LINT = os.path.join(FIXTURES, "synthetic_lint.svd")
BROKEN = os.path.join(FIXTURES, "broken.svd")
NOT_DEVICE = os.path.join(FIXTURES, "not_device.xml")
LOOKUP = os.path.join(ROOT, "skills", "embedded-register-lookup", "scripts", "lookup.py")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, LOOKUP] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
