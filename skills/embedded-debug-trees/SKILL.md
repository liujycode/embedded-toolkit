---
name: embedded-debug-trees
description: 嵌入式排障决策树库：HardFault/通信不通/DMA异常/RTOS卡死/启动失败/低功耗唤醒 六棵完整决策树，按症状关键词检索，每步带证据采集动作和高频根因排行。Use when debugging MCU crashes, bus faults, I2C/SPI/UART failures, DMA data loss, RTOS deadlocks, boot failures or low-power wake issues. 关键词：排障、调试、HardFault、死机、跑飞、I2C不通、DMA丢数据、RTOS死锁、低功耗、唤醒、debug decision tree。不用于：寄存器事实查询（用 embedded-register-lookup）、寄存器写入核验（用 embedded-register-verify）、电机行为故障（电机不转/抖动属电机控制域）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。纯知识检索，不执行用户代码。
metadata:
  author: liujycode
  version: "1.1.0"
---

# 嵌入式排障决策树

给 AI 编程助手用的排障知识库：六棵决策树覆盖嵌入式软件最高频的故障面（跑飞/不通/丢数据/卡死/起不来/低功耗），**每步都要求先取证据再下判断**，杜绝"直接开药"。

## 何时使用

- 代码跑飞 / HardFault / 死机复位
- I2C/SPI/UART 链路不通、超时、乱码
- DMA 丢数据、只收一次、数据错位
- RTOS 任务不跑、偶发死锁、中断优先级坑
- 上电起不来、卡在时钟配置、Bootloader 跳转后异常
- 低功耗睡死叫不醒、唤醒后外设乱码、进不了停机模式

## 何时不用

- 想查某寄存器的定义/复位值 → 用 embedded-register-lookup
- 想核验寄存器写入代码对不对 → 用 embedded-register-verify
- 配置语义的坑（上拉/采样时间/CPOL）还没踩到故障 → 用 embedded-peripheral-pitfalls
- 电机不转/抖动/过流等行为故障 → 电机控制领域（另有专家）
- 时序计算 → 另有 timing-calc（规划中）

## 命令

```bash
python scripts/trees.py search "DMA 丢数据"          # 按症状关键词检索命中决策树节点
python scripts/trees.py search "HardFault CFSR"      # 多关键词 AND 检索
python scripts/trees.py search "乱码" --tree comm    # 限定在某棵树内检索
python scripts/trees.py show hardfault               # 展示整棵决策树
python scripts/trees.py show dma
python scripts/trees.py show comm
python scripts/trees.py show rtos
python scripts/trees.py show boot
python scripts/trees.py show pwr
python scripts/trees.py list                          # 列出全部决策树
python scripts/trees.py rootcauses hardfault          # 某类故障的高频根因（按实战经验排序）
python scripts/trees.py demo                          # 自检：知识库加载 + 检索探针
```

- 任何命令支持 `--format json`（Agent/脚本处理用）。
- `search` 支持中英文症状词（"死机"“crash"“乱码"“丢帧"），返回命中的节点路径与下一步动作；中文整句也能检索（节点关键词反向匹配）。
- `show` 输出完整决策树（判定分支→证据动作→根因），Markdown 格式可直接贴报告。
- 检索不到就明说 `E_NOT_FOUND`，并列出最接近的节点——**不编造不存在的决策路径**。

## 决策树总目录

| 树 | 覆盖症状 |
|---|---|
| hardfault | 跑飞/总线错误/栈溢出/未定义指令/NOCP/LOCKUP（按 CFSR 分支） |
| comm | I2C/SPI/UART 不通（配置层→时序层→数据流三层）+ 半双工方向切换 |
| dma | 丢数据/只收一次/错位/偶发损坏（含 Cache 一致性、DMAMUX） |
| rtos | 任务不跑/死锁/优先级反转/FromISR 大坑/时基没跑 |
| boot | 起不来/时钟卡死/向量表偏移/复位源判定/SWD 连不上 |
| pwr | 睡死叫不醒/唤醒后时钟回落/进不了低功耗/调试器影响 |

## 总原则（回答时必须遵守）

1. 先问配置再谈玄学：大多数"诡异问题"是时钟没开/引脚没配/优先级冲突。
2. 每一步要有可观测证据：回读寄存器、示波器、逻辑分析仪。
3. 一次只改一个变量。
4. 区分"配置错"（查本库）与"行为错"（外部器件/电机域另查）。

详细路径见 `references/trees.md`（由 assets/trees.json 自动生成，与检索数据同源）。
