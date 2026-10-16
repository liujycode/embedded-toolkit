# 嵌入式开发工具箱（embedded-toolkit）

[![ci](https://github.com/liujycode/embedded-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/liujycode/embedded-toolkit/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/liujycode/embedded-toolkit?label=release)](https://github.com/liujycode/embedded-toolkit/releases)
[![license](https://img.shields.io/github/license/liujycode/embedded-toolkit)](LICENSE)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](#设计约束)

> Evidence-first embedded dev skills for AI coding agents — register lookup & code verification from CMSIS-SVD, offline, every answer cites its source.

给 AI 编程助手用的嵌入式技能包。原则：**AI 负责写得快，工具箱负责验得对**。所有结论离线计算，并带上出处和证据标签，不靠模型凭记忆回答寄存器细节。

## 当前内容

| 技能 | 版本 | 状态 | 说明 |
|---|---|---|---|
| `embedded-register-lookup`（寄存器百事通） | 1.7.0 | 本地测试与真机触发评测通过（见 `benchmarks/trigger-results.md`）；厂商 SVD 冒烟 16 家（见 `benchmarks/vendor-svds.md`） | 基于 CMSIS SVD 查外设、寄存器、位域、复位值、中断号与 NVIC 使能位；解码 / 写值计算 / 读改写陷阱提示；宏生成；双芯片与外设级对比；SVD 质量检查（**识别厂商常见的多宽度视图/位域别名，不再误报**）；环境体检；**SDK 自带 SVD 自动发现（PlatformIO / Arduino15 / ESP-IDF / Pico SDK，覆盖 ESP32 系列与 RP2040）**；**裸寄存器名直接查（AVR/MSP430 风格 `lookup UCSR0B`，重名时列候选）**；Markdown 输出；解析缓存 |
| `embedded-register-verify`（寄存器核验器） | 1.9.0 | 注入集召回 225/225=100%（合成芯片，见 `benchmarks/verify-recall.md`）；正样本 55 文件 0 误报；真实源码 0 误报：ESP-IDF v4.4.7（224 处写入）、TI TivaWare（363 处）、libopencm3 STM32F1（366 处，3 处为文件级时钟检查在库代码上的已知限制）、AVR Arduino 核心（33 处）、Microchip SAMD 核心（49 处）与 NXP 试跑（见 `benchmarks/verify-dogfood.md`） | 核验 C/C++ 代码里的寄存器写入：外设/寄存器/位域存在性、值超宽、枚举合法性、只读位、时钟使能、硬编码地址、中断分组、**使能后写 DMA 配置寄存器（E11）**、**只写寄存器读改写（E12）**；**覆盖多种写法**：`.cpp/.hpp/.ino`、CMSIS 结构体、地址别名宏、HWREG/HWREGBIT/`MMIO32`/`REG32`/`_SFR_MEM8` 地址访问宏、指针表达式写入、函数宏作左值（`GPIO_ODR(GPIOA) \|= x`）、**裸寄存器名（AVR/MSP430 风格 `PORTB = 0xFF`）**、**CMSIS union/数组风格（`PORT->Group[0].DIRSET.reg`、`SERCOM0->USART.CTRLA.reg`）**、TI 直寄存器宏（`SYSCTL_RCGC2_R`，指针别名按地址核验）、`NRF_`/`R_` 厂商别名、通道名同义写法（`DMA1_Channel3`↔`DMA1_CH3`↔SVD 后缀 `CCR3`）、ESP-IDF `REG_WRITE/REG_SET_FIELD`（配 `--headers`，**`#include` 自动跟随**、多参数函数宏、`BIT(n)`）；报/未判定/通过分桶 + 复查清单；**每条问题带 `next` 查证命令与 `--explain` 内联寄存器定义（与百事通闭环）**；目录与 git diff 模式；不执行代码 |

计划中（按阶段门推进，见总方案）：接线排障、时序计算器、原理图审查官。

## 适配范围（跨厂商、跨工具链、跨写法）

| 维度 | 覆盖 |
|---|---|
| 芯片 / 厂商 | 任何有 CMSIS SVD 的芯片：ST、GigaDevice、Nordic、NXP、Renesas、Microchip 等（Keil / cpackget 设备包）；**ESP32 系列、RP2040 由 SDK 自带 SVD 自动发现** |
| SVD 来源 | `--svd` 指定 / 项目内扫描（深度 ≤6）/ 环境变量 `ETK_SVD_DIR` / 本机 CMSIS-Pack 缓存（含多平台路径）/ PlatformIO、Arduino15、ESP-IDF、Pico SDK 自带 SVD |
| 工具链 / 环境 | Keil MDK、STM32CubeMX、PlatformIO、ESP-IDF、Arduino、Zephyr、nRF Connect SDK 的目录结构；Windows / macOS / Linux；Python 3.9+，零依赖、离线 |
| 代码写法（核验器） | CMSIS 结构体写（`USART1->CR1`）、CMSIS 宏（`SET_BIT/MODIFY_REG`）、厂商别名（`NRF_USBD`、`R_PORT0`）、地址别名宏（`#define REG (*(volatile uint32_t *)0x...)`）、`HWREG`（TI 风格）、C/C++ 与 Arduino（`.cpp/.hpp/.ino`）；ESP-IDF 风格寄存器宏明确记"未判定" |

## 安装

> 状态：GitHub 源码已公开。两个 P0 技能就位（查询 + 核验）。触发评测第三轮完成：核验器首轮全量 22 正 + 10 反（Claude Code 29/32、OpenCode 31/32）、百事通扩量 35 正 + 10 反（Claude Code 39/45、OpenCode 41/45）；首跑合计 140/154 = 90.9%，漏报与边界如实记录，见 `benchmarks/trigger-results.md`。Trae CN / WorkBuddy / Codex / Cursor 待人工。

**Claude Code（插件市场）**

```
/plugin marketplace add liujycode/embedded-toolkit
/plugin install embedded-toolkit@embedded-toolkit
```

**其他 Agent（Agent Skills 标准）**：`npx skills add liujycode/embedded-toolkit`，或把 `skills/embedded-register-lookup/` 整个文件夹复制到该 Agent 的技能目录（如 `.agents/skills/`、`.trae/skills/`），或导入对应技能页。

## 快速上手

```bash
# 零配置试一下（内置合成演示芯片，不需要装任何 SVD）
python skills/embedded-register-lookup/scripts/lookup.py fields GPIOA.MODER --demo
python skills/embedded-register-lookup/scripts/lookup.py doctor          # 本机 SVD 从哪来、有没有
python skills/embedded-register-lookup/scripts/lookup.py devices --filter STM32  # 本机有哪些芯片可用

# 芯片名：会在本机 CMSIS-Pack / 项目目录中自动查找 SVD（Keil Pack Installer 安装的包）
python skills/embedded-register-lookup/scripts/lookup.py lookup USART1.CR1.UE --chip STM32G431

# 没有 Pack 时，直接给 SVD 文件
python skills/embedded-register-lookup/scripts/lookup.py addr 0x4001380C --svd ./STM32G431xx.svd

# 按位解码寄存器值
python skills/embedded-register-lookup/scripts/lookup.py decode RCC.CR 0x00040002 --chip STM32G431

# 位域速查（掩码、复位、枚举）与位图
python skills/embedded-register-lookup/scripts/lookup.py fields TIM1.CR1 --chip STM32G431
python skills/embedded-register-lookup/scripts/lookup.py diagram TIM1.CR1 --chip STM32G431

# 算寄存器写入值（值可以用枚举名）
python skills/embedded-register-lookup/scripts/lookup.py set TIM1.CR1 CEN=1 DIR=UP --chip STM32G431

# 中断号与 C 宏（自动带 NVIC 使能位）
python skills/embedded-register-lookup/scripts/lookup.py irq USART1 --chip STM32G431
python skills/embedded-register-lookup/scripts/lookup.py macros USART1.CR1 --chip STM32G431

# 对比两颗芯片：单个寄存器全字段，或整个外设（升级 Pack、移植代码）
python skills/embedded-register-lookup/scripts/lookup.py diff USART1.CR1 --chip-a STM32F103C8 --chip-b STM32G431
python skills/embedded-register-lookup/scripts/lookup.py diff USART1 --chip-a STM32F103C8 --chip-b STM32G431

# 体检 SVD 质量
python skills/embedded-register-lookup/scripts/lookup.py lint --chip STM32G431
```

```bash
# 寄存器核验器：查 C 代码里的寄存器写入对不对（AI 生成代码 / 新驱动 / git diff）
python skills/embedded-register-verify/scripts/verify.py check Core/Src --chip STM32G431
python skills/embedded-register-verify/scripts/verify.py check main.c --chip STM32G431 --checklist
python skills/embedded-register-verify/scripts/verify.py check --patch changes.diff --chip STM32G431
python skills/embedded-register-verify/scripts/verify.py check examples/verify_demo.c --demo   # 零配置试用
```

核验输出分三桶：**报**（E01–E11，附行号/类别/建议）、**未判定**（HAL 调用、内核外设等范围外内容，如实说明）、**通过**；退出码 1 表示检出问题。

## 两个技能怎么配合（查 → 写 → 验）

两个技能共用同一份 SVD 与查找/缓存规则，一次安装、一套数据，跑成闭环：

1. **查**：写代码前用 `embedded-register-lookup` 拿事实（位域、掩码、复位值、枚举、写读语义）。
2. **验**：写完（尤其 AI 生成）用 `embedded-register-verify` 核验；报告分"报/未判定/通过"。
3. **闭环**：每条"报"都带 `next` 字段——可直接执行的百事通命令（如 `lookup USART1.CR1`、
   `addr 0x40013800`，已带本次 `--svd/--chip/--demo` 参数）；`--explain` 还能把寄存器定义直接内联进报告。
4. 修复后用同一条命令复验。

```bash
# 验：发现 USART1.CR1 的位域宏写错，报告里直接给出下一步
python skills/embedded-register-verify/scripts/verify.py check main.c --chip STM32G431
#   [报] E03 第 42 行：宏 USART_CR1_XXX 对应的位域 XXX 在 USART1.CR1 中不存在
#       下一步：embedded-register-lookup lookup USART1.CR1 --chip STM32G431

# 查：按 next 里的提示打开寄存器实况（或直接用 verify --explain 内联）
python skills/embedded-register-lookup/scripts/lookup.py lookup USART1.CR1 --chip STM32G431
```

解析结果会缓存在本机（`%LOCALAPPDATA%\etk\cache` 或 `~/.cache/etk`），重复查询更快，
SVD 文件改动后自动失效；`ETK_NO_CACHE=1` 可关闭。

每个项目可在根目录放 `.etk/config.json`，省去重复参数：

```json
{ "chip": "STM32G431RB", "svd": "tools/svd/STM32G431xx.svd" }
```

项目目录里的 `.svd` 会被自动扫描（深度 ≤ 6）；也可以用环境变量 `ETK_SVD_DIR` 指向自备 SVD 目录。

输出格式：默认中文文本；`--format json` 输出统一信封，供 Agent 解析；`--format md` 输出 Markdown 表格，可直接粘贴进文档或聊天；`--out 文件` 保存结果。

## 设计约束

- **零运行时依赖**：只使用 Python 3.9+ 标准库，无需 `pip install`。
- **离线**：不联网，不调用任何外部 API。
- **只读**：不修改用户项目文件，写出只发生在 `--out` 指定的路径。
- **不执行被检查的代码**：核验器只做词法分析，不 `eval`、不运行用户代码（仓库质量门会检查）。
- **解析缓存**：解析结果缓存在本机（按文件大小与纳秒级修改时间失效），缓存故障静默降级；`ETK_NO_CACHE=1` 关闭。
- **不内置厂商文件**：SVD 由用户本机的 CMSIS-Pack 或自备文件提供；另附一份自行编写的合成演示数据（`--demo`，不是真实芯片），仅用于零配置试用。
- **每条结论有出处**：`source` 字段给出文件、设备、版本；`label` 给出证据等级。

## 开发

```bash
python -m pip install -r requirements-dev.txt

python tools/sync_core.py          # 把 shared/etk_core 同步到各技能（技能必须自带核心库）
python tools/check_repo.py         # 仓库质量门：同步、SKILL.md 规范、3.9 语法、仅标准库
python -m pytest -q                # 单元与集成测试

# 真实厂商 SVD 测试（可选）：指向本机已有的 .svd 目录，多个目录用系统路径分隔符连接
ETK_TEST_SVD_DIR=/path/to/svd-dir python -m pytest tests/test_real_svd.py
```

目录结构：

```
shared/etk_core/          共享核心源码（唯一来源）
skills/<技能名>/          每个技能一个文件夹，内含 SKILL.md、scripts/（含 etk_core 副本）、references/
tools/                    同步与质量检查工具
tests/                    单元测试、合成夹具、触发评测用例（tests/trigger/）
benchmarks/               真实样本核对记录与基准数据
.claude-plugin/           Claude Code 插件与市场清单
```

修改 `shared/etk_core` 后，务必运行 `python tools/sync_core.py`，否则质量门会失败。

## 限制

- SVD 质量由厂商决定。发现错误时，以手册为准，并在 issue 中反馈。
- 目前已在 ST（STM32G431）、Nordic（nRF52840）、GigaDevice（GD32F3x0）三家的 SVD 上完成逐项对照验证；其他厂商待补。
- 不覆盖引脚复用（AF 表）、时钟树、手册勘误、外挂器件命令。

## 许可

MIT。厂商 SVD 文件的版权归原厂商所有，本仓库不包含这些文件。
