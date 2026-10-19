---
name: embedded-debug-trees
description: 嵌入式排障决策树库：HardFault/通信不通/DMA异常/RTOS卡死/启动失败五棵完整决策树，按症状关键词检索，每步带证据采集动作和高频根因排行。Use when debugging MCU crashes, bus faults, I2C/SPI/UART failures, DMA data loss, RTOS deadlocks or boot failures. 关键词：排障、调试、HardFault、死机、跑飞、I2C不通、DMA丢数据、RTOS死锁、debug decision tree。不用于：寄存器事实查询（用 embedded-register-lookup）、寄存器写入核验（用 embedded-register-verify）、电机行为故障（电机不转/抖动属电机控制域）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。纯知识检索，不执行用户代码。
metadata:
  author: liujycode
  version: "1.0.0"
---

# 嵌入式排障决策树

给 AI 编程助手用的排障知识库：五棵完整决策树覆盖嵌入式软件 80% 的故障面，**每步都要求先取证据再下判断**，杜绝"直接开药"。

## 何时使用

- 代码跑飞 / HardFault / 死机复位
- I2C/SPI/UART 链路不通、超时、乱码
- DMA 丢数据、只收一次、数据错位
- RTOS 任务不跑、偶发死锁、中断优先级坑
- 上电起不来、卡在时钟配置、Bootloader 跳转后异常

## 何时不用

- 想查某寄存器的定义/复位值 → 用 embedded-register-lookup
- 想核验寄存器写入代码对不对 → 用 embedded-register-verify
- 电机不转/抖动/过流等行为故障 → 电机控制领域（另有专家）
- 时序计算 → 另有 timing-calc（规划中）

## 命令

```bash
python scripts/trees.py search "DMA 丢数据"          # 按症状关键词检索命中决策树节点
python scripts/trees.py search "HardFault CFSR"      # 多关键词 AND 检索
python scripts/trees.py show hardfault               # 展示整棵决策树
python scripts/trees.py show dma
python scripts/trees.py show comm
python scripts/trees.py show rtos
python scripts/trees.py show boot
python scripts/trees.py list                          # 列出全部决策树
python scripts/trees.py rootcauses hardfault          # 某类故障的高频根因排行
python scripts/trees.py demo                          # 内置演示：检索与展示自检
```

- `search` 支持中英文症状词（"死机"“crash"“乱码"“丢帧"），返回命中的节点路径与下一步动作。
- `show` 输出完整决策树（判定分支→证据动作→根因），Markdown 格式可直接贴报告。
- 检索不到就明说 `E_NOT_FOUND`，并列出最接近的节点——**不编造不存在的决策路径**。

## 决策树总目录

| 树 | 覆盖症状 |
|---|---|
| hardfault | 跑飞/总线错误/栈溢出/未定义指令（按 CFSR 分支） |
| comm | I2C/SPI/UART 不通（配置层→时序层→数据流三层） |
| dma | 丢数据/只收一次/错位/偶发损坏（含 Cache 一致性） |
| rtos | 任务不跑/死锁/优先级反转/FromISR 大坑 |
| boot | 起不来/时钟卡死/向量表偏移/复位源判定 |

## 总原则（回答时必须遵守）

1. 先问配置再谈玄学：90% 的"诡异问题"是时钟没开/引脚没配/优先级冲突。
2. 每一步要有可观测证据：回读寄存器、示波器、逻辑分析仪。
3. 一次只改一个变量。
4. 区分"配置错"（查本库）与"行为错"（外部器件/电机域另查）。

详细路径见 `references/trees.md`（本库人类可读全量版，与 assets/trees.json 同源）。
