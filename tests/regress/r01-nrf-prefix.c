/* 回归用例 r01：Nordic SDK 的 NRF_ 前缀外设别名。
   来源：nRF5 SDK nrfx/hal 头文件试跑（2026-10-16）。
   当时误报：E01「外设 NRF_USBD 在 nrfSVD 中不存在」等，38 个文件 203/417 处（48.68%）。
   修复：外设名解析支持 NRF_ 前缀（nrf.h 约定 NRF_USBD → USBD）。
   此文件是等价最小复现（对 tests/fixtures/synthetic.svd）；预期 0 条“报”。 */
#include "synth32.h"

void r01_nrf_prefix(void)
{
    NRF_USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;   /* NRF_ 别名 → USART1 */
    NRF_USART1->BRR = 0x00000683;
}
