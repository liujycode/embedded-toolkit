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
import re
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


def _lint_refs(node, problems, version):
    """refs 若存在，必须是**非空**字符串数组（防占位）。仅 schema 1.1 允许出现。"""
    if "refs" not in node:
        return
    if version < 2:
        problems.append("%s 含 refs，但 schema 为 1.0（refs 仅 schema 1.1 允许）" % node.get("id", "?"))
        return
    refs = node.get("refs")
    if not isinstance(refs, list) or not refs:
        problems.append("%s 的 refs 存在但为空（应为非空字符串数组）" % node.get("id", "?"))
        return
    for i, r in enumerate(refs):
        if not isinstance(r, str) or not r.strip():
            problems.append("%s 的 refs 第 %d 项非法（必须是非空字符串）" % (node.get("id", "?"), i + 1))


# next 必须是可直接执行的命令：`<skill-id> <subcommand> [--flag <占位符>]`。
# 子命令/参数白名单与五个技能 CLI 的 argparse 定义保持同步（新增子命令时同步此表）。
NEXT_SKILLS = {
    "embedded-register-lookup": {
        "subcommands": frozenset((
            "lookup", "addr", "search", "irq", "decode", "fields", "diagram", "set",
            "macros", "diff", "range", "lint", "info", "list", "devices", "doctor",
        )),
        "flags": frozenset((
            "--project-dir", "--format", "--out", "--svd", "--svd-a", "--svd-b",
            "--chip", "--chip-a", "--chip-b", "--demo", "--limit", "--from", "--all",
            "--filter", "--kind", "--peripheral", "--write",
        )),
    },
    "embedded-register-verify": {
        "subcommands": frozenset(("check", "rules")),
        "flags": frozenset((
            "--project-dir", "--format", "--out", "--svd", "--chip", "--demo",
            "--define", "--headers", "--patch", "--no-clock-check", "--checklist",
            "--explain", "--limit",
        )),
    },
    "embedded-debug-trees": {
        "subcommands": frozenset(("search", "show", "rootcauses", "list", "demo")),
        "flags": frozenset(("--format", "--tree")),
    },
    "embedded-peripheral-pitfalls": {
        "subcommands": frozenset(("search", "show", "list", "rule", "demo")),
        "flags": frozenset(("--format", "--category")),
    },
    "embedded-timing-calc": {
        "subcommands": frozenset((
            "uart", "timer", "i2c-rp", "i2c-time", "can-bit", "adc-rad", "rc", "spi",
            "nyquist", "deadtime", "fpga-uart", "fpga-slack", "fpga-pwm", "wdg", "pll",
            "divider", "ntc", "rc-settle", "ppm", "esp32-clk", "rp2040-uart",
            "pwm-dim", "ws2812", "servo", "stepper", "serial-baud", "rtc-drift",
            "usb-clk", "battery", "modbus-silence", "flash-wear", "spi-time",
            "sensor-lsb", "fpga-i2c", "fpga-debounce", "fpga-cdc", "fpga-fifo",
            "list", "demo",
        )),
        "flags": frozenset((
            "--format", "--pclk", "--baud", "--os", "--freq", "--psc", "--arr",
            "--bus", "--cb", "--vdd", "--bytes", "--clk", "--sp", "--family", "--ts",
            "--fadc", "--nbits", "--cs", "--r", "--c", "--fc", "--fclk", "--div",
            "--fs", "--fbw", "--fsw", "--dt", "--tclk", "--tco", "--tlogic",
            "--troute", "--tsu", "--fpwm", "--presc", "--reload", "--clkin", "--m",
            "--n", "--p", "--vcomin", "--vcomax", "--vin", "--vout", "--iua",
            "--r25", "--beta", "--temp", "--base", "--ppm", "--target", "--clk-peri",
            "--t0h", "--t1h", "--pulse-us", "--angle", "--range", "--step-deg",
            "--microstep", "--rpm", "--module", "--days", "--mah", "--i",
            "--no-derate", "--page", "--cycles", "--pages", "--sck", "--raw", "--fsr",
            "--clk-div", "--rate", "--ms", "--stages", "--tx-bps", "--read-bps",
            "--burst", "--depth",
        )),
    },
}

_PLACEHOLDER = re.compile(r"<[^>]+>")
_PROSE_CHARS = re.compile(r"[\u4e00-\u9fff，。；：、（）《》“”‘’！？]")


def _lint_next(node, problems, version):
    """next：可选非空字符串，必须是 `<skill-id> <subcommand> [参数]` 形式的可执行命令。

    子命令必须在白名单内；`--flag` 必须是该技能 CLI 支持的参数；除 `<占位符>`
    外不得混入中文说明文字。仅 schema 1.1 允许。
    """
    if "next" not in node:
        return
    if version < 2:
        problems.append("%s 含 next，但 schema 为 1.0（next 仅 schema 1.1 允许）" % node.get("id", "?"))
        return
    nxt = node.get("next")
    if not isinstance(nxt, str) or not nxt.strip():
        problems.append("%s 的 next 非法（必须是非空字符串）" % node.get("id", "?"))
        return
    nxt = nxt.strip()
    if "\n" in nxt:
        problems.append("%s 的 next 必须单行命令：%s" % (node.get("id", "?"), nxt))
        return
    parts = nxt.split()
    skill = parts[0]
    spec = NEXT_SKILLS.get(skill)
    if spec is None:
        problems.append("%s 的 next 必须以技能 id 开头（%s 之一）：%s"
                        % (node.get("id", "?"), "/".join(sorted(NEXT_SKILLS)), nxt))
        return
    if len(parts) < 2 or parts[1] not in spec["subcommands"]:
        problems.append("%s 的 next 子命令非法（%s 可用：%s）：%s"
                        % (node.get("id", "?"), skill,
                           "/".join(sorted(spec["subcommands"])), nxt))
        return
    for tok in parts[2:]:
        if tok.startswith("--") and tok not in spec["flags"]:
            problems.append("%s 的 next 含 %s 不支持的参数 %s：%s"
                            % (node.get("id", "?"), skill, tok, nxt))
            return
    if _PROSE_CHARS.search(_PLACEHOLDER.sub("", nxt)):
        problems.append("%s 的 next 必须是纯命令（说明文字请删掉，参数用 <占位符>）：%s"
                        % (node.get("id", "?"), nxt))


def _lookup_ids(db):
    ids = set()
    for tree in db["trees"]:
        for n in _iter_nodes(tree):
            ids.add(n["id"])
    return ids


def _lint_see(node, problems, known, version):
    """see：可选字符串（"树id/节点id" 或 "节点id"），必须能在已知节点解析。"""
    if "see" not in node:
        return
    if version < 2:
        problems.append("%s 含 see，但 schema 为 1.0（see 仅 schema 1.1 允许）" % node.get("id", "?"))
        return
    s = node.get("see")
    if not isinstance(s, str) or not s.strip():
        problems.append("%s 的 see 非法（必须是非空字符串）" % node.get("id", "?"))
        return
    target = s.strip().split("/")[-1]
    if target not in known:
        problems.append("%s 的 see 指向不存在的节点：%s" % (node.get("id", "?"), s))
    elif target == node.get("id"):
        problems.append("%s 的 see 指向自身：%s" % (node.get("id", "?"), s))


def lint_db(skill, db, problems):
    """schema 校验：必填字段、唯一 id、keywords/fixes 非空 + refs/next/see 格式。"""
    seen = set()
    version = 2 if db.get("schema", "").endswith("/1.1") else 1  # 1.1→2, 1.0→1
    if skill == "embedded-debug-trees":
        known = _lookup_ids(db)
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
                _lint_refs(node, problems, version)
                _lint_see(node, problems, known, version)
                _lint_next(node, problems, version)
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
                _lint_refs(p, problems, version)
                _lint_next(p, problems, version)
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
    if node.get("refs"):
        lines.append("%s  - 依据：%s" % (pad, "；".join(node["refs"])))
    if node.get("see"):
        lines.append("%s  - 转入：%s" % (pad, node["see"]))
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
        for p in cat["pitfalls"]:
            if p.get("refs") or p.get("next"):
                note = []
                if p.get("refs"):
                    note.append("依据：%s" % "；".join(p["refs"]))
                if p.get("next"):
                    note.append("下一步：%s" % p["next"])
                lines.append("- **%s** %s" % (p["title"], "；".join(note)))
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
