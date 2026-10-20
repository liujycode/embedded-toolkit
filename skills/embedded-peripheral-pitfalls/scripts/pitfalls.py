#!/usr/bin/env python3
"""外设配置坑清单检索器：按外设/症状关键词检索坑位，或展示某外设全部坑表。

用法：
  python pitfalls.py search "I2C 上拉" [--category i2c] [--format json]
  python pitfalls.py show adc [--format json]
  python pitfalls.py list [--format json]
  python pitfalls.py rule [--format json]
  python pitfalls.py demo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

__version__ = "1.2.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "assets", "pitfalls.json")

SYNONYMS = {
    "不通": ["配置", "无响应"],
    "没反应": ["无响应"],
    "收不到": ["收不到", "无响应"],
    "错位": ["错位", "字节序"],
    "精度差": ["精度", "抖动"],
    "跑飞": ["hardfault"],
    "hardfault": ["hardfault"],
    "复用": ["af", "复用"],
    "推挽": ["开漏", "推挽"],
    "低功耗": ["pwr", "低功耗", "唤醒"],
    "看门狗": ["iwdg", "wwdg", "wdg"],
    "复位循环": ["iwdg", "复位"],
}


class PitfallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_db():
    if not os.path.isfile(DATA):
        raise PitfallError("E_DATA_MISSING", "找不到知识库文件 assets/pitfalls.json")
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


def tokenize(query):
    words = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", query.lower())
    out = list(words)
    for w in words:
        out.extend(SYNONYMS.get(w, []))
    return sorted(set(out))


def _bigrams(s):
    out = set()
    for seg in re.findall(r"[\u4e00-\u9fff]+", s):
        n = len(seg)
        for i in range(n - 1):
            out.add(seg[i:i + 2])
    return out


def bigram_boost(text, raw, weight=0.5):
    """中文 bigram 兜底排序加成：≤weight（整句查询无关键词命中时的排序兜底）。"""
    if len(raw) < 4:
        return 0.0
    rb = _bigrams(raw)
    if not rb:
        return 0.0
    tb = _bigrams(text)
    if not tb:
        return 0.0
    return min(weight, weight * len(rb & tb) / len(rb))


def node_text(pitfall, cat):
    return " ".join([
        cat.get("id", ""), cat.get("title", ""),
        pitfall.get("id", ""), pitfall.get("title", ""),
        pitfall.get("symptom", ""), pitfall.get("fix", ""),
        " ".join(pitfall.get("keywords", [])),
    ]).lower()


def match_count(text, terms, node=None, raw=""):
    """宽松匹配计分：中文词子串命中、ASCII 词词内子串命中。

    中文整句不做分词——补一层反向匹配：节点关键词（≥2 字中文）出现在原始查询串里
    按命中关键词个数计分（"调试时老是复位" 命中 "调试"+"复位" 计 2 分，排序更准）。
    """
    n = 0
    for t in terms:
        if re.search(r"[\u4e00-\u9fff]", t):
            if t in text:
                n += 1
            elif node and raw:
                n += sum(1 for kw in node.get("keywords", [])
                         if len(kw) >= 2 and re.search(r"[\u4e00-\u9fff]", kw) and kw in raw)
        elif re.search(r"[a-z0-9_]*%s[a-z0-9_]*" % re.escape(t), text):
            n += 1
    if n and raw:
        n += bigram_boost(text, raw)
    return n


def search(db, terms, category=None, raw=""):
    hits = []
    for cat in db["categories"]:
        if category and cat["id"] != category:
            continue
        for p in cat.get("pitfalls", []):
            n = match_count(node_text(p, cat), terms, p, raw)
            if n:
                hits.append((n, cat, p))
    hits.sort(key=lambda h: -h[0])
    return hits


def cmd_search(args, out):
    db = load_db()
    terms = tokenize(args.query)
    if not terms:
        raise PitfallError("E_EMPTY_QUERY", "检索词为空")
    hits = search(db, terms, args.category, args.query.lower())
    if not hits:
        if args.format == "json":
            print(json.dumps({
                "tool": "embedded-peripheral-pitfalls", "version": __version__,
                "kind": "search", "query": args.query, "terms": terms,
                "hits": [], "total": 0,
                "categories": [c["id"] for c in db["categories"]],
            }, ensure_ascii=False, indent=2))
        else:
            print("E_NOT_FOUND：坑清单中没有命中 '%s' 的条目。" % args.query)
            print("可用外设类别：%s" % ", ".join(c["id"] for c in db["categories"]))
            print("建议：换外设名或具体症状词（如 '上拉' '采样时间' 'CPOL'），或用 show <类别> 通读。")
        return 1
    if args.format == "json":
        items = []
        for n, cat, p in hits[:8]:
            items.append({
                "category": cat["id"], "category_title": cat["title"],
                "id": p["id"], "title": p["title"],
                "symptom": p.get("symptom", ""), "fix": p.get("fix", ""),
                "score": n,
            })
        print(json.dumps({
            "tool": "embedded-peripheral-pitfalls", "version": __version__,
            "kind": "search", "query": args.query, "terms": terms,
            "total": len(hits), "hits": items,
        }, ensure_ascii=False, indent=2))
        return 0
    print("命中 %d 个坑位（检索词：%s，按相关度排序）\n" % (len(hits), " + ".join(terms)))
    for _, cat, p in hits[:8]:
        print("## [%s] %s" % (cat["title"], p["title"]))
        print("  症状：%s" % p.get("symptom", "-"))
        print("  对策：%s" % p.get("fix", "-"))
        if p.get("refs"):
            print("  依据：%s" % "；".join(p["refs"]))
        if p.get("next"):
            print("  下一步：%s" % p["next"])
        print()
    if len(hits) > 8:
        print("（只显示前 8 条，共 %d 条——加限定词或用 show <类别> 收窄）" % len(hits))
    return 0


def cmd_show(args, out):
    db = load_db()
    cat = next((c for c in db["categories"] if c["id"] == args.category), None)
    if cat is None:
        raise PitfallError("E_NO_CATEGORY", "没有 '%s' 类别（可用：%s）"
                           % (args.category, ", ".join(c["id"] for c in db["categories"])))
    if args.format == "json":
        print(json.dumps({
            "tool": "embedded-peripheral-pitfalls", "version": __version__,
            "kind": "category", "category": cat,
        }, ensure_ascii=False, indent=2))
        return 0
    print("# %s 配置坑清单\n" % cat["title"])
    print("| 坑 | 症状 | 对策 |")
    print("|---|---|---|")
    for p in cat.get("pitfalls", []):
        print("| %s | %s | %s |" % (p["title"], p.get("symptom", "-"), p.get("fix", "-")))
    for p in cat.get("pitfalls", []):
        if p.get("refs"):
            print("- [%s] %s 依据：%s" % (p["id"], p["title"], "；".join(p["refs"])))
        if p.get("next"):
            print("- [%s] %s 下一步：%s" % (p["id"], p["title"], p["next"]))
    return 0


def cmd_list(args, out):
    db = load_db()
    rows = [{"id": c["id"], "title": c["title"], "pitfalls": len(c.get("pitfalls", []))}
            for c in db["categories"]]
    total = sum(r["pitfalls"] for r in rows)
    if args.format == "json":
        print(json.dumps({
            "tool": "embedded-peripheral-pitfalls", "version": __version__,
            "kind": "list", "total_categories": len(rows), "total_pitfalls": total,
            "categories": rows,
        }, ensure_ascii=False, indent=2))
        return 0
    print("共 %d 类外设 / %d 个坑位：\n" % (len(rows), total))
    for r in rows:
        print("- %-6s %s（%d 坑）" % (r["id"], r["title"], r["pitfalls"]))
    return 0


def cmd_rule(args, out):
    db = load_db()
    rule = db.get("rule", "（无口诀数据）")
    if args.format == "json":
        print(json.dumps({
            "tool": "embedded-peripheral-pitfalls", "version": __version__,
            "kind": "rule", "rule": rule,
        }, ensure_ascii=False, indent=2))
        return 0
    print(rule)
    return 0


def cmd_demo(args, out):
    db = load_db()
    total = sum(len(c.get("pitfalls", [])) for c in db["categories"])
    # 检索自检：典型场景必须命中对应类别
    probes = [
        ("I2C 上拉电阻", "i2c"),
        ("SPI 时钟极性", "spi"),
        ("ADC 采样时间", "adc"),
        ("定时器周期不对", "tim"),
        ("时钟没开 hardfault", "rcc"),
        ("看门狗调试复位", "wdg"),
        ("停机模式唤醒乱码", "pwr"),
        ("CAN 收不到报文", "can"),
        ("DMA 收不到数据", "dma"),
        ("USB 枚举失败", "usb"),
        ("Flash 写不进去", "flash"),
        ("RTC 每次上电重置时间", "rtc"),
        ("CRC 算出来对不上", "crc"),
        ("MPU 配置没生效", "mpu"),
        ("调试器断开程序卡死", "dbg"),
        ("链接脚本段溢出", "link"),
        ("ETH 网口 ping 不通", "eth"),
        ("SD 卡挂载失败", "sd"),
        ("volatile 变量被优化", "c"),
        ("Modbus 收不到完整帧", "modbus"),
        ("DS18B20 温度读不出来", "sensor-bus"),
        ("DAC 输出波形不对", "dac"),
    ]
    failed = []
    for query, expect in probes:
        terms = tokenize(query)
        hits = search(db, terms, raw=query.lower())
        if not any(h[1]["id"] == expect for h in hits):
            failed.append("%s → %s" % (query, expect))
    if failed:
        print("自检失败：检索未命中预期类别：%s" % "；".join(failed))
        return 2
    print("自检通过：%d 类外设 / %d 个坑位；%d 条检索探针全部命中。" % (
        len(db["categories"]), total, len(probes)))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="pitfalls.py", description="嵌入式外设配置坑清单检索器")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    p = sub.add_parser("search", help="按外设/症状关键词检索")
    p.add_argument("query")
    p.add_argument("--category", default=None, help="限定在某类别内检索")
    common(p)
    p = sub.add_parser("show", help="展示某外设全部坑位")
    p.add_argument("category")
    common(p)
    p = sub.add_parser("list", help="列出全部外设类别")
    common(p)
    p = sub.add_parser("rule", help="输出通用配置口诀")
    common(p)
    p = sub.add_parser("demo", help="自检：知识库加载 + 典型场景检索探针")
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
        if args.cmd == "list":
            return cmd_list(args, out)
        return cmd_rule(args, out)
    except PitfallError as exc:
        if getattr(args, "format", "text") == "json":
            print(json.dumps({"tool": "embedded-peripheral-pitfalls", "version": __version__,
                              "error": {"code": exc.code, "message": str(exc)}},
                             ensure_ascii=False))
        else:
            print("%s：%s" % (exc.code, exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
