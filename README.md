# 嵌入式开发工具箱（embedded-toolkit）

[![ci](https://github.com/liujycode/embedded-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/liujycode/embedded-toolkit/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/liujycode/embedded-toolkit?label=release)](https://github.com/liujycode/embedded-toolkit/releases)
[![license](https://img.shields.io/github/license/liujycode/embedded-toolkit)](LICENSE)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](#设计约束)

> Evidence-first embedded dev skills for AI coding agents — register lookup from CMSIS-SVD, offline, every answer cites its source.

给 AI 编程助手用的嵌入式技能包。原则：**AI 负责写得快，工具箱负责验得对**。所有结论离线计算，并带上出处和证据标签，不靠模型凭记忆回答寄存器细节。

## 当前内容

| 技能 | 版本 | 状态 | 说明 |
|---|---|---|---|
| `embedded-register-lookup`（寄存器百事通） | 1.3.0 | 本地测试与真机触发评测通过（见 `benchmarks/trigger-results.md`） | 基于 CMSIS SVD 查外设、寄存器、位域、复位值、中断号；地址反查；寄存器值解码与写入值计算；位域速查与位图；CMSIS 风格宏生成；双芯片寄存器对比；地址区间、SVD 元信息与质量检查；本机芯片清单与环境体检；Markdown 表格输出 |

计划中（按阶段门推进，见总方案）：寄存器核验器、接线排障、时序计算器、原理图审查官。

## 安装

> 状态：GitHub 源码已公开。真机触发评测第二轮完成：全量 20 正 + 10 反，Claude Code 30/30、OpenCode 30/30（见 `benchmarks/trigger-results.md`）；Trae CN / WorkBuddy / Codex / Cursor 待测。

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

# 中断号与 C 宏
python skills/embedded-register-lookup/scripts/lookup.py irq USART1 --chip STM32G431
python skills/embedded-register-lookup/scripts/lookup.py macros USART1.CR1 --chip STM32G431

# 对比两颗芯片的同一寄存器；体检 SVD 质量
python skills/embedded-register-lookup/scripts/lookup.py diff USART1.CR1 --chip-a STM32F103C8 --chip-b STM32G431
python skills/embedded-register-lookup/scripts/lookup.py lint --chip STM32G431
```

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
