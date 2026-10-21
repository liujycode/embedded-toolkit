---
name: embedded-peripheral-pitfalls
description: 配置 MCU 外设前对照避坑清单，或排查"配置看起来都对但就是不工作"：RCC 时钟使能与顺序、GPIO 复用/开漏/上拉/5V 兼容、EXTI 与 NVIC 中断（标志清除/优先级分组）、定时器（ARR/PSC/PWM 频率/死区）、ADC（采样时间/校准/序列）、DMA（循环模式/地址自增/宽度/标志清除/请求映射）、UART 波特率、I2C（上拉/时钟拉伸/地址）、SPI（CPOL/CPHA/片选/溢出）、CAN（位时序/过滤器/终端电阻）、低功耗（唤醒/待机）、看门狗（喂狗/窗口/调试冻结）、USB（HSI48 时钟/上拉软断开/端点缓冲对齐/CDC 驱动）、片上 Flash 擦写、RTC（时钟源/写保护/首次上电判定）、DAC/CRC/MPU、调试与链接（semihosting/SWO/DBGMCU/VTOR/栈堆/段溢出）、以太网（RMII 时钟/MDIO/cache/lwIP 内存）、SD 卡、C 代码、Modbus、1-Wire 传感器总线。二十五类外设 148 个实战坑，每坑=症状+对策，含配置口诀。Use when configuring MCU peripherals, checking init code, or troubleshooting peripheral misconfiguration. 与 verify 分工：verify 查寄存器写入合法性，本库查配置语义陷阱。不用于：故障已发生要定位根因（用 embedded-debug-trees）、寄存器事实查询（用 embedded-register-lookup）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。纯知识检索，不执行用户代码。
metadata:
  author: 周衡
  version: "1.2.1"
---

# 嵌入式外设配置坑清单

给 AI 编程助手用的配置避坑知识库：二十五类外设的实战坑位，**每个坑=症状+对策**，配置类问题先对清单再回答，命中直接给解法不从头推导。

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
- `search` 支持中英文（"上拉"“开漏"“采样时间"“cache"），中文整句也能检索（节点关键词反向匹配 + bigram 兜底），返回坑位与对策；命中带"下一步"的坑位会给出姊妹技能命令（如时序用 embedded-timing-calc）。
- `show` 输出某外设的完整坑表（Markdown 表格，可直接贴报告）。
- `rule` 输出配置口诀："使能时钟 → 配 GPIO → 配外设 → 配中断/NVIC → 使能外设"，顺序不能乱。
- 检索不到明说 `E_NOT_FOUND`——不编造坑位。

## 覆盖的外设类别

RCC/时钟、GPIO、EXTI/NVIC 中断、定时器、ADC、DMA、USART、I2C、SPI、CAN/FDCAN、低功耗 PWR、看门狗 IWDG/WWDG、USB、片上 Flash、RTC、DAC、CRC、MPU、调试 DBGMCU/SWO、链接脚本、以太网 ETH、SD/MMC、C 语言、Modbus、1-Wire 传感器总线。

## 覆盖边界（终态）

**二十五类外设 / 148 个坑位**：adc(9) c(7) can(6) crc(4) dac(4) dbg(5) dma(8) eth(5) exti(6) flash(6) gpio(6) i2c(7) link(6) modbus(5) mpu(5) pwr(6) rcc(6) rtc(5) sd(5) sensor-bus(5) spi(5) tim(9) uart(8) usb(6) wdg(4)。

**覆盖范围**：配置语义陷阱（寄存器写对了但外设不工作/结果不对），按"类别 → 症状 → 对策"组织。

**不覆盖（明确非目标）**：
- 故障已发生要定位根因 → `embedded-debug-trees`
- 寄存器事实查询（复位值/位定义）→ `embedded-register-lookup`
- 寄存器写入合法性核验 → `embedded-register-verify`
- 时序/数值计算 → `embedded-timing-calc`
- 电机专属配置本体（相电流采样/死区与 SVPWM/SVPWM 编排）→ 电机控制领域
- 处理器架构/内核机制、编译选项全面 JIT 调优 → 非外设配置语义

未知配置问题不编造坑位；检索不到明说并给出相邻类别。

## 与姊妹技能的分工

| 场景 | 用谁 |
|---|---|
| 写配置代码前自查坑 | 本技能 |
| 故障已发生，定位根因 | embedded-debug-trees |
| 查寄存器事实 | embedded-register-lookup |
| 核验寄存器写入合法性 | embedded-register-verify |

详细坑表见 `references/pitfalls.md`（由 assets/pitfalls.json 自动生成，与检索数据同源）。
