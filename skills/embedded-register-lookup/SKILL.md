---
name: embedded-register-lookup
description: 查询 MCU 外设寄存器、位域、复位值和地址（基于 CMSIS SVD），每条结论带出处与证据标签；支持地址反查、寄存器值解码与写入值计算、位域速查与位图、中断号查询、CMSIS 风格宏生成、跨芯片寄存器对比、地址区间查询、SVD 质量检查、本机芯片清单与环境体检、Markdown 表格输出。Use when the user asks about a register, bit field, reset value, peripheral base address, interrupt number, wants to decode or compute a register value to write, generate register macros, compare register definitions between devices, or find/verify SVD files on the machine. 关键词：寄存器、位域、复位值、SVD、外设地址、寄存器值、掩码、位图、中断号、IRQn、宏定义、对比、质量检查、SVD 位置、芯片清单、USART1->CR1、register、bitfield、mask、reset value、decode、interrupt。不用于：引脚复用、手册章节检索、勘误查询、核对代码中的寄存器写入（用 embedded-register-verify）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。需要目标芯片的 CMSIS SVD 文件：厂商 CMSIS-Pack 或用户自备的 .svd；没有 SVD 时可用内置演示芯片（--demo）零配置试用。
metadata:
  author: liujycode
  version: "1.3.0"
---

# 寄存器百事通

按芯片的 SVD 文件查外设、寄存器、位域和复位值，做地址反查与寄存器值解码。每条结论带来源（文件、设备、版本）和证据标签。

## 何时使用

- 问某个外设寄存器的某一位是什么、复位值是多少
- 给一个地址，问它是哪个寄存器
- 给一个寄存器值，按位解码成各字段；或给位域赋值，算要写入的寄存器值
- 要位域掩码、位图布局或写读语义（如写 1 清零），方便写代码
- 问外设的中断号（如 USART1_IRQn / 中断向量 37）
- 要寄存器或位域的 C 宏定义（CMSIS 风格参考）
- 对比两颗芯片（或两份 SVD 文件）的同一寄存器
- 按关键词查找，例如 "baud"、"DMA 通道"
- 找不到 SVD 文件、不知道本机有哪些芯片可用（用 doctor / devices / --demo）
- 核对 SVD 文件本身：厂商、统计、文件哈希、质量问题（lint）
- 要把查询结果整理成文档或聊天里的表格（--format md）

## 何时不用

- 引脚复用、AF 功能表：SVD 不包含这些信息
- 手册章节、勘误、电气参数
- 检查代码里的寄存器写入是否正确：用 embedded-register-verify
- 写驱动代码、排查接线：用对应技能

## 命令

脚本路径相对于本 SKILL.md 所在目录。

```bash
python scripts/lookup.py lookup USART1.CR1.UE --chip STM32G431
python scripts/lookup.py lookup USART1->CR1 USART1.CR1 --svd ./STM32G431xx.svd
python scripts/lookup.py addr 0x4001380C --chip STM32G431
python scripts/lookup.py search baud --chip STM32G431
python scripts/lookup.py irq USART1 --chip STM32G431
python scripts/lookup.py decode RCC.CR 0x00040002 0x00000100 --chip STM32G431
python scripts/lookup.py decode GPIOA.IDR 0xFFFF --write --chip STM32F103C8
python scripts/lookup.py fields TIM1.CR1 --chip STM32G431
python scripts/lookup.py diagram TIM1.CR1 --chip STM32G431
python scripts/lookup.py set TIM1.CR1 CEN=1 DIR=UP --chip STM32G431
python scripts/lookup.py macros USART1.CR1 --chip STM32G431
python scripts/lookup.py diff USART1.CR1 --chip-a STM32F103C8 --chip-b STM32G431
python scripts/lookup.py range 0x40013800 0x40013FFF --chip STM32G431
python scripts/lookup.py lint --chip STM32G431
python scripts/lookup.py info --chip STM32G431
python scripts/lookup.py list --chip STM32G431
python scripts/lookup.py devices --filter STM32F4
python scripts/lookup.py doctor
python scripts/lookup.py fields GPIOA.MODER --demo
```

- 没有 SVD 时先 `doctor`（各来源与数量）和 `devices`（本机芯片清单）；想立刻体验用 `--demo`（内置合成芯片，不是真实数据）。
- `lookup`、`fields`、`diagram`、`diff` 可一次给多个路径/寄存器（某个失败不影响其它）。
- `set` 的值可以是数字（0x/0b/十进制）或字段的枚举名；默认以复位值为基准，`--from 数字` 可换基准。
- `decode --write` 从写入方视角给提示：只读位域、未定义位、写 1 清零等写读语义。
- `lint` 检查 SVD 质量问题（重叠、越界、重复名、复位值超宽、中断号冲突），可用 `--peripheral` 限定范围。
- `diff` 两侧分别用 `--svd-a/--chip-a`、`--svd-b/--chip-b` 指定。
- 需要解析结果时加 `--format json`；要粘贴进文档或聊天时加 `--format md`（Markdown 表格）。
- 需要保存给用户时加 `--out 文件名`。
- 查询语法和各子命令的输出字段见 `references/query-syntax.md`。

## SVD 查找顺序

1. `--svd <路径>`
2. 项目根目录 `.etk/config.json` 中的 `svd` 或 `chip` 字段（从当前目录向上查找）
3. 项目内扫描：当前目录向下深度 ≤ 6 的 `*.svd`（跳过隐藏目录与依赖目录）；没给 `--chip` 时，唯一的 .svd 会被直接使用
4. 环境变量 `ETK_SVD_DIR` 指向的自备 SVD 目录（多个用系统路径分隔符分开）
5. 本机 Pack 缓存：`%LOCALAPPDATA%\Arm\Packs`（Windows）、`~/.arm/Packs`、`~/.cache/arm/packs`（Linux）、`~/Library/Caches/Arm/Packs`（macOS）
6. 都找不到时返回 `E_SVD_NOT_FOUND`，并列出已尝试的位置；此时建议用户运行 `doctor` 查看具体原因

找不到 SVD 时，告诉用户这几种办法：把 .svd 放进项目目录（会被自动扫描）、安装对应芯片的 CMSIS 设备包（Keil Pack Installer 可安装）、用 `ETK_SVD_DIR` 指向自备 SVD 目录、或用 `--svd` 指定文件。不要凭记忆补寄存器定义。

## 怎么回答

- 直接引用结果中的寄存器名、地址、位域位置和复位值。
- 带上 `source` 中的文件名和设备名，让用户知道依据是哪份 SVD。
- 标签为"已核验"时说明依据是 SVD 本身。
- 地址落在保留区或没有寄存器定义时，直接说明"SVD 中未定义"，不要推测用途。
- `set` 结果里有 `notes`（如只读位域）时，把提醒转告用户。
- `diff` 结论要说明两侧各来自哪份 SVD 文件。
- 结果中有 `warnings` 时，简要告诉用户哪些内容被跳过（如某个位域位置缺失）。

## 限制

- 只查 SVD 中定义的内容。引脚复用、时钟树、手册勘误不在范围内。
- `diff` 要求两侧都能解析到同一路径的寄存器，缺任一侧会报错并注明是 A 还是 B 侧。
- `macros` 生成 CMSIS 风格参考宏，宏名含外设实例名（如 `USART1_CR1_UE_Pos`）；厂商头文件常用外设类型名，对照时注意命名差异。
- 中断名按 SVD 原样输出（ST 的 SVD 里就是 `USART1`，不带 `_IRQn` 后缀）。
- `--demo` 用的是内置合成芯片（ETK-DEMO），只用于试用与演示，绝不能当作真实芯片的依据；输出里会带"合成数据"警告。
- `lint` 只做从 SVD 自身数据可判定的检查（重叠、越界、重复名等），不核对电气参数与手册。
- 厂商 SVD 质量参差。发现明显错误时说明"以 SVD 为准，建议对照手册核对"；也可用 `lint` 给出证据。
- 只读：不修改用户文件，不联网。
- SVD 支持范围与已知缺口见 `references/svd-support.md`。
