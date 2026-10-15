#!/usr/bin/env python3
"""把 shared/etk_core 同步到每个技能的 scripts/etk_core。

原因：`npx skills add` 或插件安装只拷贝单个技能目录，技能必须自带核心库。
shared/etk_core 是唯一的源码；技能内的副本由本脚本生成，不要手工修改。

用法：
  python tools/sync_core.py           # 同步
  python tools/sync_core.py --check   # 只检查；不一致时退出码为 1
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "shared", "etk_core")


def skill_targets():
    base = os.path.join(ROOT, "skills")
    targets = []
    for name in sorted(os.listdir(base)):
        scripts = os.path.join(base, name, "scripts")
        if os.path.isdir(scripts):
            targets.append(os.path.join(scripts, "etk_core"))
    return targets


def _py_files(directory):
    return sorted(f for f in os.listdir(directory) if f.endswith(".py"))


def diff(target):
    rel = os.path.relpath(target, ROOT)
    if not os.path.isdir(target):
        return ["缺少 %s" % rel]
    problems = []
    src_files = _py_files(SRC)
    dst_files = _py_files(target)
    for name in src_files:
        if name not in dst_files:
            problems.append("缺少 %s" % os.path.join(rel, name))
        elif not filecmp.cmp(os.path.join(SRC, name), os.path.join(target, name), shallow=False):
            problems.append("内容与 shared 不一致 %s" % os.path.join(rel, name))
    for name in dst_files:
        if name not in src_files:
            problems.append("多余文件 %s" % os.path.join(rel, name))
    return problems


def sync(target):
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(SRC, target, ignore=shutil.ignore_patterns("__pycache__"))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="同步 shared/etk_core 到各技能")
    parser.add_argument("--check", action="store_true", help="只检查，不写入")
    args = parser.parse_args(argv)
    if args.check:
        problems = [p for t in skill_targets() for p in diff(t)]
        for p in problems:
            print("不同步：" + p)
        if problems:
            print("请运行 python tools/sync_core.py 重新同步。")
            return 1
        print("etk_core 副本与 shared 一致。")
        return 0
    for target in skill_targets():
        sync(target)
        print("已同步 " + os.path.relpath(target, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
