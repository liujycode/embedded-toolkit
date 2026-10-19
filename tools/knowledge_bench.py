#!/usr/bin/env python3
"""知识检索评测：症状/场景查询 → 期望命中的树或坑位（注入式，逐条 ground truth）。

- check：跑全部用例，命中率 < 100% 时退出码 1。
- doc：把结果写入 benchmarks/knowledge-recall.md。

用例与被测实现同仓：直接 import 技能脚本里的 tokenize/search（测的就是分发代码）。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "benchmarks", "knowledge-recall.md")

# (查询, 期望树 id)
TREE_CASES = [
    ("程序总是莫名其妙 HardFault，怎么定位？", "hardfault"),
    ("单片机跑飞了，偶尔死机复位，帮我排查思路", "hardfault"),
    ("CFSR 里 PRECISERR 置位怎么查", "hardfault"),
    ("任务栈溢出水位的确认方法", "hardfault"),
    ("函数指针跳飞，PC 落在 0xE0000000 段", "hardfault"),
    ("IMPRECISERR 报错，怀疑 DMA 目标地址", "hardfault"),
    ("UNDEFINSTR 未定义指令 fault", "hardfault"),
    ("内核 LOCKUP 状态怎么出来的", "hardfault"),
    ("浮点中断一进就挂，NOCP 置位", "hardfault"),
    ("故障偶发难抓，怎么留现场", "hardfault"),
    ("野指针非法访问怎么定位", "hardfault"),
    ("DMA 缓冲区放 DTCM 里 DMA 到不了", "hardfault"),
    ("I2C 读传感器一直超时，一步一步怎么查？", "comm"),
    ("SPI 完全没有输出", "comm"),
    ("UART 波特率对不上一直乱码", "comm"),
    ("配置回读全对但通信还是失败", "comm"),
    ("I2C 的 SDA 被从机拉死了怎么解救", "comm"),
    ("RS485 收不到回包", "comm"),
    ("CPOL CPHA 四种组合怎么选", "comm"),
    ("示波器抓 I2C 的 ACK", "comm"),
    ("IDLE 空闲中断做不定长接收", "comm"),
    ("DMA 只收到第一次数据", "dma"),
    ("DMA 传输的数据偶尔损坏", "dma"),
    ("H7 上 DMA 收到的是旧数据，cache 问题", "dma"),
    ("DMA 根本不启动传输", "dma"),
    ("DMA 数据错位，半字当字节", "dma"),
    ("DMAMUX 请求映射怎么核对", "dma"),
    ("DMA 双缓冲 ping-pong 怎么做", "dma"),
    ("FreeRTOS 任务不跑", "rtos"),
    ("系统跑一小时就死锁", "rtos"),
    ("优先级反转怎么破", "rtos"),
    ("中断里调用 FreeRTOS API 挂死", "rtos"),
    ("任务卡在 vTaskDelay 不再继续", "rtos"),
    ("configMAX_SYSCALL_INTERRUPT_PRIORITY 的关系", "rtos"),
    ("中断优先级数值和 BASEPRI 的关系", "rtos"),
    ("上电起不来卡在时钟初始化", "boot"),
    ("Bootloader 跳 App 后 HardFault", "boot"),
    ("设备周期性复位，原因不明", "boot"),
    ("BOOT0 引脚电平怎么查", "boot"),
    ("SWD 连不上调试器", "boot"),
    ("看门狗复位循环，喂狗路径", "boot"),
    ("进入停机模式后串口乱码", "pwr"),
    ("低功耗睡死叫不醒", "pwr"),
    ("WFI 之后电流降不下来", "pwr"),
    ("调试器挂着低功耗正常，拔了就异常", "pwr"),
    ("唤醒后定时器变慢了", "pwr"),
]

# (查询, 期望坑位 id)
PITFALL_CASES = [
    ("配置 I2C 有哪些常见的坑要注意？", "i2c-pullup"),
    ("SPI 的 CPOL 和 CPHA 应该怎么选？", "spi-cpha"),
    ("GPIO 配置成复用模式有什么要注意的？", "gpio-af"),
    ("I2C 引脚能不能配成推挽输出", "gpio-i2c-pushpull"),
    ("时钟使能了外设还是不工作", "rcc-no-enable"),
    ("PLL 超频后系统不稳", "rcc-vos"),
    ("HSI 做 UART 时钟长距离乱码", "rcc-hsi-uart"),
    ("定时器周期总是差一倍", "rcc-tim-clk"),
    ("APB 分频和定时器时钟的关系", "rcc-tim-clk"),
    ("非 FT 引脚接了 5V 会怎样", "gpio-5v"),
    ("ADC 采集引脚噪声很大", "gpio-analog"),
    ("EXTI 标志位清除顺序", "exti-flag"),
    ("NVIC 优先级分组怎么理解", "exti-group"),
    ("高优先级中断里做慢活会怎样", "exti-slow-isr"),
    ("FreeRTOS 的 configMAX_SYSCALL 优先级限制", "exti-rtos-prio"),
    ("EXTI 线映射 EXTICR 怎么配", "exti-line-map"),
    ("EXTI pending 置位但不进中断", "exti-nvic"),
    ("ARR 和 PSC 怎么算频率", "tim-arr"),
    ("改了 ARR 新周期不生效", "tim-ug"),
    ("互补输出没配死区会怎样", "tim-bdtr"),
    ("编码器模式读数跳变", "tim-enc"),
    ("定时器配完不计数", "tim-cen"),
    ("多个定时器怎么同步", "tim-sync-master"),
    ("ADC 采样时间怎么选", "adc-sample-time"),
    ("ADC 上电要先做校准吗", "adc-cal"),
    ("规则组和注入组什么区别", "adc-inject"),
    ("ADC 参考电压漂了怎么办", "adc-vref"),
    ("H7 的 DTCM 里 DMA 不搬数据", "adc-dma-mem"),
    ("ADC 多通道只有第一路有数据", "adc-seqlen"),
    ("G4 的 ADC 校准顺序", "adc-cal-aden"),
    ("波特率寄存器 BRR 手算", "uart-brr"),
    ("USART 完全无响应", "uart-clk"),
    ("DMA 加空闲中断做不定长接收", "uart-idle"),
    ("串口校验位和停止位配置", "uart-frame"),
    ("RS485 方向脚什么时候切", "uart-rs485-de"),
    ("I2C 上拉电阻选多大", "i2c-pullup"),
    ("I2C 从机地址 NAK", "i2c-addr"),
    ("I2C 的 SDA 一直为低", "i2c-stuck"),
    ("F1 的 I2C 状态机陷阱", "i2c-f1-sr"),
    ("I2C 时钟拉伸是什么", "i2c-stretch"),
    ("I2C 总线挂死怎么恢复", "i2c-timeout-recovery"),
    ("SPI 全是 0xFF 或错位", "spi-cpha"),
    ("SPI 最后一字节丢失", "spi-cs-early"),
    ("SPI 的 16 位和 8 位帧", "spi-frame"),
    ("SPI 的 OVR 溢出", "spi-ovr"),
    ("SPI 片选用软件还是硬件 NSS", "spi-cs-gpio"),
    ("CAN 位时序采样点", "can-bit-timing"),
    ("CAN 过滤器收不到报文", "can-filter"),
    ("CAN 发送丢帧", "can-tx-full"),
    ("CAN 终端电阻", "can-term"),
    ("CAN 环回自测 loopback", "can-loopback"),
    ("FDCAN 内核时钟配置", "fdcan-clock"),
    ("调试时看门狗把板子复位了", "wdg-dbg-freeze"),
    ("喂狗应该放在哪里", "wdg-feed-path"),
    ("WWDG 窗口期复位", "wdg-wwdg-window"),
    ("没用看门狗也复位循环", "wdg-hw-option"),
    ("standby 醒来变量丢了", "pwr-sram-retention"),
    ("低功耗电流降不下来引脚漏电", "pwr-gpio-leak"),
    ("唤醒后时钟没重配", "pwr-wake-clock"),
    ("唤醒标志没清进不了低功耗", "pwr-wakeup-flag"),
]


def _load_module(skill, script):
    path = os.path.join(ROOT, "skills", skill, "scripts", script)
    spec = importlib.util.spec_from_file_location(script[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evaluate():
    trees = _load_module("embedded-debug-trees", "trees.py")
    pitfalls = _load_module("embedded-peripheral-pitfalls", "pitfalls.py")
    tdb = trees.load_db()
    pdb = pitfalls.load_db()

    rows = []
    miss = []
    for query, expect in TREE_CASES:
        terms = trees.tokenize(query)
        hits = []
        for tree in tdb["trees"]:
            trees.walk(tree, terms, [], hits, query.lower())
        got = [(h[1][0] if h[1] else h[2].get("id")) for h in hits]
        ok = expect in got
        rows.append(("debug-trees", query, expect, ok, got[:4]))
        if not ok:
            miss.append(("debug-trees", query, expect, got[:4]))
    for query, expect in PITFALL_CASES:
        terms = pitfalls.tokenize(query)
        hits = pitfalls.search(pdb, terms, raw=query.lower())
        got = [h[2]["id"] for h in hits]
        ok = expect in got
        rows.append(("pitfalls", query, expect, ok, got[:4]))
        if not ok:
            miss.append(("pitfalls", query, expect, got[:4]))
    total = len(rows)
    hit = sum(1 for r in rows if r[3])
    return rows, hit, total, miss


def write_doc(rows, hit, total):
    lines = [
        "# 知识检索评测（embedded-debug-trees / embedded-peripheral-pitfalls）",
        "",
        "用例 = 真实症状/场景查询 + 期望命中的树或坑位（注入式，逐条 ground truth）；",
        "被测实现 = 技能脚本里的检索函数本体（import 复用，测的就是分发代码）。",
        "",
        "| 技能 | 用例 | 命中 | 召回 |",
        "|---|---|---|---|",
    ]
    t_rows = [r for r in rows if r[0] == "debug-trees"]
    p_rows = [r for r in rows if r[0] == "pitfalls"]
    lines.append("| embedded-debug-trees（按树） | %d | %d | %.1f%% |" % (
        len(t_rows), sum(1 for r in t_rows if r[3]), 100.0 * sum(1 for r in t_rows if r[3]) / len(t_rows)))
    lines.append("| embedded-peripheral-pitfalls（按坑位） | %d | %d | %.1f%% |" % (
        len(p_rows), sum(1 for r in p_rows if r[3]), 100.0 * sum(1 for r in p_rows if r[3]) / len(p_rows)))
    lines.append("| **合计** | **%d** | **%d** | **%.1f%%** |" % (
        total, hit, 100.0 * hit / total))
    lines.append("")
    if hit < total:
        lines.append("## 未命中用例")
        lines.append("")
        for skill, query, expect, got in [(m[0], m[1], m[2], m[3]) for m in rows if not m[3]]:
            lines.append("- [%s] %s → 期望 %s，实际命中 %s" % (
                skill, query, expect, "、".join(got) if got else "（无）"))
        lines.append("")
    lines.append("口径：查询经技能自带 tokenize + 同义词 + 反向关键词匹配后，期望的树/坑位出现在"
                 "命中列表（任意排名）即为命中。")
    with open(DOC, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("已写入 %s" % os.path.relpath(DOC, ROOT))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="知识检索评测")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="评测（<100%% 退出码 1）")
    group.add_argument("--doc", action="store_true", help="评测并写 benchmarks/knowledge-recall.md")
    args = parser.parse_args()
    rows, hit, total, miss = evaluate()
    print("检索评测：%d/%d 命中（%.1f%%）" % (hit, total, 100.0 * hit / total))
    for skill, query, expect, got in miss:
        print("  未命中 [%s] %s → 期望 %s，实际 %s" % (
            skill, query, expect, "、".join(got) if got else "（无）"))
    if args.doc:
        write_doc(rows, hit, total)
    return 0 if hit == total else 1


if __name__ == "__main__":
    sys.exit(main())
