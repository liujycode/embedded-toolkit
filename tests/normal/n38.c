/* 自动生成：核验器正样本集（n38）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

#define UART_BAUD_VALUE 0x0683UL

void n38(void)
{
    USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;
    USART1->BRR = UART_BAUD_VALUE;
}
