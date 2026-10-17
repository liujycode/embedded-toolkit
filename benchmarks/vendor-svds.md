# 厂商 SVD 冒烟（跨厂商适配证据）

日期：2026-10-16 ｜ 工具：`tools/vendor_smoke.py` ｜ 环境：Windows，Python 3.12

> 样本来源：`cmsis-svd/cmsis-svd-data`（MIT 许可，本地取样，**原始 SVD 不进仓库**，只记录统计与结论）。
> 每个 SVD 做三件事：lint（质量检查）、查询（字段级）、核验冒烟
> （构造「合法写 / 假字段宏 / 超宽值」片段，期望恰好 **E03 + E04** 两条“报”、其余 0 条）。

| SVD | 设备 | lint 错/警 | 查询 | 核验冒烟 | 备注 |
|---|---|---|---|---|---|
| Atmel__ATSAMD21G18A.svd | ATSAMD21G18A | 0/0 | ok | ✅ |  |
| Cypress__psoc63.svd | psoc63 | 0/0 | ok | ✅ |  |
| Espressif__esp32s3-ulp.svd | ESP32-S3-ULP | 0/0 | ok | ✅ |  |
| Fujitsu__MB9AF10xN.svd | MB9AF10xN | 0/0 | ok | ✅ |  |
| GigaDevice__GD32VF103.svd | GD32VF103 | 0/0 | ok | ✅ |  |
| Holtek__ht32f125x.svd | HT32F125x | 0/0 | ok | ✅ |  |
| Infineon__XMC4700.svd | XMC4700 | 0/0 | ok | ✅ |  |
| NXP__MK64F12.svd | MK64F12 | 0/0 | ok | ✅ |  |
| Nuvoton__M051_Series.svd | M05x_registers | 0/0 | ok | ✅ |  |
| RaspberryPi__rp2040.svd | RP2040 | 0/0 | ok | ✅ |  |
| Renesas__R7FA6M4AF.svd | R7FA6M4AF | 0/0 | ok | ✅ |  |
| SiFive-Community__e310x.svd | FE310 | 3/0 | skip | 跳过 | 寄存器为 RISC-V CSR 小写命名，不符合 CMSIS 大写约定 |
| SiliconLabs__EFM32GG990F1024.svd | EFM32GG990F1024 | 0/0 | ok | ✅ |  |
| SiliconLabs__EFR32MG12P132F1024GL125.svd | EFR32MG12P132F1024GL125 | 0/0 | ok | ✅ |  |
| SiliconLabs__EFR32MG21A020F1024IM32.svd | EFR32MG21A020F1024IM32 | 0/0 | ok | ✅ | cmsis-svd-data 的 Series 2 外设带 `_S` 安全别名后缀（GPIO → GPIO_S），工具自动映射 |
| Spansion__MB9AF10xN.svd | MB9AF10xN | 1/0 | ok | ✅ | `HWWDT.WDG_RIS` 复位值 0xFF 超出 1 位宽——厂商数据可疑，lint 正确报出 |
| TexasInstruments__TM4C123GH6PM.svd | TM4C123GH6PM | 0/0 | ok | ✅ |  |
| Toshiba__M061.svd | M061 | 0/0 | ok | ✅ |  |

合计：**16** 家厂商 SVD，核验冒烟通过 **15**，失败 0，跳过 1（命名约定不符）。

> v1.8.0 追加：AVR `ATmega328P`（`felias-fogg/PyAvrOCD` 的 `svd/atmega328p.svd`，Atmel 包同源）
> 也通过同一套冒烟（lint + 查询 + 基础核验），即 **17 家 / 通过 16**。该 SVD 使用 AVR 数据空间
> 地址口径（`0x800000 + 数据地址`），工具自动探测匹配（见 `benchmarks/verify-dogfood.md` 的 AVR 一节）。

> v1.10.0 追加：Silicon Labs `EFR32MG12P`（Series 1）与 `EFR32MG21`（Series 2）两份 SVD 通过同一套冒烟，
> 合计 **19 家 / 通过 18**；Series 2 的外设带 `_S` 安全别名后缀（GPIO → GPIO_S），工具自动映射。

## 过程中发现并修掉的问题（均在本轮修复）

1. **带下划线的外设名导致字段宏漏报**（Espressif `RTC_CNTL`）：
   `RTC_CNTL_RTC_ULP_CP_TIMER_ZZZ` 这类宏的前缀切分失败（只认第一段 `RTC`），
   假字段宏不进 E03。已修 `_map_macro`：**先试最长的前缀**（`RTC_CNTL` 整体消费）。
   修复后 Espressif 冒烟通过；已加单测（`test_underscore_peripheral_name_macro_mapping`）。
2. **厂商“同址多宽度视图 / 位域别名”被误报为 error**：Renesas PFS 的 32/16/8 位视图
   （`P000PFS` / `P000PFS_HA` / `P000PFS_BY`）、NXP `CRC.CTRL`/`CTRLHU`、
   Atmel RTC 的 MODE 组、Nuvoton/Toshiba 的位域包含关系，都是**常见合法写法**。
   已改为 **info**（新增 `register_view` / `field_alias` 两个码），
   保留“部分重叠（不构成包含）”为 error（夹具已加正反例）。

## 观察与局限

- 16 份样本的 lint 除上述 1 处厂商数据问题外全部 0 error；查询与核验链路全通。
- 取样为每厂商 1 份代表性 SVD，不代表全系列；冒烟只验证解析/查询/基础核验链路，
  不覆盖各家的字段宏命名习惯差异（E03 用通用 `P_R_ZZZ` 形式构造）。
- SiFive FE310（RISC-V CSR 命名）不在 CMSIS 命名映射的适用范围内——查询可用
  `--svd` 手工指定，但“宏映射”类核验（E03）不适用，属预期边界。
