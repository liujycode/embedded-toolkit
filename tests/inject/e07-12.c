/* 自动生成：核验器注入集（规则 E07，用例 e07-12）。
   预期触发一次 E07；ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e07_12(void)
{
    __HAL_RCC_USART1_CLK_ENABLE();
    USART2->CR1 |= USART_CR1_UE;
}
