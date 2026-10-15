---
name: embedded-register-lookup
description: 查询 MCU 外设寄存器、位域、复位值和地址（基于 CMSIS SVD），每条结论带出处与证据标签；支持地址反查、寄存器值解码、关键词搜索。Use when the user asks about a register, bit field, reset value, peripheral base address, or wants to decode a register value. 关键词：寄存器、位域、复位值、SVD、外设地址、USART1->CR1、register、bitfield、reset value、decode。不用于：引脚复用、手册章节检索、勘误查询、核对代码中的寄存器写入（用 embedded-register-verify）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。需要目标芯片的 CMSIS SVD 文件：厂商 CMSIS-Pack 或用户自备的 .svd。
metadata:
  author: liujycode
  version: "1.0.1"
---

# 寄存器百事通

按芯片的 SVD 文件查外设、寄存器、位域和复位值，做地址反查与寄存器值解码。每条结论带来源（文件、设备、版本）和证据标签。

## 何时使用

- 问某个外设寄存器的某一位是什么、复位值是多少
- 给一个地址，问它是哪个寄存器
- 给一个寄存器值，按位解码成各字段
- 按关键词查找，例如 "baud"、"DMA 通道"

## 何时不用

- 引脚复用、AF 功能表：SVD 不包含这些信息
- 手册章节、勘误、电气参数
- 检查代码里的寄存器写入是否正确：用 embedded-register-verify
- 写驱动代码、排查接线：用对应技能

## 命令

脚本路径相对于本 SKILL.md 所在目录。

```bash
python scripts/lookup.py lookup USART1.CR1.UE --chip STM32G431
python scripts/lookup.py lookup USART1->CR1 --svd ./STM32G431xx.svd
python scripts/lookup.py addr 0x4001380C --chip STM32G431
python scripts/lookup.py search baud --chip STM32G431
python scripts/lookup.py decode RCC.CR 0x00040002 --chip STM32G431
python scripts/lookup.py list --chip STM32G431
```

- 需要解析结果时加 `--format json`。
- 需要保存给用户时加 `--out 文件名`。
- 查询语法和各子命令的输出字段见 `references/query-syntax.md`。

## SVD 查找顺序

1. `--svd <路径>`
2. 项目根目录 `.etk/config.json` 中的 `svd` 或 `chip` 字段（从当前目录向上查找）
3. 本机 CMSIS-Pack 缓存中按芯片名匹配的 `SVD/*.svd`（Windows 为 `%LOCALAPPDATA%\Arm\Packs`，Linux 和 macOS 为 `~/.arm/Packs`）
4. 都找不到时返回 `E_SVD_NOT_FOUND`，并列出已尝试的位置

找不到 SVD 时，告诉用户两种办法：安装对应芯片的 CMSIS 设备包（Keil Pack Installer 可安装），或用 `--svd` 指定厂商提供的 .svd 文件。不要凭记忆补寄存器定义。

## 怎么回答

- 直接引用结果中的寄存器名、地址、位域位置和复位值。
- 带上 `source` 中的文件名和设备名，让用户知道依据是哪份 SVD。
- 标签为"已核验"时说明依据是 SVD 本身。
- 地址落在保留区或没有寄存器定义时，直接说明"SVD 中未定义"，不要推测用途。
- 结果中有 `warnings` 时，简要告诉用户哪些内容被跳过（如某个位域位置缺失）。

## 限制

- 只查 SVD 中定义的内容。引脚复用、时钟树、手册勘误不在范围内。
- 厂商 SVD 质量参差。发现明显错误时说明"以 SVD 为准，建议对照手册核对"。
- 只读：不修改用户文件，不联网。
- SVD 支持范围与已知缺口见 `references/svd-support.md`。
