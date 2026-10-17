---
name: embedded-register-verify
description: 核验 C 代码里的 MCU 寄存器写入是否与芯片 SVD 一致：外设、寄存器、位域是否存在；值是否超位宽；枚举是否合法；是否写只读位；是否访问前未开时钟；是否硬编码地址。按"报 / 未判定 / 通过"分桶输出，并可生成复查清单。Use when reviewing embedded C init code, register writes, or AI-generated firmware registers; verify register writes against a chip SVD. 关键词：寄存器核验、寄存器检查、AI 生成代码、驱动复查、初始化代码检查、对拍、register check、verify register writes。不用于：HAL/LL 结构体配置语义（会进未判定）、外挂器件命令（Flash、传感器）、时序正确性、通用代码风格、寄存器事实查询（用 embedded-register-lookup）。
license: MIT
compatibility: 需要 Python 3.9+，仅使用标准库，无需联网。需要目标芯片的 CMSIS SVD 文件（查找规则同 embedded-register-lookup）；没有 SVD 时可用内置演示芯片（--demo）零配置试用。
metadata:
  author: liujycode
  version: "1.16.1"
---

# 寄存器核验器

把一段 C 代码里的寄存器写入逐条对照芯片 SVD 核验：**这条写入合法吗？**每条结论带出处与证据标签。
只做词法分析：**不执行用户代码、不 eval**；判定不确定时进"未判定"，宁可漏报不误报。

## 何时使用

- 复查 AI 生成的初始化代码 / 驱动里的寄存器写入
- 怀疑字段宏拼错、位位置写错、值超位宽、写到只读位
- 检查"用外设前有没有开时钟"、有没有硬编码地址
- 生成复查清单：给同事或上板前逐项确认
- 对 git diff / 补丁里的新增寄存器代码做增量核验

## 何时不用

- HAL/LL 函数与结构体配置语义（不解析，进"未判定"）
- 外挂器件（Flash、传感器）的寄存器命令
- 时序正确性、电气特性（用 embedded-timing-calc 或实测）
- 通用代码风格与内存安全（用代码评审类技能）
- 只想知道某个寄存器的事实（用 embedded-register-lookup）

## 命令

```bash
python scripts/verify.py check main.c --chip STM32G431
python scripts/verify.py check src/ --svd ./STM32G431xx.svd --checklist
python scripts/verify.py check --patch changes.diff --chip STM32G431
python scripts/verify.py check examples/verify_demo.c --demo
python scripts/verify.py check main.c --chip ESP32-S3 --headers "$IDF_PATH/components/soc/esp32s3/include/soc"
python scripts/verify.py rules
```

- `check` 接受文件、目录（递归扫 `.c/.h/.cpp/.cc/.cxx/.hpp/.hh/.hxx/.ino` 等，上限 200 个）或 `--patch`（unified diff 的新增行）。
- **补丁模式**：只核验新增行；若磁盘上有完整文件（按当前目录与补丁所在目录查找），文件级检查
  （E06/E07/E11）用整文件做上下文——未改动的时钟使能/置位可见，不会误报；找不到完整文件时给出
  明确提示（建议在仓库目录内运行或加 `--no-clock-check`）。
- `--define NAME=VALUE` 补充宏定义（可多次，常用于从工程配置里带入的常量）。
- `--headers 文件或目录` 从头文件加载宏定义（可多次）：ESP-IDF 等"寄存器常量宏"风格的代码，
  配合 SVD 可正常核验 `REG_WRITE/REG_SET_BIT/REG_CLR_BIT/REG_SET_FIELD/REG_CLR_FIELD`。
  **被核验文件里的 `#include` 会被自动解析并优先加载**（含嵌套包含链）——一般给项目的 include 根
  或 SDK 的 include 目录即可，不用精确到 `soc`；其余头文件按路径顺序补足（上限 512 个文件 / 8 MB，
  达到上限会明确提示）。个别宏在其它目录（如 `esp_rom` 的 `rom/rtc.h`）时再补一个 `--headers`；
  未提供头文件时这些宏记"未判定"。
- `--no-clock-check` 关闭 E07（跨文件使能时常需要）。
- `--checklist` 按复查要求分组输出：芯片默认 / 已核验 / 需查手册 / 需实测。
- `--explain` 把每条问题对应的**寄存器定义直接内联进报告**（与百事通同一份 SVD）。
- `--format json` 给 Agent 解析；`--out 文件` 保存结果。
- 退出码：0 = 无"报"；1 = 检出问题（`errors` 为空时表示"报告"而不是工具故障）。

## 与寄存器百事通配合（查 → 写 → 验）

两个技能共用同一份 SVD 与同一套查找/缓存规则，配合成闭环：

1. **写代码前**：用 `embedded-register-lookup` 取事实（位域、掩码、复位值、枚举）。
2. **写完 / AI 生成后**：用本技能 `check` 核验。
3. **报告里的每条问题都带 `next`**：给出可直接执行的百事通命令（如 `lookup USART1.CR1`、
   `addr 0x40013800`、`search TIM2`），已经带上本次的 `--svd/--chip/--demo` 选择参数，
   打开就能看寄存器实况。
4. **`--explain`**：不想再跑一条命令时，直接把寄存器定义内联进报告。
5. **修复后**：用同一条 `check` 命令复验。

## 支持与不支持

**支持（L1 写入形态）**

| 形态 | 示例 |
|---|---|
| 直接/复合赋值 | `USART1->CR1 = v;`、`\|=`、`&=`、`^=` |
| CMSIS 宏 | `SET_BIT`、`CLEAR_BIT`、`MODIFY_REG`、`WRITE_REG`（`READ_REG` 跳过） |
| 字段宏（CMSIS 命名） | `USART_CR1_UE`、`GPIO_MODER_MODE0`、`TIM_CR2_MMS_Msk`、枚举名后缀（`USART_CR1_PS_ODD`） |
| 直接地址（报 E08 并反查寄存器名） | `*(volatile uint32_t *)0x40013800 = v;`、`*reinterpret_cast<volatile uint32_t *>(0x40013800) = v;`、`HWREG(0x40013800) = v;`（纯字面量才报 E08） |
| 地址访问宏 | `HWREG/HWREGH/HWREGB`（TI）、位带 `HWREGBITW/H/B(x, bit)`、`MMIO8/16/32`（libopencm3）、`REG8/16/32`（GD32）、`_SFR_MEM8/16/32`（AVR）：宏组合出的具名地址按具名寄存器核验，**不报 E08** |
| 地址别名宏 | `#define REG (*(volatile uint32_t *)0xADDR)` 或 `#define REG MMIO32(基址 + 偏移)`（头文件里的 `--headers` 也算）后的 `REG = v;`（按该寄存器正常核验） |
| 指针表达式写入 | `*(volatile uint32_t *)(外设_BASE + 偏移) = v;`（具名表达式不报 E08；纯字面量表达式报 E08；运行时基址记未判定） |
| 函数宏作左值 | `GPIO_ODR(GPIOA) \|= v`（libopencm3）、`GPIO_OCTL(GPIOA) = v`（GD32）——单/多参数函数宏在调用点代入求值 |
| CMSIS union/数组风格 | `PORT->Group[0].DIRSET.reg = v`、`SERCOM0->USART.CTRLA.reg = v`、`EIC->CONFIG[0].reg \|= v`（Microchip SAMD；组/通道号为运行时表达式时记"未判定"） |
| FSP 位域视图后缀 | `R_ICU->IELSR_b[irq].IR = v`（`REG_b.FIELD` → 寄存器 `REG`；下标为运行时表达式时记"未判定"；层级写法 `PORT[x].PIN[y].PmnPFS` 记"未判定"） |
| 外设指针宏（按地址解析） | `#define R_GPT0 ((R_GPT0_Type *) R_GPT0_BASE)` 后的 `R_GPT0->GTWP = v`：配 `--headers` 提供设备头，按基址匹配 SVD 外设（R_GPT0 → GPT320、R_TSN_CTRL → TSN） |
| 占位符位域组 | `R_CPSCU_ICUSARC_SADMACn_Msk`（FSP 用 `n` 占位编号 → SADMAC0…7 组；编号未指定或来自运行参数时记"未判定"） |
| Silicon Labs 风格 | `GPIO->P[3].DOUT = v`（端口字母命名 → `PD_DOUT`；运行时端口号记"未判定"）、`GPIO->CMUROUTE.CLKOUT0ROUTE = v`（`REG.FIELD` 直写拆分）、Series 2 的 `_S` 安全别名（`GPIO` → `GPIO_S`） |
| 裸寄存器名 | `PORTB = 0xFF;`、`P1OUT \|= BIT0;`、`UCSR0B = (1 << RXEN0)`（AVR/MSP430/8051；与 SVD 中唯一寄存器名匹配才核验） |
| 通道名同义写法 | `DMA1_Channel3->CCR` ↔ `DMA1_CH3->CCR`；SVD 若把通道号放在寄存器后缀（G4 的 `CCR3`），也能对上并做字段级核验 |
| ESP-IDF 风格寄存器宏 | `REG_WRITE/REG_SET_BIT/REG_CLR_BIT/REG_SET_FIELD/REG_CLR_FIELD(...)`：用 `--headers` 提供寄存器常量宏后按具名寄存器核验（`REG_SET_FIELD` 做到**字段级**：存在性/只读/位宽/枚举）；地址求值支持 `BIT(n)` 与函数宏（`TIMG_RTCCALICFG_REG(0)`、`GPIO_ODR(port)`）；`#include` 自动跟随；未提供时记"未判定" |
| 语言/工程 | C 与 C++（`.c/.h/.cpp/.cc/.hpp/.ino` 等），Arduino 工程里的直接寄存器写同样适用 |

**不支持（一律进"未判定"，不当作错误）**：HAL/LL 调用、结构体成员赋值（`hi2c1.Init.X`）、运行时计算的地址、无法映射的字段宏、簇寄存器命名（如 `DMA1_Channel1->CCR` 对应 SVD 里 `DMA1` 的 `CH1` 簇）、内核外设（SysTick/NVIC 等在设备 SVD 之外）。

## 判定口径（E01–E12）

| 编号 | 判定 | 标签 | 严重度 |
|---|---|---|---|
| E01 | 外设不存在于该芯片 | 已核验 | 高 |
| E02 | 寄存器不存在 | 已核验 | 高 |
| E03 | 字段宏对应的位域不存在（或宏属于别的寄存器） | 已核验 | 高 |
| E04 | 值超出寄存器/位域宽度（位域直写按位域宽度） | 已核验 | 高 |
| E05 | 值不是位域的合法枚举（含位域直写；带 isDefault 默认项的位域不报） | 已核验 | 中 |
| E06 | 无效清位（清复位为 0 且本文件未见置位的位） | 需查手册 | 低 |
| E07 | 写入前未见该外设时钟使能 | 需查手册 | 中 |
| E08 | 硬编码地址 | 已核验 | 高 |
| E09 | 中断分组多处设置（`NVIC_SetPriorityGrouping`） | 需查手册 | 中 |
| E10 | 写只读寄存器或位域（含位域直写） | 已核验 | 高 |
| E11 | 使能（EN=1）后写 DMA 计数/地址寄存器（CNDTR/CMAR/CPAR 等） | 需查手册 | 中 |
| E13 | 写 1 清零寄存器上的读改写（`\|=`/`SET_BIT`/`MODIFY_REG` 等；W1C 位未被掩码覆盖时会把已置位标志顺带清零，掩码未知记未判定） | 需查手册 | 中 |
| E12 | 只写寄存器上的读改写（`\|=`/`&=`/`SET_BIT`/`MODIFY_REG`/`REG_SET_FIELD`/`REG_CLR_FIELD`，读回值不可靠） | 需查手册 | 中 |

**条件编译块口径**：目标（外设/寄存器/位域）不存在、或**访问属性类问题（E10/E12）**出现在
`#if/#ifdef` 块内时，记"未判定"并注明原因——厂商库源码常在一个文件里用 `#if` 区分芯片家族/配置
（如 FSP 的 `R_GPT_ODC`、`R_ICU->INTSELR`；Gecko 的 Series 1/2 分支里 `CMU->CALCNT` 在 Series 2
是只读），避免把其它型号的分支误报成错误；条件块**外**照常报 E01/E02/E03/E10/E12。

完整判定细节与示例见 `references/rules.md`；支持形态与限制见 `references/syntax.md`。

## 怎么回答

- 先给结论："共 N 处写入，报 X、未判定 Y、通过 Z"，再列"报"的每条：行号、类别、原因、建议。
- 引用结果里的 `message`/`suggestion`；每条的问题都对应 SVD 中的事实或明确的约定。
- **每条"报"都带 `next`**：把"下一步查证"的百事通命令一并告诉用户（或直接执行），
  需要展开细节时用 `--explain` 内联寄存器定义；不要凭记忆补寄存器事实。
- "未判定"要如实说明为什么没判定（如 HAL 调用不在范围内、簇命名无法对应），不要猜。
- 依据来自哪份 SVD（`source`）要说明。
- 用户要"复查清单"时用 `--checklist`，并说明"需实测"组建议上板验证。

## 限制

- 只认 SVD 里的名字与命名约定，不做完整 C 解析、不跨文件分析；E07 是**文件级**检查（使能在其它文件时请加 `--no-clock-check`）。
- 条件编译分支全部检查，可能与实际编译结果不同。
- 值只能在文件内 `#define`/`--define` 范围内求值；`sizeof`、函数返回值等无法求值 → 未判定。
- 不修改被检查文件；不联网；不执行任何被检查的代码。
