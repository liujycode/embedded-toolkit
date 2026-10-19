#!/usr/bin/env python3
"""排障决策树检索器：按症状关键词检索决策树，或展示整树/根因排行。

用法：
  python trees.py search "DMA 丢数据" [--tree dma] [--format json]
  python trees.py show hardfault [--format json]
  python trees.py rootcauses hardfault
  python trees.py list [--format json]
  python trees.py demo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

__version__ = "1.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "assets", "trees.json")

SYNONYMS = {
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
    "低功耗": ["pwr", "stop", "standby"],
    "唤醒": ["pwr", "wakeup"],
    "电流大": ["pwr", "stop"],
}


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
    out = list(words)
    for w in words:
        out.extend(SYNONYMS.get(w, []))
    return sorted(set(out))


def node_text(node):
    return " ".join([
        node.get("id", ""), node.get("title", ""),
        node.get("symptom", ""), node.get("action", ""),
        node.get("verdict", ""), " ".join(node.get("fixes", [])),
        " ".join(node.get("keywords", [])),
    ]).lower()


def hit_count(node, terms, raw=""):
    """宽松匹配计分：中文词子串命中、ASCII 词词内子串命中。

    中文整句查询不做分词——补一层反向匹配：节点关键词（≥2 字中文）出现在原始查询
    串里按命中关键词个数计分（"调试时老是复位" 命中 "调试"+"复位" 计 2 分，排序更准）。
    """
    text = node_text(node)
    n = 0
    for t in terms:
        if re.search(r"[\u4e00-\u9fff]", t):
            if t in text:
                n += 1
            elif raw:
                n += sum(1 for kw in node.get("keywords", [])
                         if len(kw) >= 2 and re.search(r"[\u4e00-\u9fff]", kw) and kw in raw)
        elif re.search(r"[a-z0-9_]*%s[a-z0-9_]*" % re.escape(t), text):
            n += 1
    return n


def walk(node, terms, path, hits, raw=""):
    n = hit_count(node, terms, raw)
    if n:
        hits.append((n, path, node))
    for child in node.get("children", []):
        walk(child, terms, path + [node.get("id", "?")], hits, raw)


def cmd_search(args, out):
    db = load_db()
    terms = tokenize(args.query)
    if not terms:
        raise TreeError("E_EMPTY_QUERY", "检索词为空")
    hits = []
    for tree in db["trees"]:
        if args.tree and tree["id"] != args.tree:
            continue
        walk(tree, terms, [], hits, args.query.lower())
    if not hits:
        if args.format == "json":
            print(json.dumps({
                "tool": "embedded-debug-trees", "version": __version__,
                "kind": "search", "query": args.query, "terms": terms,
                "hits": [], "total": 0,
                "trees": [t["id"] for t in db["trees"]],
            }, ensure_ascii=False, indent=2))
        else:
            print("E_NOT_FOUND：决策树库中没有命中 '%s' 的节点。" % args.query)
            print("可用决策树：%s" % ", ".join(t["id"] for t in db["trees"]))
            print("建议：换更具体的现象词（如 'SDA 卡死' '只收一次' '栈溢出'），或用 show <树名> 通读全树。")
        return 1
    hits.sort(key=lambda h: -h[0])
    total = len(hits)
    if args.format == "json":
        items = []
        for n, path, node in hits[:8]:
            items.append({
                "tree": path[0] if path else node.get("id", "?"),
                "path": path + [node["id"]],
                "score": n,
                "symptom": node.get("symptom", ""),
                "action": node.get("action", ""),
                "verdict": node.get("verdict", ""),
                "fixes": node.get("fixes", []),
            })
        print(json.dumps({
            "tool": "embedded-debug-trees", "version": __version__,
            "kind": "search", "query": args.query, "terms": terms,
            "total": total, "hits": items,
        }, ensure_ascii=False, indent=2))
        return 0
    print("命中 %d 个节点（检索词：%s，按相关度排序）\n" % (total, " + ".join(terms)))
    for n, path, node in hits[:8]:
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
    if total > 8:
        print("（只显示前 8 条，共 %d 条——加限定词或用 show <树名> 收窄）" % total)
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


def cmd_show(args, out):
    db = load_db()
    tree = next((t for t in db["trees"] if t["id"] == args.tree), None)
    if tree is None:
        raise TreeError("E_NO_TREE", "没有名为 '%s' 的决策树（可用：%s）"
                        % (args.tree, ", ".join(t["id"] for t in db["trees"])))
    if args.format == "json":
        print(json.dumps({
            "tool": "embedded-debug-trees", "version": __version__,
            "kind": "tree", "tree": tree,
            "rootcauses_note": "按实战经验排序（非实测统计）",
        }, ensure_ascii=False, indent=2))
        return 0
    lines = ["# 决策树：%s（%s）" % (tree["id"], tree.get("title", "")), ""]
    if tree.get("rootcauses"):
        lines.append("高频根因（按实战经验排序）：")
        for i, c in enumerate(tree["rootcauses"], 1):
            lines.append("%d. %s" % (i, c))
        lines.append("")
    for child in tree.get("children", []):
        _render(child, 0, lines)
    print("\n".join(lines))
    return 0


def cmd_rootcauses(args, out):
    db = load_db()
    tree = next((t for t in db["trees"] if t["id"] == args.tree), None)
    if tree is None:
        raise TreeError("E_NO_TREE", "没有名为 '%s' 的决策树" % args.tree)
    causes = tree.get("rootcauses", [])
    if args.format == "json":
        print(json.dumps({
            "tool": "embedded-debug-trees", "version": __version__,
            "kind": "rootcauses", "tree": args.tree,
            "note": "按实战经验排序（非实测统计）", "causes": causes,
        }, ensure_ascii=False, indent=2))
        return 0
    if not causes:
        print("该决策树暂无根因排行数据。")
        return 0
    print("# %s 高频根因排行（按实战经验排序，非实测统计）\n" % args.tree)
    for i, c in enumerate(causes, 1):
        print("%d. %s" % (i, c))
    return 0


def _iter_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from _iter_nodes(child)


def cmd_list(args, out):
    db = load_db()
    rows = [{"id": t["id"], "title": t.get("title", ""),
             "nodes": sum(1 for _ in _iter_nodes(t))} for t in db["trees"]]
    if args.format == "json":
        print(json.dumps({
            "tool": "embedded-debug-trees", "version": __version__,
            "kind": "list", "total": len(rows), "trees": rows,
        }, ensure_ascii=False, indent=2))
        return 0
    print("共 %d 棵决策树：\n" % len(rows))
    for r in rows:
        print("- %-10s %s（节点 %d）" % (r["id"], r["title"], r["nodes"]))
    return 0


def cmd_demo(args, out):
    db = load_db()
    n = sum(1 for t in db["trees"] for _ in _iter_nodes(t))
    # 检索自检：典型症状必须命中对应树
    probes = [
        ("DMA 丢数据", "dma"),
        ("HardFault 死机", "hardfault"),
        ("I2C 不通", "comm"),
        ("任务卡死", "rtos"),
        ("上电起不来", "boot"),
        ("唤醒后乱码", "pwr"),
    ]
    failed = []
    for query, expect in probes:
        terms = tokenize(query)
        hits = []
        for tree in db["trees"]:
            walk(tree, terms, [], hits, query.lower())
        if not any((h[1][0] if h[1] else h[2].get("id")) == expect for h in hits):
            failed.append("%s → %s" % (query, expect))
    if failed:
        print("自检失败：检索未命中预期树：%s" % "；".join(failed))
        return 2
    print("自检通过：知识库 %d 棵树 / %d 节点；%d 条检索探针全部命中。" % (
        len(db["trees"]), n, len(probes)))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="trees.py", description="嵌入式排障决策树检索器")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    p = sub.add_parser("search", help="按症状关键词检索")
    p.add_argument("query")
    p.add_argument("--tree", default=None, help="限定在某棵树内检索")
    common(p)
    p = sub.add_parser("show", help="展示整棵决策树")
    p.add_argument("tree")
    common(p)
    p = sub.add_parser("rootcauses", help="高频根因排行（按实战经验排序）")
    p.add_argument("tree")
    common(p)
    p = sub.add_parser("list", help="列出全部决策树")
    common(p)
    p = sub.add_parser("demo", help="自检：知识库加载 + 典型症状检索探针")
    common(p)
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    out = sys.stdout
    try:
        if args.cmd == "demo":
            return cmd_demo(args, out)
        if args.cmd == "search":
            return cmd_search(args, out)
        if args.cmd == "show":
            return cmd_show(args, out)
        if args.cmd == "rootcauses":
            return cmd_rootcauses(args, out)
        return cmd_list(args, out)
    except TreeError as exc:
        if getattr(args, "format", "text") == "json":
            print(json.dumps({"tool": "embedded-debug-trees", "version": __version__,
                              "error": {"code": exc.code, "message": str(exc)}},
                             ensure_ascii=False))
        else:
            print("%s：%s" % (exc.code, exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
