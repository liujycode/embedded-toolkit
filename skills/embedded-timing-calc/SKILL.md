---
name: embedded-timing-calc
description: 嵌入式时序计算器：凡问"该填多少/是多少/选多大/误差多少/几位分辨率/多久"的具体数字，先跑本工具算，不要心算——UART 波特率与 BRR、定时器 PWM 分频（PSC/ARR 互算）、I2C 上拉电阻、CAN 位时序与采样点、ADC 源阻抗、RC 滤波、SPI 分频、采样定理、I2C 总线耗时、死区占比，以及 USB 48M 时钟链、传感器 LSB、RTC 走时、电池续航、Modbus 帧间隔、Flash 擦写寿命、WS2812/舵机/步进、看门狗、PLL/分压/NTC，外加 FPGA 专属（UART 分频误差、时序 slack 与 Fmax、PWM 位深）。一次算出并回显公式、判定合法性与依据，全离线。Use when any concrete number is asked - UART BRR, timer prescaler, I2C pull-up resistor, CAN bit timing, ADC source impedance, RC filter cutoff, SPI divider, USB 48MHz clock chain, sensor LSB, RTC drift, battery life, flash wear, Modbus frame gap, WS2812/servo/stepper, FPGA clock divider or timing slack. 关键词：波特率计算、该填多少、分频、上拉电阻选多大、采样点、位时序、源阻抗、截止频率、slack、USB 48M、传感器 LSB、RTC 走时、电池续航、Modbus、Flash 寿命、WS2812、舵机、步进、timing calc。不用于：排障决策（用 embedded-debug-trees）、配置坑查询（用 embedded-peripheral-pitfalls）、寄存器事实（用 embedded-register-lookup）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。纯计算，不执行用户代码。
metadata:
  author: liujycode
  version: "1.1.1"
---

# 嵌入式时序计算器

给 AI 编程助手用的一次到位时序计算：**输入参数 → 结果 + 公式回显 + 合法性判定（带依据）**，翻手册加手算加验算的十分钟压成十秒，错了直接说为什么错。

## 何时使用

- 配 UART：主频/波特率 → BRR、实际波特率、误差判定（<2% 才可用）
- 配定时器 PWM：PCLK 与目标频率 ↔ PSC/ARR 互算（反向给多组推荐）
- 配 I2C：总线电容/速率等级 → 上拉电阻上下限与推荐值（std/fast/Fm+ 同用 Rp_max=tr/(0.8473×Cb)；**Hs-mode 为电流源上拉，本工具不支持、抛 E_UNSUPPORTED**，需按 UM10204 Hs-mode 章节人工核对）
- 配 CAN：位时钟与波特率 → TQ 段分配、采样点位置（检查 75-87.5%）
- 配 ADC 前端：采样周期/精度 → 最大源阻抗；RC 抗混叠截止频率
- 配 SPI：分频表与实际频率
- USB/RTC/续航/寿命：USB 48M 推导链、RTC 日走时、电池续航、Flash 擦写寿命、Modbus 3.5 字符、WS2812/舵机/步进、看门狗超时、PLL/分压/NTC
- 传感器链路：采样定理检查（fs vs 信号带宽）、I2C 总线传输耗时、LSB 换算
- FPGA：UART 整数分频误差、静态时序 slack 与 Fmax、PWM 位深
- 功率级：死区时间占开关周期比（电机深水区提示转电机专家）

## 何时不用

- 故障已发生要定位根因 → embedded-debug-trees
- 配置为什么错的坑位解释 → embedded-peripheral-pitfalls
- 查寄存器定义/复位值 → embedded-register-lookup
- 核验寄存器写入代码 → embedded-register-verify

## 命令

```bash
python scripts/timing.py uart --pclk 72000000 --baud 115200
python scripts/timing.py uart --pclk 72000000 --baud 921600 --os 8
python scripts/timing.py timer --pclk 72000000 --freq 1000        # 反向：推荐 PSC/ARR
python scripts/timing.py timer --pclk 72000000 --psc 71 --arr 999 # 正向：算频率
python scripts/timing.py i2c-rp --bus fast --cb 100               # 上拉电阻（pF）
python scripts/timing.py can-bit --clk 42000000 --baud 500000 --sp 87.5
python scripts/timing.py adc-rad --ts 47 --fadc 42000000 --nbits 12
python scripts/timing.py rc --r 1000 --c 100e-9                   # 截止频率
python scripts/timing.py rc --fc 1590 --c 100e-9                  # 反推电阻
python scripts/timing.py spi --fclk 84000000 --div 8
python scripts/timing.py nyquist --fs 1000 --fbw 100              # 采样定理检查
python scripts/timing.py i2c-time --bus std --bytes 6
python scripts/timing.py deadtime --fsw 20000 --dt 500e-9
python scripts/timing.py fpga-uart --clk 50000000 --baud 115200
python scripts/timing.py fpga-slack --tclk 10 --tco 2.5 --tlogic 3.2 --troute 3.1 --tsu 0.8
python scripts/timing.py fpga-pwm --clk 50000000 --fpwm 20000
python scripts/timing.py wdg --clk 40000 --presc 256 --reload 625
python scripts/timing.py pll --clkin 8000000 --m 4 --n 80 --p 2
python scripts/timing.py divider --vin 12 --vout 3.3
python scripts/timing.py ntc --r25 10000 --beta 3950 --temp 50
python scripts/timing.py rc-settle --r 10000 --c 100e-9 --nbits 10
python scripts/timing.py ppm --base 8000000 --ppm 20
python scripts/timing.py fpga-i2c --clk 50 --clk-div 250 --rate 100000
python scripts/timing.py fpga-debounce --clk 50000000 --ms 20
python scripts/timing.py fpga-cdc
python scripts/timing.py fpga-fifo --tx-bps 115200 --read-bps 230400 --burst 64 --depth 128
python scripts/timing.py list
python scripts/timing.py demo                                     # 自检：已知答案回归
```

- 全部计算器统一输出：**结果 → 公式 → 判定 → 依据**；不合法直接说超限原因。
- 判定阈值（波特率误差 2%、CAN 采样点 75-87.5%、I2C 上升时间等）与来源见 `assets/thresholds.json`，每条带 source 字段。
- 公式与推导见 `references/formulas.md`。
- `--format json` 输出结构化结果给 Agent 解析。

## 覆盖面（37 个计算器）

| 类别 | 计算器 |
|---|---|
| MCU 串口/时钟 | uart、timer、spi、spi-time（传输耗时）、pll（VCO 窗判定）、ppm（晶振漂移对波特率影响）、usb-clk（48M 推导链）、esp32-clk（APB 80M）、rp2040-uart（IBRD 16 位+FBRD 6 位）、rc-settle（建立时间） |
| 总线/协议 | i2c-rp、i2c-time、can-bit、modbus-silence（3.5 字符帧间隔）、serial-baud（模块默认波特率速查） |
| 模拟前端/传感器 | adc-rad、rc、rc-settle（建立时间）、nyquist、divider（分压电阻 E24 推荐）、ntc（Beta 公式测温）、sensor-lsb（分辨率换算）、pwm-dim（调光分辨率）、ws2812（高/低电平脉宽检查） |
| 功率级/机电 | deadtime（电机深水区转电机专家）、servo（舵机脉宽↔角度）、stepper（步进脉宽/转速） |
| 防护/寿命 | wdg（看门狗超时+喂狗纪律）、flash-wear（擦写寿命+页轮换）、battery（续航估算 8 折） |
| 时钟精度 | rtc-drift（32.768k 晶振日走时）、ppm |
| FPGA | fpga-uart、fpga-slack、fpga-pwm、fpga-i2c（行为级 SCL）、fpga-debounce（消抖）、fpga-cdc（跨时钟域检查单）、fpga-fifo（溢出检查） |

## 真实场景示例（一条命令出全答案）

```bash
# 板子 42M 时钟跑 CAN 500k，位时序怎么配？
python scripts/timing.py can-bit --clk 42000000 --baud 500000 --sp 87.5
# 传感器 12V 供电采 ADC，分压到 3.3V 电阻怎么选？
python scripts/timing.py divider --vin 12 --vout 3.3
# NTC 10k B3950 在 50°C 阻值多少（配分压采样）？
python scripts/timing.py ntc --r25 10000 --beta 3950 --temp 50
```
