/* 自动生成：核验器注入集（规则 E07，用例 e07-21）。
   预期触发一次 E07；ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

#define UART_BAUD_VALUE 0x0683UL

void e07_21(void)
{
    USART2->BRR = UART_BAUD_VALUE;
}
