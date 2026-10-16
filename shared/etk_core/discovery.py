"""SVD 文件查找与盘点，顺序：
--svd 参数 > 项目配置 .etk/config.json > 项目内扫描 > 环境变量 ETK_SVD_DIR > 本机 Pack 缓存。

Pack 目录布局：<Packs>/<厂商>/<包名>/<版本>/{SVD,CMSIS/SVD}/*.svd，
两种布局分别对应 Keil STM32F1/F3 包与 STM32F4/G4 包，以及 Nordic、GigaDevice 的常见布局。

除查找外还提供 doctor_report（环境体检）与 list_devices（本机 SVD 盘点），
供 CLI 的 doctor / devices 子命令使用。
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

from .errors import E_INPUT_INVALID, E_SVD_NOT_FOUND, EtkError
from .svd import device_name_fast

CONFIG_RELPATH = os.path.join(".etk", "config.json")
ENV_SVD_DIR = "ETK_SVD_DIR"
ENV_PACKS_DIR = "ETK_PACKS_DIR"

_PACK_PATTERNS = (
    os.path.join("*", "*", "*", "SVD", "*.svd"),
    os.path.join("*", "*", "*", "CMSIS", "SVD", "*.svd"),
    os.path.join("*", "*", "*", "*.svd"),
)
_PACKAGE_SUFFIX = re.compile(r"(?<=\d{3})[A-Z][A-Z0-9]*$")

# 项目内扫描的限制：深度 ≤ 6、目录数 ≤ 4000、结果 ≤ 50（超限会给出提示）
_PROJECT_MAX_DEPTH = 6
_PROJECT_MAX_DIRS = 4000
_PROJECT_MAX_FILES = 50
_PROJECT_SKIP_DIRS = frozenset({
    "node_modules", "__pycache__", "site-packages",
    "appdata", "windows", "program files", "program files (x86)",
    "library", "$recycle.bin", "system volume information",
})
# devices 命令读取设备名的条数上限（超出的用文件名代替）
_DEVICE_NAME_MAX = 400


def find_config(start):
    cur = os.path.abspath(start)
    while True:
        cand = os.path.join(cur, CONFIG_RELPATH)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def read_config(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise EtkError(
            E_INPUT_INVALID,
            "项目配置无法解析：%s（%s）" % (path, exc),
            hint="检查 .etk/config.json 是否为合法 JSON。",
        ) from None
    if not isinstance(data, dict):
        raise EtkError(E_INPUT_INVALID, "项目配置必须是 JSON 对象：%s" % path)
    return data


def _dedup(paths):
    out = []
    seen = set()
    for item in paths:
        key = os.path.normcase(os.path.abspath(item))
        if key not in seen:
            seen.add(key)
            out.append(os.path.normpath(item))
    return out


def extra_svd_roots():
    """ETK_SVD_DIR 指定的额外 SVD 目录（多个用系统路径分隔符分开）。"""
    raw = os.environ.get(ENV_SVD_DIR) or ""
    dirs = [os.path.expanduser(p.strip()) for p in raw.split(os.pathsep)]
    return _dedup([d for d in dirs if d and os.path.isdir(d)])


def pack_candidates():
    """本机已知的 CMSIS-Pack 位置，包含不存在的候选（doctor 用来显示原因）。"""
    home = os.path.expanduser("~")
    items = []
    env_dir = os.environ.get(ENV_PACKS_DIR)
    if env_dir:
        items.append(("环境变量 ETK_PACKS_DIR", env_dir))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        items.append(("CMSIS-Pack（Windows 默认）", os.path.join(local, "Arm", "Packs")))
    items.append(("CMSIS-Pack（用户目录 .arm）", os.path.join(home, ".arm", "Packs")))
    items.append(("cpackget 缓存（Linux）", os.path.join(home, ".cache", "arm", "packs")))
    items.append(("cpackget 缓存（macOS）", os.path.join(home, "Library", "Caches", "Arm", "Packs")))
    return items


def pack_roots():
    roots = []
    for _, path in pack_candidates():
        absolute = os.path.abspath(path)
        if os.path.isdir(absolute):
            roots.append(absolute)
    return _dedup(roots)


def _pack_svds(roots):
    found = set()
    for root in roots:
        for pattern in _PACK_PATTERNS:
            for path in glob.glob(os.path.join(root, pattern)):
                found.add(os.path.normpath(path))
    return sorted(found)


def project_svds(start):
    """在项目目录内浅层扫描 .svd：深度 ≤ 6，跳过隐藏与依赖目录。

    返回 (按文件名自然排序的列表, 是否达到上限)。
    """
    root0 = os.path.abspath(start)
    found = []
    truncated = False
    visited = 0
    for root, dirs, files in os.walk(root0):
        rel = os.path.relpath(root, root0)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= _PROJECT_MAX_DEPTH:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d.lower() not in _PROJECT_SKIP_DIRS]
        visited += 1
        if visited > _PROJECT_MAX_DIRS:
            truncated = True
            break
        for name in files:
            if name.lower().endswith(".svd"):
                found.append(os.path.normpath(os.path.join(root, name)))
                if len(found) >= _PROJECT_MAX_FILES:
                    truncated = True
                    break
        if truncated:
            break
    return sorted(found, key=_natural), truncated


def _scan_roots(roots):
    found = []
    truncated = False
    for root in roots:
        items, limit_hit = project_svds(root)
        found.extend(items)
        truncated = truncated or limit_hit
    return _dedup(found), truncated


def _chip_keys(chip):
    """芯片名候选：完整名，再去掉封装后缀（STM32G431RB -> STM32G431）。"""
    base = chip.strip().upper()
    keys = [base]
    stripped = _PACKAGE_SUFFIX.sub("", base)
    if stripped and stripped != base and len(stripped) >= 6:
        keys.append(stripped)
    return keys


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0].upper()


def _natural(path):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", path)]


def _wildcard_equal(key, stem):
    """文件名里的 x 是厂商的通配写法（如 STM32F40x.svd 覆盖 STM32F405/407/415/417）。

    等长比较：stem 中的 X 匹配任意字符，其余字符必须一致。
    只在精确与前缀匹配都失败后使用，避免抢走更具体的文件（如 F401 优先 F401x.svd）。
    """
    if len(stem) != len(key):
        return False
    for s_ch, k_ch in zip(stem, key):
        if s_ch != k_ch and s_ch != "X":
            return False
    return True


def _match(chip, paths):
    for key in _chip_keys(chip):
        exact = [p for p in paths if _stem(p) == key]
        if exact:
            return exact, key
        prefix = [p for p in paths if _stem(p).startswith(key)]
        if prefix:
            return prefix, key
        wildcard = [p for p in paths if _wildcard_equal(key, _stem(p))]
        if wildcard:
            return wildcard, key
    return [], None


def _choose(paths, key):
    """优先精确同名；其次名称最短者；同名多个（不同版本）取自然排序最大的。"""
    def rank(path):
        stem = _stem(path)
        return (0 if stem == key else 1, len(stem))

    best_rank = min(rank(p) for p in paths)
    top = [p for p in paths if rank(p) == best_rank]
    chosen = max(top, key=_natural)
    others = sorted((p for p in paths if p != chosen), key=_natural)
    return chosen, others


def _pick_from(chip, paths, label, notes):
    """在一批路径中按芯片名匹配；命中时返回路径，否则返回 None。label 用于提示语前缀。"""
    matches, key = _match(chip, paths)
    if not matches:
        return None
    chosen, others = _choose(matches, key)
    if others:
        shown = "、".join(os.path.basename(p) for p in others[:5])
        notes.append("%s找到多个候选，已选用 %s；其余：%s" % (label, os.path.basename(chosen), shown))
    return chosen


def find_svd(svd=None, chip=None, project_dir=None):
    """返回 (SVD 路径, 选择方式, 提示列表)。找不到时抛出 E_SVD_NOT_FOUND，并列出已尝试的位置。"""
    start = project_dir or os.getcwd()
    notes = []
    if svd:
        path = os.path.abspath(svd)
        if os.path.isfile(path):
            return path, "参数 --svd", notes
        raise EtkError(
            E_SVD_NOT_FOUND,
            "--svd 指定的文件不存在：%s" % svd,
            hint="检查路径；可以是绝对路径，也可以相对于当前目录。",
        )

    config_path = find_config(start)
    config = read_config(config_path) if config_path else {}
    cfg_svd = config.get("svd")
    if cfg_svd:
        root = os.path.dirname(os.path.dirname(config_path))
        path = os.path.normpath(os.path.join(root, cfg_svd))
        if os.path.isfile(path):
            return path, "项目配置 %s" % config_path, notes
        raise EtkError(
            E_SVD_NOT_FOUND,
            "项目配置中的 svd 路径不存在：%s" % path,
            hint="检查 .etk/config.json 中 svd 字段（相对于项目根目录）。",
        )

    chip = chip or config.get("chip")
    tried = [
        "--svd：未提供",
        "项目配置：%s" % (config_path or "未找到 .etk/config.json"),
    ]
    files, truncated = project_svds(start)
    if truncated:
        notes.append("项目内扫描达到上限（深度 %d、最多 %d 个文件），可能还有更多 .svd；可用 --svd 明确指定"
                     % (_PROJECT_MAX_DEPTH, _PROJECT_MAX_FILES))
    if chip:
        if files:
            picked = _pick_from(chip, files, "项目内", notes)
            if picked:
                return picked, "项目内扫描", notes
            tried.append("项目内扫描（%d 个 .svd）未匹配 %s" % (len(files), chip))
        else:
            tried.append("项目内扫描：没有 .svd")
        env_roots = extra_svd_roots()
        if env_roots:
            env_files, _ = _scan_roots(env_roots)
            picked = _pick_from(chip, env_files, "ETK_SVD_DIR ", notes) if env_files else None
            if picked:
                return picked, "环境变量 ETK_SVD_DIR", notes
            tried.append("ETK_SVD_DIR（%d 个 .svd）未匹配 %s" % (len(env_files), chip))
        roots = pack_roots()
        tried.append("CMSIS-Pack 目录：%s" % (", ".join(roots) if roots else "未找到"))
        picked = _pick_from(chip, _pack_svds(roots), "本机", notes)
        if picked:
            return picked, "本机 CMSIS-Pack", notes
        tried.append("按芯片名 %s 未匹配到任何 .svd" % chip)
    else:
        if len(files) == 1:
            return files[0], "项目内扫描", notes
        if len(files) > 1:
            shown = "、".join(os.path.basename(p) for p in files[:10])
            raise EtkError(
                E_SVD_NOT_FOUND,
                "当前目录附近找到 %d 个 SVD 文件，无法确定用哪一个" % len(files),
                hint="用 --svd 指定其一，或用 --chip 指定芯片名。候选：%s%s"
                     % (shown, " 等" if len(files) > 10 else ""),
                details={"found": [os.path.basename(p) for p in files]},
            )

    hint = ("用 --svd 指定 .svd 文件；把 .svd 放进项目目录（工具会自动扫描）；"
            "设置环境变量 ETK_SVD_DIR 指向自备 SVD 目录；或安装芯片对应的 CMSIS 设备包"
            "（Keil Pack Installer 可安装）；或在项目根目录的 .etk/config.json 中写入 \"svd\" 字段。")
    if not chip:
        hint = "未提供 --chip，也无法从项目或配置确定芯片。" + hint
    raise EtkError(
        E_SVD_NOT_FOUND,
        "找不到 SVD 文件",
        hint=hint,
        details={"tried": tried},
    )


def list_devices(start=None, keyword=None, limit=200):
    """盘点本机可用的 SVD：项目扫描 + ETK_SVD_DIR + CMSIS-Pack 缓存（按文件去重）。"""
    start = os.path.abspath(start or os.getcwd())
    entries = []
    sources = []
    seen = set()

    def add_source(label, paths, note=None):
        added = 0
        for path in paths:
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "file": os.path.basename(path),
                "path": path,
                "device": None,
                "source": label,
            })
            added += 1
        sources.append({"name": label, "count": added, "note": note})

    project_files, truncated = project_svds(start)
    add_source("项目内扫描", project_files, note=start)
    env_roots = extra_svd_roots()
    if env_roots:
        env_files, _ = _scan_roots(env_roots)
        add_source("ETK_SVD_DIR", env_files, note="；".join(env_roots))
    add_source("CMSIS-Pack", _pack_svds(pack_roots()))

    for index, entry in enumerate(entries):
        if index < _DEVICE_NAME_MAX:
            name = device_name_fast(entry["path"])
        else:
            name = None
        entry["device"] = name or os.path.splitext(entry["file"])[0]

    needle = (keyword or "").strip().lower()
    if needle:
        matched = [
            e for e in entries
            if needle in e["file"].lower()
            or needle in e["device"].lower()
            or needle in e["path"].lower()
        ]
    else:
        matched = entries
    matched.sort(key=lambda e: (e["file"].lower(), e["path"].lower()))
    return {
        "kind": "devices",
        "keyword": keyword or None,
        "total": len(matched),
        "truncated": len(matched) > limit,
        "entries": matched[:limit],
        "sources": sources,
        "note": "按文件去重；设备名直接读自 SVD（读不到时用文件名代替）。",
        "label": "已盘点",
    }


def doctor_report(start=None, demo_path=None):
    """环境体检：Python 版本、SVD 来源（存在与否、数量）与上手建议。"""
    start = os.path.abspath(start or os.getcwd())
    checks = []
    all_files = []

    def add(name, path, exists, count, note):
        checks.append({
            "name": name,
            "path": path,
            "exists": bool(exists),
            "count": count,
            "note": note,
        })

    config_path = find_config(start)
    add("项目配置 .etk/config.json", config_path, bool(config_path), None,
        config_path or "未找到（可在其中写 \"svd\" 或 \"chip\"）")

    project_files, truncated = project_svds(start)
    all_files.extend(project_files)
    add("项目内扫描", start, True, len(project_files),
        "从当前目录向下深度 ≤ %d" % _PROJECT_MAX_DEPTH
        + ("；达到上限，可能还有更多" if truncated else ""))

    env_roots = extra_svd_roots()
    env_files = []
    if env_roots:
        env_files, _ = _scan_roots(env_roots)
        all_files.extend(env_files)
    add("环境变量 ETK_SVD_DIR", os.environ.get(ENV_SVD_DIR) or None, bool(env_roots),
        len(env_files) if env_roots else None,
        "；".join(env_roots) if env_roots
        else "未设置（可指向自备 SVD 目录，多个用 %s 分隔）" % os.pathsep)

    for label, path in pack_candidates():
        absolute = os.path.abspath(path)
        exists = os.path.isdir(absolute)
        count = None
        note = "不存在"
        if exists:
            found = _pack_svds([absolute])
            all_files.extend(found)
            count = len(found)
            note = absolute
        add(label, os.path.abspath(path), exists, count, note)

    idf = os.environ.get("IDF_PATH")
    if idf:
        soc = os.path.join(idf, "components", "soc")
        idf_files = sorted(glob.glob(os.path.join(soc, "**", "*.svd"), recursive=True)) if os.path.isdir(soc) else []
        all_files.extend(idf_files)
        add("ESP-IDF（IDF_PATH）", idf, os.path.isdir(idf), len(idf_files),
            "components/soc 下找到 %d 个" % len(idf_files))

    demo_exists = bool(demo_path) and os.path.isfile(demo_path)
    add("内置演示数据（--demo）", demo_path, demo_exists, None,
        demo_path if demo_exists else "缺失（安装不完整）")

    total = len(_dedup(all_files))
    advice = []
    if total == 0:
        advice.append("本机没有找到任何 .svd：可安装芯片的 CMSIS 设备包（Keil Pack Installer / cpackget），"
                      "或把 .svd 放进项目目录（工具会自动扫描），或用 ETK_SVD_DIR 指向自备 SVD 目录。")
    else:
        advice.append("直接查询：lookup USART1.CR1 --chip <芯片名>；列出本机可用芯片：devices。")
    if demo_exists:
        advice.append("想先试一下：任何查询命令加 --demo 使用内置演示芯片（合成数据，非真实芯片）。")
    if not env_roots:
        advice.append("有自备 SVD 目录时：设置环境变量 ETK_SVD_DIR（多个用 %s 分隔）即可被自动找到。" % os.pathsep)
    return {
        "kind": "doctor",
        "python": "%d.%d.%d" % sys.version_info[:3],
        "platform": sys.platform,
        "checks": checks,
        "total_svds": total,
        "advice": advice,
        "label": "环境体检",
    }
