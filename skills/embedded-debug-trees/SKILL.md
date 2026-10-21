---
name: embedded-debug-trees
description: 排查 MCU 硬件/固件故障时使用：程序跑飞、HardFault、死机复位、总线错误；串口/UART/I2C/SPI/CAN 通信不通、超时、乱码；DMA 丢数据、只收一次、数据错位、偶发损坏；RTOS 任务不跑、卡死死锁、中断优先级问题；上电起不来、Bootloader 跳转异常、莫名周期复位；CAN/CAN-FD 通信不通、错误帧、发不出去、bus-off；USB 识别不到/枚举失败/虚拟串口不弹；Flash 写不进/擦除失败/选项字节读保护；RTC 走时不准/掉电重置；LCD 全黑白屏/花屏/触摸；低功耗睡死叫不醒、唤醒后外设异常；FPGA/RTL 综合后数据全零、资源压不下去、跨时钟域撕裂、仿真器假信息、时序违例。十二棵排障决策树、77 个节点，每步先给证据采集动作（回读寄存器/示波器/故障快照）再下判断，附按实战经验排序的高频根因。Use when debugging MCU crashes, bus faults, I2C/SPI/UART failures, DMA data loss, RTOS deadlocks, CAN/CAN-FD failures, USB/Flash/RTC/Display issues, boot failures, low-power wake issues, or FPGA/RTL synthesis mismatches, CDC issues, resource/timing closure and simulator artifacts. 检索不到明说，不编造决策路径。不用于：寄存器事实查询（用 embedded-register-lookup）、寄存器写入核验（用 embedded-register-verify）、配置语义坑（用 embedded-peripheral-pitfalls）、电机行为故障（电机控制域）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。纯知识检索，不执行用户代码。
metadata:
  author: 周衡
  version: "1.3.1"
---

# 嵌入式排障决策树

给 AI 编程助手用的排障知识库：十二棵决策树、77 个节点覆盖嵌入式软件与 FPGA/RTL 最高频的故障面（跑飞/不通/丢数据/卡死/起不来/CAN/USB/Flash/RTC/LCD/低功耗/FPGA-RTL），**每步都要求先取证据再下判断**，杜绝"直接开药"。

## 何时使用

- 代码跑飞 / HardFault / 死机复位
- I2C/SPI/UART 链路不通、超时、乱码
- DMA 丢数据、只收一次、数据错位
- RTOS 任务不跑、偶发死锁、中断优先级坑
- CAN/CAN-FD 通信不通、错误帧、发不出去、bus-off
- USB 识别不到、枚举失败、设备管理器感叹号/错误43、虚拟串口不弹、传输丢字节
- Flash 写不进、整页擦除失败、写完读回旧值、选项字节读保护
- RTC 走时不准、掉电时间重置、备份域丢配置、唤醒定时器
- LCD 全黑全白、花屏、刷新撕裂、触摸坐标偏移
- 上电起不来、卡在时钟配置、Bootloader 跳转后异常
- 低功耗睡死叫不醒、唤醒后外设乱码、进不了停机模式
- FPGA/RTL 综合后数据全零、功能恒定、端口/参数漏接
- FPGA/RTL 资源压不下去（RAM 推断失败、LUT/REG/CLS 资源账）
- FPGA/RTL 跨时钟域撕裂、亚稳态、建立/保持时间违例
- FPGA/RTL 仿真器输出不可信、非阻塞赋值读到旧值、时序收敛与回归归因

## 何时不用

- 想查某寄存器的定义/复位值 → 用 embedded-register-lookup
- 想核验寄存器写入代码对不对 → 用 embedded-register-verify
- 配置语义的坑（上拉/采样时间/CPOL）还没踩到故障 → 用 embedded-peripheral-pitfalls
- 电机不转/抖动/过流等行为故障 → 电机控制领域（另有专家）
- 时序计算 → 用 embedded-timing-calc

## 命令

```bash
python scripts/trees.py search "DMA 丢数据"          # 按症状关键词检索命中决策树节点
python scripts/trees.py search "HardFault CFSR"      # 多关键词 AND 检索
python scripts/trees.py search "乱码" --tree comm    # 限定在某棵树内检索
python scripts/trees.py show hardfault               # 展示整棵决策树
python scripts/trees.py show dma
python scripts/trees.py show comm
python scripts/trees.py show can
python scripts/trees.py show rtos
python scripts/trees.py show boot
python scripts/trees.py show pwr
python scripts/trees.py show usb
python scripts/trees.py show flash
python scripts/trees.py show rtc
python scripts/trees.py show display
python scripts/trees.py show fpga-rtl
python scripts/trees.py list                          # 列出全部决策树
python scripts/trees.py rootcauses hardfault          # 某类故障的高频根因（按实战经验排序）
python scripts/trees.py demo                          # 自检：知识库加载 + 检索探针
```

- 任何命令支持 `--format json`（Agent/脚本处理用）。
- `search` 支持中英文症状词（"死机"“crash"“乱码"“丢帧"），返回命中的节点路径与下一步动作；中文整句也能检索（节点关键词反向匹配 + bigram 兜底）。
- `show` 输出完整决策树（判定分支→证据动作→根因），Markdown 格式可直接贴报告。
- 检索不到就明说 `E_NOT_FOUND`，并列出最接近的节点——**不编造不存在的决策路径**。

## 决策树总目录

| 树 | 覆盖症状 |
|---|---|
| hardfault | 跑飞/总线错误/栈溢出/未定义指令/NOCP/LOCKUP（按 CFSR 分支） |
| comm | I2C/SPI/UART 不通（配置层→时序层→数据流三层）+ 半双工方向切换 |
| dma | 丢数据/只收一次/错位/偶发损坏（含 Cache 一致性、DMAMUX） |
| can | CAN/CAN-FD 通信不通（物理层/位时序/过滤器/发送邮箱/bus-off） |
| rtos | 任务不跑/死锁/优先级反转/FromISR 大坑/时基没跑 |
| boot | 起不来/时钟卡死/向量表偏移/复位源判定/SWD 连不上 |
| pwr | 睡死叫不醒/唤醒后时钟回落/进不了低功耗/调试器影响 |
| usb | 识别不到/枚举失败/描述符/设备管理器感叹号/CDC 驱动/传输丢字节 |
| flash | 写不进/擦除失败/写完读旧值/busy 轮询/中断里擦除卡死/选项字节读保护 |
| rtc | 走时不准/掉电重置/备份域丢配置/LSE 未起振/唤醒定时器/读数跳变 |
| display | 全黑白屏/花屏/刷新撕裂/复位脉宽/触摸坐标偏移 |
| fpga-rtl | 综合后数据全零/参数端口漏接/资源压不下去/RAM 推断失败/CDC 撕裂/仿真器假信息/时序违例/改版回归归因 |

## 覆盖边界（终态）

**十二棵决策树、77 个节点**：hardfault / comm / dma / can / rtos / boot / pwr / usb / flash / rtc / display / fpga-rtl。

**覆盖范围**：程序崩溃与总线错误、串口/SPI/I2C/CAN 链路、DMA、RTOS 调度、上电与启动、低功耗、USB、片上 Flash、RTC、LCD 显示，以及 FPGA/RTL 综合后行为异常、资源推断、跨时钟域、仿真器可信度与时序收敛——每条决策路径都"先采集证据再判断"。

**不覆盖（明确非目标）**：
- 寄存器事实查询（复位值/位定义）→ `embedded-register-lookup`
- 寄存器写入代码核验 → `embedded-register-verify`
- 配置语义的坑（上拉/采样时间/CPOL 等，未踩到故障时）→ `embedded-peripheral-pitfalls`
- 时序/波特率的数值计算 → `embedded-timing-calc`
- 电机控制行为故障（过流/抖动/磁编码器校准）→ 电机控制领域
- 纯 RTL 功能实现/代码生成、协议报文解析实现 → 非排障知识，不在此库
- 芯片选型、板级原理图与 PCB 设计 → 非排障知识，不在此库

未知的故障现象不编造决策路径；检索不到时明说并给出最接近节点。

## 总原则（回答时必须遵守）

1. 先问配置再谈玄学：大多数"诡异问题"是时钟没开/引脚没配/优先级冲突。
2. 每一步要有可观测证据：回读寄存器、示波器、逻辑分析仪。
3. 一次只改一个变量。
4. 区分"配置错"（查本库）与"行为错"（外部器件/电机域另查）。

详细路径见 `references/trees.md`（由 assets/trees.json 自动生成，与检索数据同源）。
