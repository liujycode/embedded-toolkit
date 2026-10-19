#!/usr/bin/env python3
"""外设配置坑清单检索器：按外设/症状关键词检索坑位，或展示某外设全部坑表。

用法：
  python pitfalls.py search "I2C 上拉"
  python pitfalls.py show adc
  python pitfalls.py list
  python pitfalls.py rule
  python pitfalls.py demo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

__version__ = "1.0.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "assets", "pitfalls.json")


class PitfallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_db():
    if not os.path.isfile(DATA):
        raise PitfallError("E_DATA_MISSING", "找不到知识库文件 assets/pitfalls.json")
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


SYN = {
    "不通": ["配置", "无响应"],
    "没反应": ["无响应"],
    "收不到": ["收不到", "无响应"],
    "错位": ["错位", "字节序"],
    "精度差": ["精度", "抖动"],
    "跑飞": ["hardfault"],
    "hardfault": ["hardfault"],
    "复用": ["af", "复用"],
    "推挽": ["开漏", "推挽"],
}


def tokenize(query):
    words = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", query.lower())
    out = list(words)
    for w in words:
        out.extend(SYN.get(w, []))
    return sorted(set(out))


def node_text(pitfall, cat):
    return " ".join([
        cat.get("id", ""), cat.get("title", ""),
        pitfall.get("id", ""), pitfall.get("title", ""),
        pitfall.get("symptom", ""), pitfall.get("fix", ""),
        " ".join(pitfall.get("keywords", [])),
    ]).lower()


def match_count(text, terms):
    n = 0
    for t in terms:
        if re.search(r"[\u4e00-\u9fff]", t):
            if t in text:
                n += 1
        elif re.search(r"[a-z0-9_]*%s[a-z0-9_]*" % re.escape(t), text):
            n += 1
    return n


def cmd_search(args):
    db = load_db()
    terms = tokenize(args.query)
    if not terms:
        raise PitfallError("E_EMPTY_QUERY", "检索词为空")
    hits = []
    for cat in db["categories"]:
        for p in cat.get("pitfalls", []):
            n = match_count(node_text(p, cat), terms)
            if n:
                hits.append((n, cat, p))
    if not hits:
        print("E_NOT_FOUND：坑清单中没有命中 '%s' 的条目。" % args.query)
        print("可用外设类别：%s" % ", ".join(c["id"] for c in db["categories"]))
        print("建议：换外设名或具体症状词（如 '上拉' '采样时间' 'CPOL'），或用 show <类别> 通读。")
        return 1
    hits.sort(key=lambda h: -h[0])
    print("命中 %d 个坑位（检索词：%s，按相关度排序）\n" % (len(hits), " + ".join(terms)))
    for _, cat, p in hits[:8]:
        print("## [%s] %s" % (cat["title"], p["title"]))
        print("  症状：%s" % p.get("symptom", "-"))
        print("  对策：%s" % p.get("fix", "-"))
        print()
    return 0


def cmd_show(args):
    db = load_db()
    cat = next((c for c in db["categories"] if c["id"] == args.category), None)
    if cat is None:
        raise PitfallError("E_NO_CATEGORY", "没有 '%s' 类别（可用：%s）"
                           % (args.category, ", ".join(c["id"] for c in db["categories"])))
    print("# %s 配置坑清单\n" % cat["title"])
    print("| 坑 | 症状 | 对策 |")
    print("|---|---|---|")
    for p in cat.get("pitfalls", []):
        print("| %s | %s | %s |" % (p["title"], p.get("symptom", "-"), p.get("fix", "-")))
    return 0


def cmd_list(args):
    db = load_db()
    total = sum(len(c.get("pitfalls", [])) for c in db["categories"])
    print("共 %d 类外设 / %d 个坑位：\n" % (len(db["categories"]), total))
    for c in db["categories"]:
        print("- %-6s %s（%d 坑）" % (c["id"], c["title"], len(c.get("pitfalls", []))))
    return 0


def cmd_rule(args):
    db = load_db()
    print(db.get("rule", "（无口诀数据）"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pitfalls.py", description="嵌入式外设配置坑清单检索器")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("search", help="按外设/症状关键词检索")
    p.add_argument("query")
    p = sub.add_parser("show", help="展示某外设全部坑位")
    p.add_argument("category")
    sub.add_parser("list", help="列出全部外设类别")
    sub.add_parser("rule", help="输出通用配置口诀")
    sub.add_parser("demo", help="自检")
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    try:
        if args.cmd == "demo":
            db = load_db()
            total = sum(len(c.get("pitfalls", [])) for c in db["categories"])
            print("自检通过：%d 类外设 / %d 个坑位。" % (len(db["categories"]), total))
            return 0
        if args.cmd == "search":
            return cmd_search(args)
        if args.cmd == "show":
            return cmd_show(args)
        if args.cmd == "list":
            return cmd_list(args)
        return cmd_rule(args)
    except PitfallError as exc:
        print("%s：%s" % (exc.code, exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
