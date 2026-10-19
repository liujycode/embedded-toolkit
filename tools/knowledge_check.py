#!/usr/bin/env python3
"""知识库校验与文档生成（embedded-debug-trees / embedded-peripheral-pitfalls）。

- 校验：schema（必填字段/唯一 id/keywords/fixes）、id 全局唯一、references 与 JSON 同源。
- 生成：references/trees.md、references/pitfalls.md 由 assets/*.json 生成（保证同源）。

用法：
  python tools/knowledge_check.py --check   # 校验（不一致退出码 1）
  python tools/knowledge_check.py --doc     # 重新生成 references
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = {
    "embedded-debug-trees": {
        "data": "assets/trees.json",
        "reference": "references/trees.md",
        "item_key": "trees",
    },
    "embedded-peripheral-pitfalls": {
        "data": "assets/pitfalls.json",
        "reference": "references/pitfalls.md",
        "item_key": "categories",
    },
}

HEADER = "<!-- 本文件由 tools/knowledge_check.py --doc 从 assets/*.json 生成，勿手改。 -->"


def _load(skill):
    path = os.path.join(ROOT, "skills", skill, SKILLS[skill]["data"])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _iter_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from _iter_nodes(child)


def lint_db(skill, db, problems):
    """schema 校验：必填字段、唯一 id、keywords/fixes 非空。"""
    seen = set()
    if skill == "embedded-debug-trees":
        for tree in db["trees"]:
            if not tree.get("rootcauses"):
                problems.append("树 %s 缺 rootcauses" % tree["id"])
            if not tree.get("title"):
                problems.append("树 %s 缺 title" % tree["id"])
            for node in _iter_nodes(tree):
                nid = node.get("id", "")
                if not nid:
                    problems.append("存在无名节点（树 %s）" % tree["id"])
                if nid in seen:
                    problems.append("节点 id 重复：%s" % nid)
                seen.add(nid)
                if node is tree:
                    continue  # 树根是容器：只要求 rootcauses/title
                for field in ("title", "action", "verdict"):
                    if not node.get(field):
                        problems.append("节点 %s 缺 %s" % (nid, field))
                if not node.get("symptom"):
                    problems.append("节点 %s 缺 symptom" % nid)
                if not node.get("keywords"):
                    problems.append("节点 %s 缺 keywords" % nid)
    else:
        for cat in db["categories"]:
            if not cat.get("pitfalls"):
                problems.append("类别 %s 没有任何坑位" % cat["id"])
            for p in cat["pitfalls"]:
                pid = p.get("id", "")
                if not pid:
                    problems.append("类别 %s 存在无名坑位" % cat["id"])
                if pid in seen:
                    problems.append("坑位 id 重复：%s" % pid)
                seen.add(pid)
                for field in ("title", "symptom", "fix", "keywords"):
                    if not p.get(field):
                        problems.append("坑位 %s 缺 %s" % (pid, field))
                if p.get("fix_alt") is not None and "fix_alt" in p:
                    problems.append("坑位 %s 含遗留字段 fix_alt" % pid)
        if not db.get("rule"):
            problems.append("缺配置口诀 rule")
    return seen


def _tree_md(db):
    lines = [HEADER, "", "# 决策树全量参考（自动生成）", ""]
    for tree in db["trees"]:
        lines.append("## %s — %s" % (tree["id"], tree.get("title", "")))
        lines.append("")
        if tree.get("rootcauses"):
            lines.append("高频根因（按实战经验排序，非实测统计）：")
            lines.append("")
            for i, c in enumerate(tree["rootcauses"], 1):
                lines.append("%d. %s" % (i, c))
            lines.append("")
        for node in tree.get("children", []):
            _render_node(node, 0, lines)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_node(node, depth, lines):
    pad = "  " * depth
    lines.append("%s- **%s** %s" % (pad, node["id"], node.get("title", "")))
    if node.get("symptom"):
        lines.append("%s  - 症状：%s" % (pad, node["symptom"]))
    if node.get("action"):
        lines.append("%s  - 证据动作：%s" % (pad, node["action"]))
    if node.get("verdict"):
        lines.append("%s  - 判定：%s" % (pad, node["verdict"]))
    for fix in node.get("fixes", []):
        lines.append("%s  - 对策：%s" % (pad, fix))
    for child in node.get("children", []):
        _render_node(child, depth + 1, lines)


def _pitfalls_md(db):
    lines = [HEADER, "", "# 外设配置坑全量参考（自动生成）", ""]
    for cat in db["categories"]:
        lines.append("## %s — %s（%d 坑）" % (cat["id"], cat["title"], len(cat["pitfalls"])))
        lines.append("")
        lines.append("| 坑 | 症状 | 对策 |")
        lines.append("|---|---|---|")
        for p in cat["pitfalls"]:
            lines.append("| %s | %s | %s |" % (
                p["title"], p.get("symptom", "-"), p.get("fix", "-")))
        lines.append("")
    lines.append("## 配置口诀")
    lines.append("")
    lines.append(db.get("rule", ""))
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_reference(skill):
    db = _load(skill)
    if skill == "embedded-debug-trees":
        return _tree_md(db)
    return _pitfalls_md(db)


def reference_path(skill):
    return os.path.join(ROOT, "skills", skill, SKILLS[skill]["reference"])


def run_check():
    problems = []
    for skill in SKILLS:
        db = _load(skill)
        lint_db(skill, db, problems)
        want = render_reference(skill)
        with open(reference_path(skill), encoding="utf-8") as fh:
            have = fh.read()
        if have != want:
            problems.append("skills/%s/%s 与 JSON 不同源（跑 tools/knowledge_check.py --doc 重新生成）"
                            % (skill, SKILLS[skill]["reference"]))
    return problems


def run_doc():
    for skill in SKILLS:
        want = render_reference(skill)
        with open(reference_path(skill), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(want)
        print("已生成 skills/%s/%s" % (skill, SKILLS[skill]["reference"]))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="知识库校验与文档生成")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="校验 schema 与同源")
    group.add_argument("--doc", action="store_true", help="重新生成 references")
    args = parser.parse_args()
    if args.doc:
        run_doc()
        return 0
    problems = run_check()
    if problems:
        for p in problems:
            print("问题：" + p)
        print("共 %d 个问题。" % len(problems))
        return 1
    print("知识库校验通过（schema + 同源）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
