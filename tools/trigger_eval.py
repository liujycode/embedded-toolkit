#!/usr/bin/env python3
"""触发评测结果判定工具（离线解析，不发起任何模型调用）。

用途：把无头 Agent 的输出目录判定为逐例「已触发 / 未触发」，输出逐例表格与汇总。
支持两种流格式：
  --agent claude    Claude Code `--output-format stream-json --verbose` 的 JSONL
  --agent opencode  OpenCode `run --format json` 的 JSONL

为什么不能用纯文本匹配：技能名会出现在系统提示的技能清单里（Claude Code 的
init/slash_commands、OpenCode 的技能列表），"技能名出现即触发"的判定会把全部
用例误判为触发。本工具只认结构化信号：
  claude：  "Launching skill: <skill>" / "commandName": "<skill>"；带技能安装路径的脚本调用
  opencode：tool="skill" 且 name=<skill>；tool="bash" 且命令含脚本调用

解析容错：utf-8-sig 去 BOM；json.loads(strict=False) 容忍字符串内的终端转义字符；
解析失败的行按"工具类型 + 名称/脚本"配对特征兜底。

文件名约定：p 开头为正例、n 开头为反例（与 tests/trigger/ 的用例一致）。
用法示例：
  python tools/trigger_eval.py --dir <输出目录> --agent claude
  python tools/trigger_eval.py --dir <输出目录> --agent opencode --threshold 0.9
准确率低于 --threshold（默认 0.9）时退出码为 1，便于脚本化。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

DEFAULT_SKILL = "embedded-register-lookup"
DEFAULT_SCRIPT = "lookup.py"
SUBCOMMANDS = ("lookup", "addr", "search", "decode", "list")


def load_events(path):
    events = []
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line, strict=False))
            except json.JSONDecodeError:
                events.append({"_raw": line})
    return events


def looks_like_run(text, script):
    """命令行文本里脚本名后紧跟子命令，才算"真实执行"，避免目录列表里的裸文件名误报。"""
    pattern = re.escape(script) + r".{0,4}(" + "|".join(SUBCOMMANDS) + r")\b"
    return bool(re.search(pattern, text))


def looks_like_installed_run(text, skill, script):
    """文本中带安装目录限定的执行证据：skills/<skill>/[scripts/]<script> <子命令>。

    Claude Code 的流里会混入技能文档内容（含示例命令 python scripts/lookup.py ...），
    只认带技能安装路径的调用，避免把文档示例误当成真实执行。
    """
    pattern = (r"skills[\\/]+" + re.escape(skill) + r"[\\/]+(?:scripts[\\/]+)?" + re.escape(script)
               + r".{0,4}(" + "|".join(SUBCOMMANDS) + r")\b")
    return bool(re.search(pattern, text, re.IGNORECASE))


def detect_claude(path, skill, script):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read()
    launch = bool(re.search(r"Launching skill:\s*" + re.escape(skill), text))
    command = bool(re.search(r'"commandName"\s*:\s*"' + re.escape(skill) + r'"', text))
    ran = looks_like_installed_run(text, skill, script)
    return {"launch": launch, "command": command, "script": ran}, (launch or command or ran)


def detect_opencode(path, skill, script):
    loads = 0
    runs = 0
    for ev in load_events(path):
        if "_raw" in ev:
            raw = ev["_raw"]
            if '"tool":"skill"' in raw and skill in raw:
                loads += 1
            if '"tool":"bash"' in raw and looks_like_run(raw, script):
                runs += 1
            continue
        if ev.get("type") != "tool_use":
            continue
        part = ev.get("part") or {}
        tool = part.get("tool")
        inp = (part.get("state") or {}).get("input") or {}
        if tool == "skill":
            if skill in str(inp.get("name") or ""):
                loads += 1
        elif tool == "bash":
            if looks_like_run(str(inp.get("command") or ""), script):
                runs += 1
    return {"skill_loads": loads, "script_runs": runs}, (loads > 0 or runs > 0)


def evaluate(directory, agent, skill=DEFAULT_SKILL, script=DEFAULT_SCRIPT):
    detector = detect_claude if agent == "claude" else detect_opencode
    rows = []
    for path in sorted(glob.glob(os.path.join(directory, "*.jsonl"))):
        case_id = os.path.basename(path).split(".")[0]
        if not (case_id.startswith("p") or case_id.startswith("n")):
            continue
        signals, triggered = detector(path, skill, script)
        expect = "positive" if case_id.startswith("p") else "negative"
        rows.append({
            "id": case_id,
            "expect": expect,
            "triggered": triggered,
            "ok": triggered == (expect == "positive"),
            "signals": signals,
        })
    return rows


def summarize(rows):
    total = len(rows)
    correct = sum(1 for r in rows if r["ok"])
    pos = [r for r in rows if r["expect"] == "positive"]
    neg = [r for r in rows if r["expect"] == "negative"]
    return {
        "total": total,
        "correct": correct,
        "accuracy": (float(correct) / total) if total else 0.0,
        "pos_ok": sum(1 for r in pos if r["ok"]),
        "pos_total": len(pos),
        "neg_ok": sum(1 for r in neg if r["ok"]),
        "neg_total": len(neg),
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="触发评测结果判定（离线）")
    parser.add_argument("--dir", required=True, help="无头 Agent 输出目录（含逐例 .jsonl）")
    parser.add_argument("--agent", required=True, choices=("claude", "opencode"))
    parser.add_argument("--skill", default=DEFAULT_SKILL, help="技能名（默认 %s）" % DEFAULT_SKILL)
    parser.add_argument("--script", default=DEFAULT_SCRIPT, help="技能内脚本文件名（默认 %s）" % DEFAULT_SCRIPT)
    parser.add_argument("--threshold", type=float, default=0.9, help="低于该准确率时退出码 1（默认 0.9）")
    args = parser.parse_args(argv)

    rows = evaluate(args.dir, args.agent, args.skill, args.script)
    if not rows:
        print("目录中没有找到 p*/n* 命名的 .jsonl 输出：%s" % args.dir)
        return 2
    print("%-5s %-9s %-6s %-5s %s" % ("case", "expect", "trig", "ok", "signals"))
    for r in rows:
        print("%-5s %-9s %-6s %-5s %s" % (
            r["id"], r["expect"], r["triggered"], "OK" if r["ok"] else "X", r["signals"]))
    s = summarize(rows)
    print("-" * 64)
    print("正例 %d/%d  反例 %d/%d  总准确率 %d/%d = %.0f%%" % (
        s["pos_ok"], s["pos_total"], s["neg_ok"], s["neg_total"],
        s["correct"], s["total"], 100.0 * s["accuracy"]))
    return 0 if s["accuracy"] >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
