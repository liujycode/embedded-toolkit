"""输出封装：证据标签、来源信息、统一的 JSON 信封。"""

from __future__ import annotations

import os

LABEL_VERIFIED = "已核验"
LABEL_MANUAL = "需查手册"
LABEL_MEASURE = "需实测"
LABEL_UNDETERMINED = "未判定"
LABELS = (LABEL_VERIFIED, LABEL_MANUAL, LABEL_MEASURE, LABEL_UNDETERMINED)


def source_meta(device):
    return {
        "file": os.path.basename(device.path),
        "path": device.path,
        "device": device.name,
        "version": device.version,
    }


def envelope(tool, version, results=None, warnings=None, errors=None):
    errs = list(errors or [])
    return {
        "ok": not errs,
        "tool": tool,
        "version": version,
        "results": list(results or []),
        "warnings": list(warnings or []),
        "errors": errs,
    }
