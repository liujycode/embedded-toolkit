"""SVD 文件查找，顺序：--svd 参数 > 项目配置 .etk/config.json > 本机 CMSIS-Pack 缓存。

Pack 目录布局：<Packs>/<厂商>/<包名>/<版本>/{SVD,CMSIS/SVD}/*.svd，
两种布局分别对应 Keil STM32F1/F3 包与 STM32F4/G4 包，以及 Nordic、GigaDevice 的常见布局。
"""

from __future__ import annotations

import glob
import json
import os
import re

from .errors import E_INPUT_INVALID, E_SVD_NOT_FOUND, EtkError

CONFIG_RELPATH = os.path.join(".etk", "config.json")
_PACK_PATTERNS = (
    os.path.join("*", "*", "*", "SVD", "*.svd"),
    os.path.join("*", "*", "*", "CMSIS", "SVD", "*.svd"),
    os.path.join("*", "*", "*", "*.svd"),
)
_PACKAGE_SUFFIX = re.compile(r"(?<=\d{3})[A-Z][A-Z0-9]*$")


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


def pack_roots():
    candidates = []
    env_dir = os.environ.get("ETK_PACKS_DIR")
    if env_dir:
        candidates.append(env_dir)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Arm", "Packs"))
    candidates.append(os.path.join(os.path.expanduser("~"), ".arm", "Packs"))
    roots = []
    for cand in candidates:
        absolute = os.path.abspath(cand)
        if os.path.isdir(absolute) and absolute not in roots:
            roots.append(absolute)
    return roots


def _pack_svds(roots):
    found = set()
    for root in roots:
        for pattern in _PACK_PATTERNS:
            for path in glob.glob(os.path.join(root, pattern)):
                found.add(os.path.normpath(path))
    return sorted(found)


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
    if chip:
        roots = pack_roots()
        tried.append("CMSIS-Pack 目录：%s" % (", ".join(roots) if roots else "未找到"))
        matches, key = _match(chip, _pack_svds(roots))
        if matches:
            chosen, others = _choose(matches, key)
            if others:
                shown = "、".join(os.path.basename(p) for p in others[:5])
                notes.append("本机找到多个候选，已选用 %s；其余：%s" % (os.path.basename(chosen), shown))
            return chosen, "本机 CMSIS-Pack", notes
        tried.append("按芯片名 %s 未匹配到任何 .svd" % chip)

    hint = ("用 --svd 指定 .svd 文件；或安装芯片对应的 CMSIS 设备包（Keil Pack Installer 可安装）；"
            "或在项目根目录的 .etk/config.json 中写入 \"svd\" 字段。")
    if not chip:
        hint = "未提供 --chip，无法在本机 CMSIS-Pack 中查找。" + hint
    raise EtkError(
        E_SVD_NOT_FOUND,
        "找不到 SVD 文件",
        hint=hint,
        details={"tried": tried},
    )
