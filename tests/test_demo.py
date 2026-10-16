"""内置演示数据（--demo）完整性与自洽测试：demo 是零配置试用的入口。"""

import os

from etk_core import query
from etk_core.svd import load_device
from helpers import ROOT, run_cli

DEMO = os.path.join(ROOT, "skills", "embedded-register-lookup", "assets", "demo.svd")


def test_demo_file_exists_and_parses_without_warnings():
    assert os.path.isfile(DEMO)
    device = load_device(DEMO)
    assert device.name == "ETK-DEMO"
    assert device.warnings == []
    assert device.vendor
    assert device.cpu == "CM4"


def test_demo_covers_every_feature():
    device = load_device(DEMO)
    # lookup：外设 / 寄存器 / 位域 / 簇
    assert query.lookup(device, "GPIOA")["kind"] == "peripheral"
    assert query.lookup(device, "USART1.CR1")["kind"] == "register"
    assert query.lookup(device, "USART1.CR1.UE")["kind"] == "field"
    assert query.lookup(device, "DMA1.CH1")["kind"] == "cluster"
    # 派生外设
    assert device.peripheral("GPIOB").derived_from == "GPIOA"
    # 地址反查
    assert query.find_address(device, 0x40013800)["kind"] == "exact"
    # 解码、写入视角提示（只读位域 / 写 1 清零）、写入值计算
    assert query.decode(device, "USART1.SR", 0xE0)["value"] == 0xE0
    assert query.decode(device, "GPIOA.IDR", 0x1, as_write=True)["write_notes"]
    assert query.decode(device, "EXTI.PR", 0x1, as_write=True)["write_notes"]
    assert query.set_fields(device, "GPIOA.MODER", ["MODE0=OUTPUT"])["value"] == 1
    # 中断、宏、位域表、位图、区间、搜索
    assert query.find_interrupts(device, "USART1")["matches"][0]["value"] == 37
    assert "#define USART1_CR1_UE_Pos 0U" in query.macros_for(device, "USART1.CR1")["code"]
    assert query.register_fields(device, "GPIOA.MODER")["fields"]
    assert query.diagram(device, "GPIOA.MODER")["legend"]
    assert query.find_in_range(device, 0x40013800, 0x400138FF)["count"] >= 4
    assert query.search(device, "波特率")["total"] >= 1
    info = query.device_info(device)
    assert info["counts"]["peripherals"] == 7
    assert info["counts"]["interrupts"] == 5
    # diff 自比对
    assert query.diff_registers(device, device, "USART1.CR1")["identical"] is True


def test_demo_lint_is_clean():
    res = query.lint(load_device(DEMO))
    assert res["counts"]["total"] == 0


def test_demo_cli_works_without_any_svd_configuration():
    r = run_cli("lookup", "USART1.CR1.UE", "--demo")
    assert r.returncode == 0, r.stderr
    assert "ETK-DEMO" in r.stdout
    assert "合成数据" in r.stdout


def test_demo_cli_markdown_quickstart():
    r = run_cli("fields", "GPIOA.MODER", "--demo", "--format", "md")
    assert r.returncode == 0, r.stderr
    assert "| 位 | 位域 | 访问 | 复位 | 掩码 | 说明 |" in r.stdout


def test_demo_conflicts_with_svd_argument():
    r = run_cli("lookup", "USART1.CR1", "--demo", "--svd", DEMO)
    assert r.returncode == 1
    assert "E_INPUT_INVALID" in r.stdout
