# 寄存器核验器：真实代码试跑记录

日期：2026-10-16 ｜ 版本：embedded-register-verify（各小节标注：v1.2.0 → v1.8.0） ｜ 环境：Windows，本机 SVD（工程自带 / 厂商 SDK / 芯片包）

> 说明：本文件记录**真实代码**上的试跑与误报观察（本地语料，原代码不进仓库）。
> 合成芯片上的召回率与误报率量化（225 处注入、55 个正样本）见 `benchmarks/verify-recall.md`。
>
> **v1.8.0 起计数口径**：局部变量/指针成员访问（如 `p->len = 0`、`base->C1 = x`）不是寄存器写入，
> 静默忽略且**不再计入"写入/通过"**；"写入"只统计能对应到外设/地址/寄存名的写入。v1.8.0 之前的
> 各节旧数字按当时口径保留。

## 试跑结果（v1.2.0）

| 语料 | 规模 | 报 | 未判定 | 通过 | 备注 |
|---|---|---|---|---|---|
| G431 FOC 工程 4 个项目 `Core/Src`（CubeMX/HAL 风格） | 60 文件 | **0** | 8 | 8 | 未判定均为 `SCB->CPACR`/`SCB->VTOR`（内核寄存器，SVD 不完整） |
| 同上手写驱动（`foc/bsp`、`foc_20k/bsp`、`test/User`） | 33 文件 | **0** | 0 | 127 | 直接寄存器写为主 |
| Nordic `nrfx/hal`（SDK 内嵌头文件，对照 nrf52840.svd） | 38 文件 | 12（2.88%） | 17 | 388 | 归类见下 |
| Nordic `nrfx/drivers/src`（SDK 驱动源码） | 36 文件 | 10（4.12%） | 4 | 229 | 全部为 E08 硬编码地址（厂商写未文档化寄存器的合法用法） |
| 合成夹具 `tests/fixtures/verify_bad.c` | 1 文件 | 12 | 3 | 5 | 覆盖 E01–E10 全部规则 |
| 合成夹具 `tests/fixtures/verify_ok.c` | 1 文件 | 0 | 0 | 5 | 正样本 |

- **应用级真实代码合计：93 个文件、270 处写入、0 报**（G431 四个工程 + 手写驱动）。
- Nordic SDK 内嵌头文件 12 条“报”的归类（均为“规则设计如此”或“数据版本差”，非工具误判）：
  1. 5 条来自 `nrf_adc.h`：该头文件是 nRF51 的 ADC 外设，nRF52840 无此外设 → E01 正确检出“跨芯片使用”；
  2. 4 条来自 SVD 与头文件版本差：`QDEC.PSELA/PSELB/PSELLED`、`COMP.ISOURCE`（头文件有、旧版 SVD 未收录）；
  3. 3 条为硬编码地址（E08，规则设计如此）：`0x4000C504`（TEMP 未文档化寄存器）、`0x400005F0/F4`。
- Nordic SDK 驱动源码 10 条“报”全部是 E08 硬编码地址（`CLOCK`/`NFCT`/`SAADC`/`SPIM` 的
  未文档化寄存器地址，SDK 内部合法用法）——按规则设计提示“建议改用外设结构体或宏”，属预期行为。

## ESP-IDF v4.4.7 真实源码试跑（`--headers`，v1.5.0）

日期：2026-10-16 ｜ 语料：esp-idf **v4.4.7** 的 ESP32-S3 相关源码 14 个文件（GitHub 原始文件，本地语料不进仓库）
+ 本机 PlatformIO `framework-arduinoespressif32`（arduino-esp32 2.0.17）的 3 个 core 文件，
合计 **17 个文件**；SVD 与头文件均取同代本机数据（`tools/ide-debug/svd/esp32s3.svd`、
`tools/sdk/esp32s3/include/soc/esp32s3/include/soc`，头部共 125 个文件 / 4.62 MB）。

| 指标 | 不带 `--headers` | 带 `--headers` |
|---|---|---|
| 写入处 | 332 | 332 |
| 报 | 0 | **0（0.00%）** |
| 未判定 | 224 | **34** |
| 通过 | 108 | **298** |

- `--headers` 把 **190 处**从“未判定”升级为“已核验”（占原未判定的 84.8%），报保持 0——
  即真实 IDF 代码在配套 SVD 下**全量零误报**。
- 剩余 34 处“未判定”全部归因（非工具问题）：
  1. **19 处**来自 `esp_timer_impl_lac.c`（LACT 为 H2/C6 专用外设，esp32s3 头文件中没有这些宏，
     该文件本就不会为 S3 编译）；
  2. **2 处** `RTC_RESET_CAUSE_REG`：宏定义在 `esp_rom/include/esp32s3/rom/rtc.h`（不在给定的 `soc` 目录；
     多加一个 `--headers` 目录即可解析）；
  3. **7 处**射频/模拟域别名地址（`BBPD_CTRL`、`NRXPD_CTRL`、`FE_GEN_CTRL` 等）：SVD 中本就没有这些地址；
  4. **6 处**数值标识符无法映射（如 `UINT32_MAX`，由标准头提供而非寄存器宏）。
- 单文件亮点：`rtc_time.c` 15/15 通过（含 `TIMG_RTCCALICFG_REG(0)` 这类**函数式寄存器宏**链式求值）、
  `driver/uart.c` 47/47、`driver/rmt.c` 30/30、`bootloader_random_esp32s3.c` 31/31。
- **v1.7.0 复测（`#include` 自动跟随）**：`--headers` 指向**整个 include 根**（2225 个头文件，
  按 include 闭包优先加载 241 个）时结果与精确 `soc` 目录**完全一致**（0 / 34 / 298）——
  不再需要手点目录，也不会被大目录的加载上限截断误伤关键宏。
- **v1.8.0 复测（计数口径修正后）**：写入 **224**、报 **0**、未判定 34、通过 190——
  与原 332 的差值 108 处为局部结构体/指针成员访问（`p_rmt->tx_data = 0` 这类），
  按新口径不再计入统计；寄存器类写入的通过/未判定构成与上表一致。

本轮为此修掉/新增的解析能力（对全部用户生效）：

1. **单参数函数宏求值**（`#define X(i) (BASE(i) + 0xNN)`）：调用点代入实参递归求值
   （`--headers` 头文件与源文件内的定义都支持），解决 IDF 大量 `*_REG(i)` 形态；
2. **头文件多行续行宏**：`--headers` 收集前先拼接 `\` 续行（原先会漏掉多行宏）；
3. **`REG_SET_FIELD` / `REG_CLR_FIELD` 字段级核验**：字段存在性（E03）、只读（E10）、
   值位宽与枚举（E04/E05）；
4. **位函数宏**：`BIT(n)`、`BIT_MASK(n)`、`_BV(n)`（Arduino/AVR）在数值表达式里直接求值；
5. **字段名容忍匹配**：字段宏与 SVD 位域名存在插入词差异时（`SENS_FORCE_XPD_SAR` →
   SVD `SAR_FORCE_XPD_SAR`、`RTC_CNTL_SDIO_PD_EN` → SVD `SDIO_REG_PD_EN`）按“词集合包含 + 唯一命中”
   放宽匹配——本轮最初跑出的 3 条 E03 全部是这类命名差异（语义正确），修复后归零。

## TI TivaWare 真实源码试跑（v1.6.0）

日期：2026-10-16 ｜ 语料：TI TivaWare（`yuvadm/tiva-c` 镜像）的 TM4C123 相关源码 **24 个文件**
（dk/ek-tm4c123g 板级示例 + `utils/uartstdio.c`、`cpu_usage.c` + `boot_loader/bl_uart.c`、`bl_flash.c`
+ `driverlib/` 11 个驱动 + `usblib/` 2 个文件），头文件 `inc/` 106 个（用 `--headers`），
SVD 为 `TM4C123GH6PM.svd`（跨厂商冒烟同源）。

| 指标 | 数值 |
|---|---|
| 写入处 | 406 |
| 报 | **0（0.00%）** |
| 未判定 | 286 |
| 通过 | 120 |

- 未判定构成（全部归因，非工具问题）：
  1. **257 处** `HWREG(ui32Base + ...)`：driverlib 函数的基址是**运行时参数**，天然无法静态解析
     （与 HAL 调用同类，诚实记未判定）；
  2. **29 处**别名地址不在 SVD：`NVIC_SW_TRIG`（0xE000EF00，SCS 内核区）与 GPIO 数据屏蔽窗口地址
     （TivaWare 的 `GPIO_O_DATA + (pins << 2)` 位屏蔽窗口，SVD 无法表达，如实未判定）。
- 本轮修复（否则会产生 E08 误报）：`HWREG(宏表达式)` 原先只要地址可求值就按"硬编码地址"报 E08；
  但 `HWREG(UART0_BASE + UART_O_CTL)`、`HWREG(FLASH_FMA)` 是**具名地址**写法，现改为按具名地址核验
  （与地址别名宏同口径，不报 E08）——只有纯字面量地址（如 `HWREG(0x40013800)`）才报 E08。
- **v1.7.0 复测（`#include` 自动跟随）**：`--headers` 指向仓库根（源码 + `inc/` 混在一起）时，
  `#include "inc/hw_memmap.h"` 这类相对包含按源文件目录解析（闭包 215 个头文件），
  结果与精确 `inc` 目录一致（0 / 286 / 120）。
- **v1.8.0 复测（计数口径修正 + 头文件寄存器宏按地址核验）**：写入 **363**、报 **0**、未判定 300、通过 63。
  - 差值来自两部分：局部结构体成员（`psInst->iBulkTxState` 等）不再计入（约 53 处）；
    TivaWare 经典直寄存器风格 `SYSCTL_RCGC2_R = ...`、`GPIO_PORTG_DIR_R = ...`（头文件里
    `#define ... (*((volatile uint32_t *)0x400FE108))`）现在能解析地址核验——`blinky.c` 的
    `SYSCTL_RCGC2_R` 命中 `SYSCTL.RCGC2` 通过；`GPIOG` 系列因语料是 DK 板（TM4C123GH6PGE，
    有 GPIOG）而 SVD 是 GH6PM（无 GPIOG）记"未判定"，如实反映器件差异。
- **v1.8.0 新增能力（本节语料驱动）**：地址访问宏扩展到 `HWREGBITW/H/B(x, bit)`；
  指针解引用与前缀 `*` 求值；对象宏值为指针解引用（TI 直寄存器风格）时按地址核验。

## libopencm3 真实源码试跑（v1.8.0）

日期：2026-10-16 ｜ 语料：libopencm3（`libopencm3/libopencm3`）的 STM32F1 驱动 **7 个文件**
（`lib/stm32/f1/`）+ 家族共用驱动 **9 个文件**（`lib/stm32/common/` 的 exti/iwdg/spi/usart/timer/
gpio/crc/dma/adc v1），头文件 `include/libopencm3/stm32/f1` + `stm32/common` + `cm3`（`--headers` 按
家族目录优先），SVD 为 `STM32F103xx.svd`（Keil STM32F1xx_DFP）。

| 指标 | 数值 |
|---|---|
| 写入处 | 366 |
| 报 | **3**（全部为"文件级检查在库代码上的已知限制"，见下） |
| 未判定 | 287 |
| 通过 | 76 |

- libopencm3 风格被完整覆盖：`RCC_APB1ENR |= RCC_APB1ENR_TIM2EN;`（头文件对象宏 = `MMIO32(RCC_BASE + 0x1c)`）、
  `GPIO_ODR(GPIOA) |= x`（函数宏作左值）、`GPIO_BSRR(port) = ...`（多参数函数宏调用点代入）——
  均解析地址后正常核验；`rcc_periph_clock_enable(RCC_ADC1)` / `rcc_enable_rtc_clock()` 被识别为
  时钟使能（E07 不计）。
- 未判定构成（全部归因，非工具问题）：`ADC_CR2(adc)` / `DMA_CCR(dma, channel)` 这类
  **运行时参数**（库函数入参，天然无法静态解析）；F105/107 连接线型号独有的 `FLASH_CR2/KEYR2/SR2`
  等寄存器（语料为跨型号共用驱动，F103 SVD 无这些寄存器）。
- 3 条"报"的构成：2×E07（`adc.c` 的 ADC1、`gpio.c` 的 AFIO：库文件由调用方使能时钟，
  E07 是文件级检查的已知限制，消息中已注明"若在其它文件使能请忽略"，`--no-clock-check` 可关）；
  1×E12（`crc_common_all.c` 的 `CRC_CR |= CRC_CR_RESET`：SVD 把 `CRC.CR` 标为 write-only，
  读改写读回值不可靠——按 SVD 数据如实提示，需查手册）。

## AVR（Arduino 核心）真实源码试跑（v1.8.0）

日期：2026-10-16 ｜ 语料：Arduino AVR 核心 3 个文件（`wiring.c`、`wiring_analog.c`、
`libraries/Wire/src/utility/twi.c`），头文件 `iom328p.h`（avr-libc），SVD 为 ATmega328P
（`felias-fogg/PyAvrOCD` 的 `svd/atmega328p.svd`，Atmel 包同源）。

| 指标 | 不带 `--define` | 带 `F_CPU=16000000` / `TWI_FREQ=100000` |
|---|---|---|
| 写入处 | 33 | 33 |
| 报 | **0** | **0** |
| 未判定 | 2（`F_CPU`/`TWI_FREQ` 构建期宏） | **0** |
| 通过 | 31 | **33（100%）** |

- 覆盖 AVR 经典**裸寄存器名**风格：`SREG = oldSREG;`、`TCCR1B = 0;`、`ADMUX = ...;`、
  `TWBR = ...;`、`TWCR = ...;`——名字与 SVD 中唯一寄存器名匹配即按寄存器核验；
- `UCSR0B` 等 `_SFR_MEM8(...)` 宏：解析地址后按 AVR 数据空间口径（SVD 用 `0x800000+数据地址`）
  自动探测匹配；
- 两条未判定只是 `F_CPU`/`TWI_FREQ` 这类**构建期宏**（用 `--define` 传入即通过），工具行为正确。

## NXP（MCUXpresso / mbed K64F）试跑（v1.8.0；v1.10.0 扩量）

日期：2026-10-16（扩量 2026-10-17）｜ 语料：MCUXpresso SDK 驱动 **23 个文件**
（fsl_uart/gpio/ftm/adc16/dspi/i2c/flexcan/pit/pdb/rtc/sim/pmc/wdog/dac/cmp/dmamux/edma/
sai/sdhc/enet/flexbus + `fsl_clock_config.c`）+ mbed-os K64F 的 `serial_api.c`，
SVD 为 `MK64F12.svd`（cmsis-svd-data）。

| 指标 | 数值 |
|---|---|
| 写入处 | 3 |
| 报 | **0** |
| 未判定 | 1 |
| 通过 | 2 |

- MCUXpresso 驱动绝大多数经 `base->REG = ...`（运行时基址参数）访问寄存器 → 按口径**静默忽略、
  不计入统计**（与 HAL 同类的指针参数风格）；mbed `serial_api.c` 同样如此。
- 可核验的 3 处：`SIM->SOPT1CFG |= ...`、`SIM->SOPT1 = ...`（大写外设名直写，**2 处通过**）；
  `fsl_flexcan.c` 的 `*(volatile uint32_t *)CAN_INIT_RXFIR = 0x0U` 记未判定（宏来自 SDK 头，
  未提供 `--headers` 时地址不可解析）。
- 结论：NXP 生态当前以 HAL/指针参数风格为主，直接寄存器写入少；**0 误报**。

## Renesas RA（FSP）真实源码试跑（v1.10.0）

日期：2026-10-17 ｜ 语料：FSP 源码 8 个文件（bsp_io.c、bsp_irq.c、r_ioport.c、r_sci_uart.c、
r_gpt.c、r_adc.c、r_dac.c、r_spi.c）+ 设备头 `R7FA6M4AF.h`（`--headers`），SVD 为
`R7FA6M4AF.svd`（cmsis-svd-data）。

| 指标 | 数值 |
|---|---|
| 写入处 | 36 |
| 报 | **0** |
| 未判定 | 26 |
| 通过 | 10 |

- 覆盖 Renesas FSP 的写法：`R_ICU->IELSR_b[irq].IR`（`REG_b` 位域视图后缀）、
  `R_ICU->IELSR[i] = v`（数组下标寄存器）、`R_CPSCU->ICUSARC = ~R_CPSCU_ICUSARC_SADMACn_Msk`
  （占位符位域组 `SADMACn` → SADMAC0…7）、`R_GPT0->GTWP` / `R_TSN_CTRL->TSCR`
  （**外设指针宏按地址解析**：`((R_GPT0_Type *) 0x40169000)` → `GPT320`，配设备头后 10 处通过）、
  `R_PFS->PORT[x].PIN[y].PmnPFS`（层级写法 → 未判定）。
- 未判定构成（全部归因）：NVIC 内核外设（10 处）；组/引脚/索引为运行时表达式（IELSR_b[irq]、
  PFS 层级、INTSELR[intselr_num]）；**条件编译块内的型号差异分支**——FSP 一个文件支持整个 RA 家族，
  `R_GPT_ODC`、`R_GPT_GTCLK`、`R_PORGA`、`R_IRDA`、`R_ICU->INTSELR` 均位于 `#if` 特性宏块内。
- 无头文件单跑（仅 SVD）：36 处写入同样 **0 报**（26 → 36 未判定：跨型号分支全部降级为未判定）。

## Microchip SAMD（Arduino SAMD 核心）真实源码试跑（v1.9.0）

日期：2026-10-17 ｜ 语料：ArduinoCore-samd 的 `cores/arduino/` **5 个文件**（wiring_digital.c、
WInterrupts.c、wiring_analog.c、delay.c、wiring_shift.c），SVD 为 `ATSAMD21G18A`（cmsis-svd-data）。

| 指标 | 数值 |
|---|---|
| 写入处 | 49 |
| 报 | **0** |
| 未判定 | 22 |
| 通过 | 27 |

- 覆盖 Microchip SAMD 的 **CMSIS union/数组风格**（全新语法族）：
  `PORT->Group[0].DIRSET.reg = v`、`PORT->Group[0].PINCFG[4].reg`、`SERCOM0->USART.CTRLA.reg`、
  `EIC->CONFIG[0].reg |= v`、`ADC->CTRLB.bit.RESSEL = ...`（`.bit` 后缀按寄存器级核验）、
  `GCLK->CLKCTRL.reg = GCLK_CLKCTRL_CLKEN | ...`（枚举名核验）、
  `TCx->COUNT16.CTRLA.reg`（复合寄存器名）——SVD 中寄存器名带组/引脚后缀（`DIRSET0`、`PINCFG0_4`、
  `CONFIG0`）与点号复合名（`USART.CTRLA`）都能对上。
- 未判定构成（全部归因）：组/引脚号为运行时表达式（`PORT->Group[g_APinDescription[ulPin].ulPort]…`，
  与 TI 运行时基址同类）；`EIC_INTENSET_EXTINT(inMask)` 这类**位域组宏**的编号来自运行参数
  （本轮修掉 2 处 E03 误报——编号是字面量时直接映射 `EXTINT(3)`→`EXTINT3`，否则记未判定）。
- `delay.c`/`wiring_shift.c` 无直接寄存器写入（SysTick 走 CMSIS 函数、移位用端口指针），如实计 0。

## Silicon Labs（Gecko SDK emlib）真实源码试跑（v1.11.0）

日期：2026-10-17 ｜ 语料：Gecko SDK `platform/emlib/src/` **10 个文件**（em_gpio/em_cmu/em_usart/
em_timer/em_adc/em_i2c/em_letimer/em_wdog/em_dac/em_leuart），同一份代码分别对 **3 份 SVD** 核验：
EFM32GG990F1024（Series 0）、EFR32MG12P（Series 1）、EFR32MG21（Series 2）。

| SVD（设备） | 写入 | 报 | 未判定 | 通过 |
|---|---|---|---|---|
| EFM32GG990F1024 | 318 | **0** | 247 | 71 |
| EFR32MG12P132F1024GL125 | 309 | **0** | 218 | 91 |
| EFR32MG21A020F1024IM32 | 309 | **0** | 241 | 68 |

- 覆盖 Silicon Labs 写法：`GPIO->P[3].DOUT`（**端口字母命名** → SVD 的 `PD_DOUT`）、
  `GPIO->P[port].DOUT`（运行时端口号 → 未判定）、`GPIO->CMUROUTE.CLKOUT0ROUTE`
  （**REG.FIELD 直写拆分**：寄存器 + 字段）、`CMU->CALCNT`（Series 2 的 `CMU_S`
  **安全别名后缀**自动映射）、`CMU->HFRCOCTRL`/`USART0->CTRL`/`TIMER0->CMD` 等普通成员写入与字段宏核验。
- 未判定构成（全部归因）：运行时端口号（`P[port]`）；设备家族分支——emlib 一个文件支持 Series 0/1/2，
  `#if defined(...)` 分支里的 `CMU->SYSCLKCTRL`、`GPIO->EM4WUPOL_CLR`、`PRS->CONSUMER_USART0_RX`、
  `HFXO0->CTRL` 等在本型号 SVD 中不存在或命名不同；NVIC/SysTick/CoreDebug 内核外设。
- **Series 2 只读寄存器**：`CMU->CALCNT = ...` 是 Series 1 的写法（Series 2 改为写 `CALCTRL.CALTOP`，
  `CALCNT` 只读、设备头标注 `__IM`）；该写法位于 `#if` 家族分支内 → 按"访问属性类问题 + 条件块"
  记未判定（此前会误报 E10——本轮修掉 2 处）。

## 内容深化（v1.12.0）：位域直写核验、相关寄存器与规则参考

- **位域直写核验**：`.bit.FIELD = v` / `REG_b.FIELD = v` / `REG.FIELD = v` 解析出位域后，值按
  **位域**宽度核验（E04，字段相对）、只读位域直写报 E10；位域名不存在 → 记"未判定"。
  九生态语料复测**零回归**（数字与 v1.11.0 一致：ESP-IDF 224/0/34/190、SAMD 49/0/22/27、
  Silabs MG12P 309/0/218/91、Renesas 36/0/26/10）。
- **相关置位/清位寄存器**：`lookup` 与 `--explain` 自动关联同族视图（SAMD `OUT0` →
  `OUTSET0/OUTCLR0/OUTTGL0`；Silabs `EM4WUPOL` → `EM4WUPOL_SET/_CLR`），回答位操作问题时
  优先建议用它们（避免读改写）；`--explain` 同时内联写/读语义。
- **`references/rules.md` 重写**（56 → 约 220 行）：E01–E12 每条给出判定方式、会报/不会报示例
  （含真实语料出处）、边界与已知限制、复核方法；新增计数口径（静默忽略清单）、条件编译块口径、
  已知限制汇总（文件级 E07、SVD 完整性、内核外设、指针参数风格、SVD 命名差异）。

## 细节深化（v1.13.0）：AVR 地址口径、位域直写枚举、报告汇总

- **AVR 数据空间口径**：SVD 用"0x800000 + 数据地址"（如 `PORTB = 0x800025`）时，低地址自动探测
  ——`_SFR_MEM8(0x25)`、`_SFR_IO8(0x05)`（+`__SFR_OFFSET`）、`*(volatile uint8_t *)0x25` 都核到
  `PORTB.PORTB`（报告注明 SVD 地址）；`_SFR_IO8` 从"静默漏检"改为计入统计（缺 `__SFR_OFFSET`
  记未判定，不猜偏移）；`addr 0x25` 反查同样探测并注明。
- **位域直写枚举核验（E05 扩展）**：`REG.FIELD = v` / `.bit.FIELD = v` / `REG_b.FIELD = v` 值可求值时
  按位域枚举核验；SVD 带 `isDefault` 默认项的位域一律不报（默认项渲染为"（其余值，默认）"）。
- **报告汇总深化**：文本输出汇总行带按类计数（`报 3（E04 2、E10 1）`）与未判定原因分布
  （`未判定分布：条件编译块内 9、运行时值/下标 1`）；JSON `counts` 加 `report_by_class` /
  `undetermined_by_category`。
- **`--headers` 支持分号分隔多目录**（真实工程多 include 路径）；**`irq` 带优先级字节**
  （`NVIC.IPR9 第 1 字节`）。
- 九生态语料复测**零回归**；召回集扩到 **229/229**（新增位域直写 E04/E05、只读位直写 E10 注入）。

## 试跑中发现并修掉的问题

1. **`SCB->CPACR` 误报 E02**（v1.0.0 试跑）：ST 的 SVD 里 `SCB` 只列了部分内核寄存器，
   其它内核寄存器（CPACR 等）会被“寄存器不存在”规则误报。已修正：内核外设（NVIC/SCB/SysTick…）
   的缺失寄存器一律进“未判定”。
2. **`NVIC` 不在内核外设白名单**：不含 NVIC 的 SVD（演示芯片、部分 Nordic 文件）会把
   `NVIC->ISER0` 误报为“外设不存在”。已加入白名单。
3. **宏名 `_Msk` 后缀（驼峰）**：字段宏正则最初只认全大写，`TIM_CR2_MMS_Msk` 这类被漏掉。
   已扩展为“全大写，或带 `_Msk/_Pos` 等后缀的驼峰写法”。
4. **`GPIOA→GPIO` 家族名派生**：CMSIS 的 GPIO 宏前缀是 `GPIO`，最初派生不出。
   已补“去掉末尾单个字母”的家族候选（`GPIOA→GPIO`）。
5. **E07 的桶归属**：文件级时钟检查最初不计入对应写入的“报”桶。已修正为在逐条核验前算好。
6. **只读寄存器重复报**：只读寄存器写入同时触发“寄存器级 E10”和“位域级 E10”。
   已去重（寄存器只读时不再重复报位域）。
7. **Nordic `NRF_` 前缀别名全量误报**（v1.2.0 试跑）：`NRF_USBD->...` 被报 E01
   （`nrfx/hal` 38 个文件 203/417 处，48.68%）。`nrf.h` 约定 `NRF_<外设>` 是实例指针别名，
   已在外设名解析中支持（`NRF_USBD` → `USBD`）；回归用例 `tests/regress/r01-nrf-prefix.c`。
8. **E10 数值只读位域缺口**（建基准时发现）：`SET_BIT(RCC->CR, 0x400)` 这类宏形态的
   数值写入没有检查只读位域（结构体写有）。已补 `_report_readonly_value`
   （含 `MODIFY_REG` 的置位值；清除掩码不算写入），注入集 E10 22/22 全中。
9. **大小写不敏感求值的误匹配**（libopencm3 试跑发现）：`ADC_CR2(adc)` 里的运行时参数 `adc`
   被大小写不敏感地匹配到宏 `ADC`（`ADC_BASE`），解析出**错误地址**并被当成 TIM14 的寄存器。
   已修正：大小写回退只用于全大写名字（宏风格），小写标识符必须精确匹配。
10. **同名头文件解析顺序**（libopencm3 试跑发现）：`libopencm3/stm32/rtc.h` 这类家族分发头
   会引用同名家族头（f0/f1/f2/f4 各有一份 `rtc.h`），原先按字母序选中最小的 f0。
   已修正：同名文件按 `--headers` 给定顺序优先（家族目录放前面即可）。
11. **E06 清位误报**（libopencm3 试跑发现）：`RTC_CRL &= ~RTC_CRL_RSF;` 这类"等硬件置位再清标志"
   的经典写法被"无效清位"误报。已修正：位域描述含 Flag/标志、或名字以 F 结尾的状态位不检查；
   同一寄存器在文件内被读取过（如 `while ((RTC_CRL & RTC_CRL_RSF))`）也不检查。
12. **E07 对 libopencm3 时钟接口不识别**（libopencm3 试跑发现）：
   `rcc_periph_clock_enable(RCC_ADC1)`、`rcc_enable_rtc_clock()` 已识别为时钟使能来源。
13. **局部变量访问计入"通过"**（NXP/libopencm3 试跑发现）：`p->len = 0`、`base->C1 = x`
   这类局部结构体访问原先被计入"通过"，虚增通过数。已修正为静默忽略、不进入统计（见文首口径）。
14. **位域组宏误报 E03**（SAMD 试跑发现）：`EIC_INTENSET_EXTINT(inMask)` 的字段段 `EXTINT`
   在 SVD 中是 `EXTINT0…15` 组，原先报"位域不存在"。已修正：编号为字面量时映射到实例
   （`EXTINT(3)`→`EXTINT3`），编号来自运行参数时记"位域组宏"未判定。
15. **`TCx->COUNT16.CC[tcChannel].reg` 类运行时下标**：链解析支持一层嵌套下标表达式
   （`[g_APinDescription[pin].ulPort]`），无法静态确定组/通道号时记未判定并注明原因。
16. **条件编译块内的型号差异误报**（Renesas 试跑发现）：FSP 一个文件用 `#if` 支持整个 RA 家族，
   `R_GPT_ODC`、`R_ICU->INTSELR`、`R_PORGA`、`R_IRDA` 等在本型号 SVD 中不存在 → 原先误报 E01/E02。
   已修正：写入位于 `#if/#ifdef` 块内且目标不存在时记"未判定"并注明原因；条件块外照常报。
17. **FSP `REG_b` 位域视图后缀**：`R_ICU->IELSR_b[irq].IR` 原先被当成寄存器名 `IELSR_b.IR`（E02）。
   已修正：`REG_b.FIELD` → 寄存器 `REG`；层级前缀（PFS 的 `PORT[x].PIN[y]`）记"未判定"。
18. **外设指针宏不识别**：`#define R_GPT0 ((R_GPT0_Type *) R_GPT0_BASE)` 后的 `R_GPT0->GTWP`
   原先误报 E01。已修正：配 `--headers` 后按基址匹配 SVD 外设（`R_GPT0` → `GPT320`、
   `R_TSN_CTRL` → `TSN`）；字段宏的 `R_`/`NRF_` 前缀同步支持。
19. **FSP 占位符位域组**：`SADMACn_Msk`（`n` 为占位符）原先记"无法映射"。已修正：`n` 占位符
   对应 `SADMAC0…7` 编号组 → 记"位域组宏"未判定（提供设备头时该宏直接按数值解析）。
20. **条件块内的访问属性误报**（Silicon Labs 试跑发现）：`CMU->CALCNT = ...`（Series 1 写法，
   位于 `#if` 家族分支内）在 Series 2 SVD 上因 `CALCNT` 只读而误报 E10。已修正：E10/E12 这类
   **访问属性**问题在条件编译块内一律记"未判定"（属性随型号/配置而异）；块外照常报
   （libopencm3 的 E12 复测不变）。
21. **端口字母命名**（Silicon Labs）：`GPIO->P[3].DOUT` 原先无法对应 SVD 的 `PD_DOUT`。已修正：
   数字端口下标自动补字母候选（`P[3]` → `PD_...`）；运行时端口号记未判定。
22. **`REG.FIELD` 直写拆分**：`GPIO->CMUROUTE.CLKOUT0ROUTE = v` 原先被当作复合寄存器名（报 E02）。
   已修正：精确匹配失败时把最后一段当字段拆出（寄存器存在 + 字段存在 → 正常核验；字段不存在 → 未判定）。
23. **Series 2 `_S` 安全别名**（cmsis-svd-data 约定）：代码写 `GPIO`/`CMU` 而 SVD 里是 `GPIO_S`/`CMU_S`。
   已修正：外设名自动尝试 `_S`/`_NS` 后缀别名。

## 未完成事项（下一步）

- 触发评测：`tests/trigger/embedded-register-verify.json`（22 正 + 10 反）结果见 `benchmarks/trigger-results.md`；
- Trae CN / WorkBuddy：IDE 内人工触发验证（用例已就绪）；
- 其它厂商真实语料：ESP-IDF、TI TivaWare、libopencm3、AVR（Arduino 核心）、NXP（23 文件）、
  Microchip SAMD（Arduino SAMD 核心）、Renesas RA（FSP）、Silicon Labs（Gecko SDK emlib × 3 份 SVD）
  已补（见上）；跨厂商 SVD 冒烟 19 家见 `benchmarks/vendor-svds.md`；Renesas RL78/RX、PIC/8051 的
  直接寄存器代码语料仍待补（MSP430 无可用 SVD，cmsis-svd-data 仅含 MSP432/TM4C）。
