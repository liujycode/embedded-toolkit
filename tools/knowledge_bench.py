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
    ("CAN 总线完全没应答，波形都量不到", "can"),
    ("CAN 通信时好时坏，怀疑位时序采样点", "can"),
    ("过滤器开了之后就收不到目标报文", "can"),
    ("CAN 报发送失败，一直发送超时", "can"),
    ("总线上一直插入错误帧，最后进 bus-off", "can"),
    ("CAN-FD 的收发器 STB 待机脚电平不对", "can"),
    ("两端波特率不一样，一上高速就出错，采样点也不对", "can"),
    ("一直在总线上插错误帧，错误计数 TEC 偏高", "can"),
    ("进了 bus-off 之后怎么恢复，要不要手动重进初始化", "can"),
    ("总线两端要不要各接一个 120 欧终端电阻，收发器 STB 脚电平怎么量", "can"),
    ("我想只收某一个 ID 的报文，其它都滤掉，过滤器掩码怎么配", "can"),
    ("发送邮箱满了没清，后续报文一直发不出去，是不是发送超时", "can"),
    ("插上电脑识别不到设备，先量 48Mhz 时钟有没有", "usb"),
    ("设备管理器一直报 错误43，枚举老失败卡在描述符", "usb"),
    ("插上之后根本不弹设备也没反应，识别不到，查 DP 上拉和软断开", "usb"),
    ("枚举卡在描述符请求那一步，设备管理器显示未知设备", "usb"),
    ("设备管理器里没有虚拟串口，是不是 CDC 驱动没装", "usb"),
    ("传输偶发丢字节，怀疑 PMA 缓冲对齐不对", "usb"),
    ("往 flash 写数据写不进去，写完读回来还是旧值", "flash"),
    ("整页擦除失败，擦完读回来数据还在", "flash"),
    ("写完马上读是旧数据，是不是没轮询 busy 标志", "flash"),
    ("在中断里做页擦除程序卡死，还有看门狗复位", "flash"),
    ("配了选项字节读保护后 SWD 连不上，flash 也读不出来", "flash"),
    ("先解锁再写但顺序不对，写不生效", "flash"),
    ("RTC 走时不准，一天差出好几秒", "rtc"),
    ("掉电再上电时间就重置回出厂，是不是没判首次上电标志直接跑了初始化", "rtc"),
    ("备份域一掉电配置就丢，写保护链路没走完", "rtc"),
    ("RTC 走时快慢不定，怀疑 LSE 32.768k 没起振", "rtc"),
    ("RTC 唤醒定时器没到点就醒，闹钟周期不对", "rtc"),
    ("读时间老是跳变，读数不对，是不是没做同步握手", "rtc"),
    ("屏幕全黑不亮，先查背光", "display"),
    ("屏幕全白没画面，背光是亮的", "display"),
    ("复位后第一次显示就花屏，颜色发怪", "display"),
    ("刷新时画面上下撕裂，想加 TE 双缓冲", "display"),
    ("触摸坐标偏了，点的地方和显示位置对不上，怎么校准", "display"),
    ("复位脚脉宽不够，屏偶尔不亮，上电序列要先查", "display"),
    ("USART 收发老丢字节，最后一个字节总丢，方向切换时机对不对", "comm"),
    ("DMA 请求使能没开，配置都对就是不搬", "dma"),
    # FPGA/RTL：综合后行为异常 / 资源 / CDC / 仿真器 / 时序收敛
    ("FPGA 综合后数据全零", "fpga-rtl"),
    ("跨时钟域 亚稳态", "fpga-rtl"),
    ("FPGA 资源压不下去", "fpga-rtl"),
    ("仿真器 打出的结果 不可信", "fpga-rtl"),
    ("非阻塞赋值 读到旧值", "fpga-rtl"),
    ("综合工具 警告 端口 漏接", "fpga-rtl"),
    ("存储数组 复位 导致 RAM 推断失败", "fpga-rtl"),
    ("时序违例 建立时间 不满足", "fpga-rtl"),
    # 排序回归：CLI 与评测共用 rank_hits，此查询必须排第 1
    ("USB 识别不到", "usb"),
]

# (查询, 期望坑位 id)
PITFALL_CASES = [
    ("QSPI flash 内存映射读出来全是 FF 怎么排查？", "fl-qspi-xip"),
    ("XIP 模式下要更新 QSPI flash 里的数据要注意什么坑", "fl-qspi-xip"),
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
    ("想连续采集但 DMA 只搬一次就停", "dma-circular"),
    ("DMA 乒乓缓冲数据被覆盖撕裂", "dma-ht-tc"),
    ("内存到内存 DMA 拷贝只写了第一个单元", "dma-m2m-inc"),
    ("DMA 传输宽度和指针类型对不上数据错位", "dma-width"),
    ("DMA 突发长度和 FIFO 阈值冲突", "dma-fifo-burst"),
    ("DMA 一直不触发怀疑请求映射选错了", "dma-req"),
    ("高带宽外设 DMA 欠载丢数据", "dma-priority"),
    ("DMA 中断只进一次，标志位没清干净", "dma-flags"),
    ("USB 用 HSI48 做时钟 48MHz 误差大，Windows 一直枚举失败", "usb-hsi48-no-crs"),
    ("USB 热插拔后要软断开重新枚举吗，host 现在识别不到设备", "usb-dp-pullup-soft-disconnect"),
    ("USB 端点0 描述符发送不完整，主机枚举到一半失败", "usb-ep0-descriptor"),
    ("USB 端点缓冲 PMA 对齐不对，收发数据老是错", "usb-pma-buffer-align"),
    ("USB CDC 虚拟串口 Windows 里看不到，设备管理器有感叹号", "usb-cdc-driver"),
    ("USB 插上 VBUS 没反应，是不是供电检测没做", "usb-vbus-power"),
    ("Flash 擦写前没解锁，一直读回旧数据还报 busy", "fl-keyr-bsy"),
    ("在中断里做 Flash 页擦除，系统卡死", "fl-erase-in-isr"),
    ("Flash 写入要对齐半字，我按字节写校验不过", "fl-write-align"),
    ("Flash 擦写时 CPU 取指被暂停，跑在 Flash 里的代码卡顿", "fl-stall-porch"),
    ("改了 Flash 选项字节不生效，是不是要重载", "fl-option-byte-reload"),
    ("RTC 备份域写保护没解开，改时间无效", "rtc-bkp-wpr"),
    ("RTC 每次上电时间都重置，没做首次上电判断", "rtc-first-init"),
    ("RTC 用的 LSE 晶振起振慢，走时不准", "rtc-lse-slow"),
    ("RTC 读日历寄存器总是错乱，没等同步", "rtc-rsf-lock"),
    ("RTC 唤醒定时器周期不对，时钟口径搞错了", "rtc-wake-clock"),
    ("DAC 输出波形爬升很慢，是不是缓冲摆率不够", "dac-buffer-slew"),
    ("DAC 直连高阻负载输出电压被拉低", "dac-load-cap"),
    ("DAC 用 DMA 双通道输出波形错位", "dac-dma-align"),
    ("DAC 输出噪声大，参考基准不稳", "dac-noise-ref"),
    ("CRC 和 PC 工具算的结果对不上，是不是参数没对齐", "crc-param-mismatch"),
    ("CRC 按字访问数据没对齐，结果随访问方式变化", "crc-byte-align"),
    ("硬件 CRC 多项式是固定的，想算自定义多项式怎么办", "crc-fixed-polynomial"),
    ("CRC 连续算几个数据块结果不对，是不是没复位初始值", "crc-reset-state"),
    ("MPU 区域大小 是不是要 2 的幂并且对齐，配置不生效", "mpu-size-align"),
    ("MPU 子区域掩码 SRD 误禁了一部分地址", "mpu-srd"),
    ("MPU 没被 region 覆盖的地址访问异常，背景区域怎么配", "mpu-bgnd"),
    ("MPU 要先配 region 再使能，顺序搞反了", "mpu-enable-order"),
    ("MPU 把数据区设成可执行，CPU 跳进去取指 HardFault", "mpu-xn"),
    ("printf 重定向没做好，串口什么也不输出", "dbg-printf"),
    ("脱机跑就卡死，插上调试器反而正常，是不是 semihosting", "dbg-semihosting"),
    ("SWO 输出全是乱码，波特率对不上", "dbg-swo"),
    ("RTT 看不到输出，控制块缓冲定位错", "dbg-rtt"),
    ("打断点程序行为就变，是不是调试冻结位 DBGMCU", "dbg-dbgmcu"),
    ("跳 Bootloader 后中断进错，向量表偏移 VTOR 没配", "link-vtor"),
    ("启动文件里 栈 和 堆 的大小要跟链接脚本一致，malloc 失败", "link-stack-heap"),
    ("链接时报 .bss 段 溢出 overflow，放不下", "link-overflow"),
    ("把函数放 RAM 段属性里，复位后没被拷贝", "link-ramfunc"),
    ("SystemInit 没被调用，启动时钟没配", "link-sysinit"),
    ("全局变量 初始值不对，启动文件里的 init_array 初始化没跑", "link-init-array"),
    ("以太网 RMII 需要 50MHz 参考时钟，没接 PHY 不工作", "eth-rmii-clock"),
    ("PHY 寄存器地址读不到，返回 ID 不对，怀疑 MDIO 频率", "eth-phy-mdio"),
    ("以太网描述符 cache 一致性没处理，丢包", "eth-desc-cache"),
    ("lwIP 的 pbuf 内存池太小，连接多了丢包", "eth-lwip-mem"),
    ("ping 不通要从链路层开始分层查吗", "eth-ping-layer"),
    ("SD 卡上电初始化时钟要降到 400kHz 以下，CMD0 无响应", "sd-init-clock"),
    ("FatFs 挂载失败，diskio 层实现有问题", "sd-diskio"),
    ("SD 的 DMA 缓冲要对齐块边界，数据错位", "sd-dma-align"),
    ("SD 卡热插拔换卡后要重挂载，写保护没处理", "sd-wp-hotplug"),
    ("SD 卡扇区大小配错 512，读写错位", "sd-sector"),
    ("中断改了共享变量主循环读到的还是旧值，缺 volatile", "c-volatile"),
    ("空循环延时被优化没了，时间完全不对", "c-delay-loop"),
    ("直接用指针强转结构体解析协议字段错位", "c-struct-pack"),
    ("有符号 整数 右移 溢出 是未定义行为 UB，开优化就变怪", "c-ub"),
    ("ISR 和主循环共享位域 并发读写会错乱", "c-bitfield-rw"),
    ("宏 参数没加 括号，展开结果不对", "c-macro-paren"),
    ("函数里开大数组 栈 爆了，进函数就 HardFault", "c-stack-array"),
    ("Modbus RTU 帧间隔按 3.5 字符判定，从站收不到完整报文", "modbus-frame-gap"),
    ("Modbus CRC16 字节序和初值 0xFFFF 对不上，回异常码", "modbus-crc"),
    ("Modbus 主站发请求从站不应答，功能码和从站地址对不上", "modbus-addr-func"),
    ("Modbus 寄存器地址总是差 1 个，0 基 1 基搞混", "modbus-reg-offset"),
    ("Modbus TCP 事务标识 没核对，并发 时响应容易错乱", "modbus-tcp-trid"),
    ("1-Wire 复位时序被中断打断，偶发读不到器件", "sensor-bus-timing"),
    ("DS18B20 转换等 750ms 用 忙等，主循环卡住", "sensor-bus-conv-wait"),
    ("总线上并联多个 1-Wire 器件，要做 SEARCH ROM 搜索序列号", "sensor-bus-search"),
    ("1-Wire 寄生电源供电不足，读数据全是 1", "sensor-bus-power"),
    ("DS18B20 读了温度没做 CRC 校验，偶尔读错", "sensor-bus-crc"),
    ("掉电瞬间数据没保存就复位，是不是没开 PVD 电压监控", "pwr-pvd-bor"),
    ("PVD 掉电抢救 要把中断优先级设最高，快速保存参数", "pwr-pvd-save"),
    ("I2C EEPROM 页写跨页，长数据只写了一半", "i2c-eeprom-page"),
    ("发 AT 指令 收不到回包，解析没超时 直接卡死", "uart-at-timeout"),
    ("AT 模组透传模式退不出，发 +++ 没反应", "uart-at-transparent"),
    ("RTS CTS 硬流控接反了，只发不收", "uart-rtscts"),
    ("PWM 意外关闭，刹车输入 break 没弄对", "tim-braker"),
    ("定时器 用 重复计数 REP 模式，触发更新每 N 次才对", "tim-rep-trig"),
    ("互补输出 死区 时间用 DTG 位算，tDTS 分频怎么取", "tim-deadzone"),
    ("注入组触发和 PWM 没同步，采样到的相电流不对", "adc-inject-trig"),
    ("双 ADC 交替模式主从没配，两片数据不一致", "adc-dual-mode"),
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
        trees.rank_hits(hits)  # 与 CLI cmd_search 同一排序
        got = [(h[1][0] if h[1] else h[2].get("id")) for h in hits]
        rank = got.index(expect) + 1 if expect in got else 0
        rows.append(("debug-trees", query, expect, rank))
        if not rank:
            miss.append(("debug-trees", query, expect, got[:4]))
    for query, expect in PITFALL_CASES:
        terms = pitfalls.tokenize(query)
        hits = pitfalls.search(pdb, terms, raw=query.lower())
        got = [h[2]["id"] for h in hits]
        rank = got.index(expect) + 1 if expect in got else 0
        rows.append(("pitfalls", query, expect, rank))
        if not rank:
            miss.append(("pitfalls", query, expect, got[:4]))
    total = len(rows)
    hit = sum(1 for r in rows if r[3])
    # precision@1 / MRR
    p1 = sum(1 for r in rows if r[3] == 1) / total
    mrr = sum(1.0 / r[3] for r in rows if r[3]) / total
    return rows, hit, total, miss, p1, mrr


def write_doc(rows, hit, total, p1, mrr):
    lines = [
        "# 知识检索评测（embedded-debug-trees / embedded-peripheral-pitfalls）",
        "",
        "用例 = 真实症状/场景查询 + 期望命中的树或坑位（注入式，逐条 ground truth）；",
        "被测实现 = 技能脚本里的检索函数本体（import 复用，测的就是分发代码）。",
        "",
        "| 技能 | 用例 | 命中 | 召回 | p@1 | MRR |",
        "|---|---|---|---|---|---|",
    ]
    t_rows = [r for r in rows if r[0] == "debug-trees"]
    p_rows = [r for r in rows if r[0] == "pitfalls"]

    def _metrics(rs):
        h = sum(1 for r in rs if r[3])
        return (100.0 * h / len(rs),
                100.0 * sum(1 for r in rs if r[3] == 1) / len(rs),
                100.0 * sum(1.0 / r[3] for r in rs if r[3]) / len(rs))

    tr, tp, tm = _metrics(t_rows)
    pr, pp, pm = _metrics(p_rows)
    lines.append("| embedded-debug-trees（按树） | %d | %d | %.1f%% | %.1f%% | %.1f%% |" % (
        len(t_rows), sum(1 for r in t_rows if r[3]), tr, tp, tm))
    lines.append("| embedded-peripheral-pitfalls（按坑位） | %d | %d | %.1f%% | %.1f%% | %.1f%% |" % (
        len(p_rows), sum(1 for r in p_rows if r[3]), pr, pp, pm))
    lines.append("| **合计** | **%d** | **%d** | **%.1f%%** | **%.1f%%** | **%.1f%%** |" % (
        total, hit, 100.0 * hit / total, 100.0 * p1, 100.0 * mrr))
    lines.append("")
    if hit < total:
        lines.append("## 未命中用例")
        lines.append("")
        for m in rows:
            if not m[3]:
                lines.append("- [%s] %s → 期望 %s，实际命中否" % (m[0], m[1], m[2]))
        lines.append("")
    worse = [m for m in rows if m[3] and m[3] > 3]
    worse.sort(key=lambda m: -m[3])
    if worse:
        lines.append("## 期望排名 >3 的用例（p@1/MRR 可改进点）")
        lines.append("")
        lines.append("| 技能 | 用例 | 期望目标 | 排名 |")
        lines.append("|---|---|---|---|")
        for skill, query, expect, rank in worse:
            lines.append("| %s | %s | %s | %d |" % (skill, query, expect, rank))
        lines.append("")
    lines.append("口径：查询经技能自带 tokenize + 同义词 + 反向关键词匹配后，期望的树/坑位出现在"
                 "命中列表即为命中（召回）；排名=期望目标在命中列表的位置（与 CLI search 共用同一排序）；"
                 "p@1=期望目标排第 1 的占比；MRR=期望目标倒数排名的均值。召回 100% 与 p@1≥0.9 为门禁，"
                 "MRR 只报告趋势。")
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
    rows, hit, total, miss, p1, mrr = evaluate()
    if os.environ.get("KB_DEBUG"):
        from collections import Counter
        print("DBG rank dist:", sorted(Counter(r[3] for r in rows).items()))
        print("DBG ROOT:", ROOT)
    print("检索评测：%d/%d 命中（%.1f%%）  p@1=%.1f%%  MRR=%.1f%%"
          % (hit, total, 100.0 * hit / total, 100.0 * p1, 100.0 * mrr))
    for skill, query, expect, got in miss:
        print("  未命中 [%s] %s → 期望 %s，实际 %s" % (
            skill, query, expect, "、".join(got) if got else "（无）"))
    if args.doc:
        write_doc(rows, hit, total, p1, mrr)
    return 0 if hit == total else 1


if __name__ == "__main__":
    sys.exit(main())
