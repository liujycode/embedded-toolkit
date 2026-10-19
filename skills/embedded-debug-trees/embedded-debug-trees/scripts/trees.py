#!/usr/bin/env python3
"""排障决策树检索器：按症状关键词检索五棵决策树，或展示整树/根因排行。

用法：
  python trees.py search "DMA 丢数据"
  python trees.py show hardfault
  python trees.py rootcauses hardfault
  python trees.py list
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

__version__ = "1.0.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "assets", "trees.json")


class TreeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_db():
    if not os.path.isfile(DATA):
        raise TreeError("E_DATA_MISSING", "找不到知识库文件 assets/trees.json")
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


def tokenize(query):
    words = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", query.lower())
    syn = {
        "死机": ["hardfault", "crash"],
        "跑飞": ["hardfault", "crash"],
        "崩溃": ["hardfault", "crash"],
        "乱码": ["uart", "baud"],
        "丢帧": ["dma", "uart"],
        "丢数据": ["dma", "只收一次", "丢帧", "数据"],
        "收不到": ["comm", "uart", "i2c", "spi"],
        "不通": ["comm"],
        "超时": ["comm", "timeout"],
        "卡死": ["rtos", "deadlock", "i2c"],
        "死锁": ["rtos", "deadlock"],
        "起不来": ["boot"],
        "不启动": ["boot"],
        "栈溢出": ["rtos", "stack"],
        "总线错误": ["hardfault", "preciserr"],
    }
    out = list(words)
    for w in words:
        out.extend(syn.get(w, []))
    return sorted(set(out))


def node_matches(node, terms):
    """宽松匹配：任一检索词命中即算命中（search 里按命中数排序）。
    中文词做子串匹配，ASCII 词做词内子串匹配（dma→dma/DMAR）。"""
    text = " ".join([
        node.get("id", ""), node.get("title", ""),
        node.get("symptom", ""), node.get("action", ""),
        node.get("verdict", ""), " ".join(node.get("fixes", [])),
        " ".join(node.get("keywords", [])),
    ]).lower()
    for t in terms:
        if re.search(r"[\u4e00-\u9fff]", t):
            if t in text:
                return True
        else:
            if re.search(r"[a-z0-9_]*%s[a-z0-9_]*" % re.escape(t), text):
                return True
    return False


def hit_count(node, terms):
    text = " ".join([
        node.get("id", ""), node.get("title", ""),
        node.get("symptom", ""), node.get("action", ""),
        node.get("verdict", ""), " ".join(node.get("fixes", [])),
        " ".join(node.get("keywords", [])),
    ]).lower()
    n = 0
    for t in terms:
        if re.search(r"[\u4e00-\u9fff]", t):
            if t in text:
                n += 1
        elif re.search(r"[a-z0-9_]*%s[a-z0-9_]*" % re.escape(t), text):
            n += 1
    return n


def walk(node, terms, path, hits):
    if node_matches(node, terms):
        hits.append((path, node))
    for child in node.get("children", []):
        walk(child, terms, path + [node.get("id", "?")], hits)


def cmd_search(args):
    db = load_db()
    terms = tokenize(args.query)
    if not terms:
        raise TreeError("E_EMPTY_QUERY", "检索词为空")
    hits = []
    for tree in db["trees"]:
        walk(tree, terms, [], hits)
    if not hits:
        print("E_NOT_FOUND：决策树库中没有命中 '%s' 的节点。" % args.query)
        print("可用决策树：%s" % ", ".join(t["id"] for t in db["trees"]))
        print("建议：换更具体的现象词（如 'SDA 卡死' '只收一次' '栈溢出'），或用 show <树名> 通读全树。")
        return 1
    hits.sort(key=lambda hn: -hit_count(hn[1], terms))
    print("命中 %d 个节点（检索词：%s，按相关度排序）\n" % (len(hits), " + ".join(terms)))
    for path, node in hits[:8]:
        tree_id = path[0] if path else node.get("id", "?")
        chain = " → ".join(path + [node["id"]])
        print("## %s" % chain)
        if node.get("symptom"):
            print("  症状：%s" % node["symptom"])
        if node.get("action"):
            print("  证据动作：%s" % node["action"])
        if node.get("verdict"):
            print("  判定：%s" % node["verdict"])
        for fix in node.get("fixes", []):
            print("  对策：%s" % fix)
        print()
    return 0


def _render(node, depth, lines):
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
        _render(child, depth + 1, lines)


def cmd_show(args):
    db = load_db()
    tree = next((t for t in db["trees"] if t["id"] == args.tree), None)
    if tree is None:
        raise TreeError("E_NO_TREE", "没有名为 '%s' 的决策树（可用：%s）"
                        % (args.tree, ", ".join(t["id"] for t in db["trees"])))
    lines = ["# 决策树：%s（%s）" % (tree["id"], tree.get("title", "")), ""]
    for child in tree.get("children", []):
        _render(child, 0, lines)
    print("\n".join(lines))
    return 0


def cmd_rootcauses(args):
    db = load_db()
    tree = next((t for t in db["trees"] if t["id"] == args.tree), None)
    if tree is None:
        raise TreeError("E_NO_TREE", "没有名为 '%s' 的决策树" % args.tree)
    causes = tree.get("rootcauses", [])
    if not causes:
        print("该决策树暂无根因排行数据。")
        return 0
    print("# %s 高频根因排行\n" % args.tree)
    for i, c in enumerate(causes, 1):
        print("%d. %s" % (i, c))
    return 0


def cmd_list(args):
    db = load_db()
    print("共 %d 棵决策树：\n" % len(db["trees"]))
    for t in db["trees"]:
        print("- %-10s %s（节点 %d）" % (t["id"], t.get("title", ""),
              sum(1 for _ in _iter_nodes(t))))
    return 0


def _iter_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from _iter_nodes(child)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="trees.py", description="嵌入式排障决策树检索器")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("search", help="按症状关键词检索")
    p.add_argument("query")
    p = sub.add_parser("show", help="展示整棵决策树")
    p.add_argument("tree")
    p = sub.add_parser("rootcauses", help="高频根因排行")
    p.add_argument("tree")
    sub.add_parser("list", help="列出全部决策树")
    sub.add_parser("demo", help="自检：加载知识库并试检索")
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    try:
        if args.cmd == "demo":
            db = load_db()
            n = sum(1 for t in db["trees"] for _ in _iter_nodes(t))
            print("自检通过：知识库 %d 棵树 / %d 节点。" % (len(db["trees"]), n))
            return 0
        if args.cmd == "search":
            return cmd_search(args)
        if args.cmd == "show":
            return cmd_show(args)
        if args.cmd == "rootcauses":
            return cmd_rootcauses(args)
        return cmd_list(args)
    except TreeError as exc:
        print("%s：%s" % (exc.code, exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
