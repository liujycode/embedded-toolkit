"""SVD 解析结果缓存：把解析好的 Device 序列化为 JSON 落盘，重复查询直接反序列化。

动机：大芯片 SVD（几 MB 到几十 MB）解析一次要几百毫秒到数秒；实测 JSON 往返比
重新解析快 4~7 倍。缓存按（文件绝对路径、字节数、纳秒级修改时间）失效，
任何环节失败都静默降级为直接解析，不影响结果正确性。

开关：
- `ETK_NO_CACHE=1` 关闭缓存
- `ETK_CACHE_DIR` 自定义缓存目录（默认 `%LOCALAPPDATA%\\etk\\cache` 或 `~/.cache/etk`）
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict

from .svd import (
    Device,
    EnumValue,
    Field,
    Interrupt,
    Peripheral,
    Register,
    load_device as _load_device,
)

# 2: EnumValue.usage（读/写枚举分组）——旧缓存缺该字段，必须整体失效
CACHE_FORMAT = 2
ENV_NO_CACHE = "ETK_NO_CACHE"
ENV_CACHE_DIR = "ETK_CACHE_DIR"


def cache_dir():
    custom = os.environ.get(ENV_CACHE_DIR)
    if custom:
        return os.path.abspath(os.path.expanduser(custom))
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return os.path.join(local, "etk", "cache")
    return os.path.join(os.path.expanduser("~"), ".cache", "etk")


def _cache_file(path):
    key = hashlib.sha1(
        os.path.normcase(os.path.abspath(path)).encode("utf-8", "replace")
    ).hexdigest()[:16]
    return os.path.join(cache_dir(), "svd-%s-f%d.json" % (key, CACHE_FORMAT))


def cache_stats():
    """给 doctor 用：缓存目录、条目数与是否启用。"""
    directory = cache_dir()
    enabled = not os.environ.get(ENV_NO_CACHE)
    count = 0
    try:
        if os.path.isdir(directory):
            count = sum(
                1 for name in os.listdir(directory)
                if name.startswith("svd-") and name.endswith(".json")
            )
    except OSError:
        count = 0
    return {"dir": directory, "count": count, "enabled": enabled}


def _rebuild(data):
    peripherals = []
    for item in data.get("peripherals", []):
        registers = []
        for reg in item.get("registers", []):
            fields = []
            for fld in reg.get("fields", []):
                enums = [EnumValue(**e) for e in fld.get("enums", [])]
                fields.append(Field(
                    name=fld["name"],
                    lsb=fld["lsb"],
                    width=fld["width"],
                    access=fld["access"],
                    description=fld["description"],
                    enums=enums,
                    modified_write_values=fld.get("modified_write_values", ""),
                    read_action=fld.get("read_action", ""),
                ))
            registers.append(Register(
                name=reg["name"],
                offset=reg["offset"],
                size=reg["size"],
                access=reg["access"],
                reset_value=reg["reset_value"],
                reset_mask=reg["reset_mask"],
                description=reg["description"],
                fields=fields,
                modified_write_values=reg.get("modified_write_values", ""),
                read_action=reg.get("read_action", ""),
            ))
        interrupts = [Interrupt(**i) for i in item.get("interrupts", [])]
        peripherals.append(Peripheral(
            name=item["name"],
            base_address=item["base_address"],
            description=item["description"],
            group_name=item["group_name"],
            derived_from=item["derived_from"],
            address_span=item["address_span"],
            registers=registers,
            interrupts=interrupts,
        ))
    return Device(
        name=data["name"],
        version=data["version"],
        description=data["description"],
        path=data["path"],
        peripherals=peripherals,
        warnings=list(data.get("warnings", [])),
        vendor=data.get("vendor", ""),
        cpu=data.get("cpu", ""),
    )


def _read_cache(cache_path, stamp):
    try:
        with open(cache_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != CACHE_FORMAT or data.get("stamp") != stamp:
            return None
        return _rebuild(data["device"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(cache_path, stamp, device):
    directory = os.path.dirname(cache_path)
    try:
        os.makedirs(directory, exist_ok=True)
        payload = {"format": CACHE_FORMAT, "stamp": stamp, "device": asdict(device)}
        fd, tmp_path = tempfile.mkstemp(prefix=".svd-cache-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp_path, cache_path)
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except OSError:
        pass  # 缓存是尽力而为，失败不影响主流程


def load_device_cached(path):
    """与 svd.load_device 行为一致，但优先使用未过期的缓存。"""
    if os.environ.get(ENV_NO_CACHE):
        return _load_device(path)
    path = os.path.abspath(os.fspath(path))
    try:
        stat = os.stat(path)
        stamp = [os.path.normcase(path), int(stat.st_size), int(stat.st_mtime_ns)]
    except OSError:
        return _load_device(path)  # 统一由 load_device 报错
    cache_path = _cache_file(path)
    device = _read_cache(cache_path, stamp)
    if device is not None:
        return device
    device = _load_device(path)
    _write_cache(cache_path, stamp, device)
    return device
