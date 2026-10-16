#!/usr/bin/env python3
"""仓库质量门：CI 与本地提交前都运行。

检查项：
1. etk_core 副本与 shared 一致（tools/sync_core.py --check）
2. 每个技能的 SKILL.md：frontmatter 合法、name 与目录名一致、description 长度、正文行数 ≤ 500、
   脚本版本号与 metadata.version 一致、存在触发评测用例（正例 ≥ 20、反例 ≥ 10）
3. 运行时代码（shared 与各技能 scripts）满足 Python 3.9 语法
4. 运行时代码只 import 标准库

用法：python tools/check_repo.py    （无问题时退出码 0）
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import sync_core  # noqa: E402

STDLIB_ALLOWED = {
    "__future__", "argparse", "collections", "dataclasses", "difflib", "glob",
    "hashlib", "json", "os", "re", "sys", "time", "typing", "xml",
}
LOCAL_PACKAGES = {"etk_core"}  # 随技能分发的本地核心库，不是第三方依赖
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)
MIN_POSITIVE = 20
MIN_NEGATIVE = 10
MAX_BODY_LINES = 500


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("缺少 frontmatter 起始 ---")
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        raise ValueError("frontmatter 未闭合（缺少结束 ---）")
    data = {}
    current = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, sep, value = raw.strip().partition(":")
        if not sep:
            raise ValueError("无法解析 frontmatter 行：%s" % raw)
        value = value.strip().strip('"').strip("'")
        if indent == 0:
            if value == "":
                data[key] = {}
                current = key
            else:
                data[key] = value
                current = None
        elif current is not None and isinstance(data.get(current), dict):
            data[current][key] = value
    body = "\n".join(lines[end + 1:])
    return data, body


def check_sync():
    issues = []
    for target in sync_core.skill_targets():
        issues.extend(sync_core.diff(target))
    return issues


def check_skills():
    issues = []
    base = os.path.join(ROOT, "skills")
    for name in sorted(os.listdir(base)):
        skill_dir = os.path.join(base, name)
        if not os.path.isdir(skill_dir):
            continue
        rel = "skills/%s" % name
        md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(md_path):
            issues.append("%s 缺少 SKILL.md" % rel)
            continue
        with open(md_path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            meta, body = parse_frontmatter(text)
        except ValueError as exc:
            issues.append("%s/SKILL.md：%s" % (rel, exc))
            continue
        skill_name = meta.get("name", "")
        if not NAME_RE.match(skill_name) or len(skill_name) > 64:
            issues.append("%s：name=%r 不符合规范（小写字母、数字、单个连字符，≤64 字符）" % (rel, skill_name))
        if skill_name != name:
            issues.append("%s：name=%r 与目录名不一致" % (rel, skill_name))
        description = meta.get("description", "")
        if not description or len(description) > 1024:
            issues.append("%s：description 为空或超过 1024 字符" % rel)
        compat = meta.get("compatibility")
        if compat is not None and len(compat) > 500:
            issues.append("%s：compatibility 超过 500 字符" % rel)
        body_lines = len(body.splitlines())
        if body_lines > MAX_BODY_LINES:
            issues.append("%s/SKILL.md：正文 %d 行，超过 %d 行，请把细节移到 references/" % (rel, body_lines, MAX_BODY_LINES))
        version = (meta.get("metadata") or {}).get("version")
        script_versions = {}
        scripts = os.path.join(skill_dir, "scripts")
        if os.path.isdir(scripts):
            for fname in sorted(os.listdir(scripts)):
                if fname.endswith(".py"):
                    with open(os.path.join(scripts, fname), encoding="utf-8") as fh:
                        found = VERSION_RE.search(fh.read())
                    if found:
                        script_versions[fname] = found.group(1)
        if not script_versions:
            issues.append("%s：scripts/ 中没有 __version__" % rel)
        for fname, sv in script_versions.items():
            if version != sv:
                issues.append("%s：metadata.version=%r 与 scripts/%s 的 __version__=%r 不一致" % (rel, version, fname, sv))
        trig_path = os.path.join(ROOT, "tests", "trigger", "%s.json" % name)
        if not os.path.isfile(trig_path):
            issues.append("缺少触发评测用例 tests/trigger/%s.json" % name)
        else:
            with open(trig_path, encoding="utf-8") as fh:
                trig = json.load(fh)
            if len(trig.get("positive", [])) < MIN_POSITIVE:
                issues.append("tests/trigger/%s.json：正例少于 %d 条" % (name, MIN_POSITIVE))
            if len(trig.get("negative", [])) < MIN_NEGATIVE:
                issues.append("tests/trigger/%s.json：反例少于 %d 条" % (name, MIN_NEGATIVE))
    return issues


def _runtime_files():
    files = []
    core = os.path.join(ROOT, "shared", "etk_core")
    files.extend(os.path.join(core, f) for f in sorted(os.listdir(core)) if f.endswith(".py"))
    base = os.path.join(ROOT, "skills")
    for name in sorted(os.listdir(base)):
        scripts = os.path.join(base, name, "scripts")
        if os.path.isdir(scripts):
            files.extend(os.path.join(scripts, f) for f in sorted(os.listdir(scripts)) if f.endswith(".py"))
    return files


def check_py39():
    issues = []
    for path in _runtime_files():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            ast.parse(src, filename=path, feature_version=(3, 9))
        except SyntaxError as exc:
            issues.append("%s：不兼容 Python 3.9 语法（第 %s 行）" % (os.path.relpath(path, ROOT), exc.lineno))
    return issues


def check_stdlib():
    issues = []
    for path in _runtime_files():
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name not in STDLIB_ALLOWED and name not in LOCAL_PACKAGES:
                    issues.append("%s：运行时引入了非标准库模块 %s" % (os.path.relpath(path, ROOT), name))
    return issues


def run_all():
    return check_sync() + check_skills() + check_py39() + check_stdlib()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    issues = run_all()
    if issues:
        for item in issues:
            print("问题：" + item)
        print("共 %d 个问题。" % len(issues))
        return 1
    print("仓库检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
