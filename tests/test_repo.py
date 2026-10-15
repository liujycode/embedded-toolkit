"""仓库质量门测试：同步、SKILL.md 规范、3.9 语法、仅标准库依赖。"""

import os
import sys

import pytest

from helpers import ROOT

TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import check_repo  # noqa: E402


def test_repository_passes_all_checks():
    assert check_repo.run_all() == []


def test_frontmatter_keeps_colons_in_values():
    text = "---\nname: demo\ndescription: 用于测试: 冒号 保留\nmetadata:\n  version: \"1.2.3\"\n---\n# 正文\n行二"
    meta, body = check_repo.parse_frontmatter(text)
    assert meta["name"] == "demo"
    assert meta["description"] == "用于测试: 冒号 保留"
    assert meta["metadata"]["version"] == "1.2.3"
    assert body.startswith("# 正文")


def test_frontmatter_requires_closing_marker():
    with pytest.raises(ValueError):
        check_repo.parse_frontmatter("---\nname: x\n# 没有结束标记")


def test_frontmatter_requires_opening_marker():
    with pytest.raises(ValueError):
        check_repo.parse_frontmatter("name: x\n---\n")
