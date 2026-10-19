---
name: embedded-peripheral-pitfalls
description: 配置 MCU 外设前对照避坑清单，或排查"配置看起来都对但就是不工作"：RCC 时钟使能与顺序、GPIO 复用/开漏/上拉/5V 兼容、EXTI 与 NVIC 中断（标志清除/优先级分组）、定时器（ARR/PSC/PWM 频率/死区）、ADC（采样时间/校准/序列）、UART 波特率、I2C（上拉/时钟拉伸/地址）、SPI（CPOL/CPHA/片选/溢出）、CAN（位时序/过滤器/终端电阻）、低功耗（唤醒/待机）、看门狗（喂狗/窗口/调试冻结）。十一类外设 61 个实战坑，每坑=症状+对策，含配置口诀。Use when configuring MCU peripherals, checking init code, or troubleshooting peripheral misconfiguration. 与 verify 分工：verify 查寄存器写入合法性，本库查配置语义陷阱。不用于：故障已发生要定位根因（用 embedded-debug-trees）、寄存器事实查询（用 embedded-register-lookup）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。纯知识检索，不执行用户代码。
metadata:
  author: liujycode
  version: "1.1.0"
---

# 嵌入式外设配置坑清单

给 AI 编程助手用的配置避坑知识库：十一类外设的实战坑位，**每个坑=症状+对策**，配置类问题先对清单再回答，命中直接给解法不从头推导。

## 何时使用

- 配置某个外设前，先查有没有已知坑
- 初始化代码写完，对照坑清单自查
- "配置看起来都对但就是不工作"——按坑清单逐项排查
- AI 生成代码的配置复查（与 embedded-register-verify 互补：verify 查寄存器写入合法性，本库查配置语义陷阱）

## 何时不用

- 故障已发生要定位根因 → 用 embedded-debug-trees（决策树）
- 查寄存器定义/复位值 → 用 embedded-register-lookup
- 电机专属配置（相电流注入采样/死区与 SVPWM 配合）→ 电机控制域
- 纯代码生成 → 代码生成类工具

## 命令

```bash
python scripts/pitfalls.py search "I2C 上拉"            # 按外设/症状关键词检索
python scripts/pitfalls.py search "SPI CPOL"            # 检索特定配置项
python scripts/pitfalls.py search "唤醒" --category pwr  # 限定在某类别内检索
python scripts/pitfalls.py show i2c                     # 展示某外设全部坑位
python scripts/pitfalls.py show adc
python scripts/pitfalls.py list                          # 列出全部外设类别
python scripts/pitfalls.py rule                          # 输出通用配置口诀
python scripts/pitfalls.py demo                          # 自检：加载 + 检索探针
```

- 任何命令支持 `--format json`（Agent/脚本处理用）。
- `search` 支持中英文（"上拉"“开漏"“采样时间"“cache"），中文整句也能检索（节点关键词反向匹配），返回坑位与对策。
- `show` 输出某外设的完整坑表（Markdown 表格，可直接贴报告）。
- `rule` 输出配置口诀："使能时钟 → 配 GPIO → 配外设 → 配中断/NVIC → 使能外设"，顺序不能乱。
- 检索不到明说 `E_NOT_FOUND`——不编造坑位。

## 覆盖的外设类别

RCC/时钟、GPIO、EXTI/NVIC 中断、定时器、ADC、USART、I2C、SPI、CAN/FDCAN、低功耗 PWR、看门狗 IWDG/WWDG。

## 与姊妹技能的分工

| 场景 | 用谁 |
|---|---|
| 写配置代码前自查坑 | 本技能 |
| 故障已发生，定位根因 | embedded-debug-trees |
| 查寄存器事实 | embedded-register-lookup |
| 核验寄存器写入合法性 | embedded-register-verify |

详细坑表见 `references/pitfalls.md`（由 assets/pitfalls.json 自动生成，与检索数据同源）。
