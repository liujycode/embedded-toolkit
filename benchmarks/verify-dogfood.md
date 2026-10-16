# 寄存器核验器：真实代码试跑记录

日期：2026-10-16 ｜ 版本：embedded-register-verify（各小节标注：v1.2.0 → v1.5.0） ｜ 环境：Windows，本机 SVD（工程自带 / 厂商 SDK / 芯片包）

> 说明：本文件记录**真实代码**上的试跑与误报观察（本地语料，原代码不进仓库）。
> 合成芯片上的召回率与误报率量化（225 处注入、55 个正样本）见 `benchmarks/verify-recall.md`。

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

## 未完成事项（下一步）

- 触发评测：`tests/trigger/embedded-register-verify.json`（22 正 + 10 反）全量进行中，结果记入 `benchmarks/trigger-results.md`；
- Trae CN / WorkBuddy：IDE 内人工触发验证（用例已就绪）；
- 其它厂商真实语料：ESP-IDF v4.4.7 与 TI TivaWare 已补（见上节）；跨厂商 SVD 冒烟见 `benchmarks/vendor-svds.md`；
  其余厂商（NXP/Renesas/Microchip 等）的**代码**语料与正样本集建设待补。
