# 真实 SVD 核对记录

本文件记录用于测试的真实厂商 SVD 中、已用原始文本核对过的事实。这些文件不进入仓库，只在本机通过环境变量 `ETK_TEST_SVD_DIR` 提供（多个目录用系统路径分隔符连接）。

核对方法：在原始 XML 中按外设块定位（先找 `<name>外设名</name>`，再在该块内找寄存器），不使用"文件中第一个同名寄存器"的方式。

## STM32G431xx.svd（ST，版本 1.6，CM4）

| 项目 | 核对结果 |
|---|---|
| USART1 基地址 | `0x40013800` |
| USART1.CR1 的 UE 位 | `<bitOffset>0</bitOffset>`，宽 1，描述 "USART enable" |
| USART1.CR1 的 `<size>` | 写作 `0x20`（十六进制） |
| USART2 | `derivedFrom="USART1"`，基地址 `0x40004400` |
| USART3 | `derivedFrom="USART1"`，基地址 `0x40004800` |
| `derivedFrom` 总数 | 22 |
| `dim` 与 `cluster` | 文件中均为 0 |
| `enumeratedValues` | 文件中为 0 |

注意：该文件里第一个 `<name>CR1</name>` 属于 I2C，其中的 PE、TXIE、RXIE、ADDRIE 是 I2C 的位。USART1 的 CR1 字段表包括 RXFFIE、FIFOEN、M1、M0、PS、PCE、TE、RE、UE 等，没有 PE。

## nrf52840.svd（Nordic，版本 1）

| 项目 | 核对结果 |
|---|---|
| UARTE0 基地址 | `0x40002000`，`alternatePeripheral` 为 UART0 |
| `derivedFrom` 总数 | 31（例如 `P0`、`SPI0`、`SPIM0`） |
| `dim` 总数 | 53 |
| `cluster` 总数 | 59 |
| `enumeratedValues` 总数 | 5488 |

## GD32F3x0.svd（GigaDevice，GD32F3x0_DFP 3.0.2）

| 项目 | 核对结果 |
|---|---|
| device 名 | `GD32F3x0` |
| GPIOA 基地址 | `0x48000000`，addressBlock `0x400` |
| `derivedFrom` | 5 处 |
| `dim` / `cluster` / `enumeratedValues` | 均为 0 |
| 文件开头 | `<?xml` 声明前有 2 个空格（厂商文件瑕疵）。解析器已容错并给出警告；测试侧对照解析器同样容错 |

对照测试：41 个外设，其中 36 个（非派生、非数组、非簇）与独立遍历逐项一致；5 个派生的由派生一致性规则覆盖。

## 对照测试结果

- `tests/test_real_svd.py::test_stm32g431_matches_independent_walk`：对照非派生、非数组、非簇的外设，寄存器名、偏移、位宽、复位值、位域位置逐项一致（50 个外设）。
- `tests/test_real_svd.py::test_nrf52840_matches_independent_walk`：同上（13 个外设）。
- `tests/test_real_svd.py::test_gd32f3x0_matches_independent_walk`：同上（36 个外设）。
- 派生外设由 `*_derived_peripherals_mirror_base` 系列覆盖：没有自有寄存器声明的派生外设，其寄存器列表与基础外设一致。
- 运行方法：`ETK_TEST_SVD_DIR=<G431目录><分隔符><nRF目录><分隔符><GD32目录> python -m pytest tests/test_real_svd.py`
