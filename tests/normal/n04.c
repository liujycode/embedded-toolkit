/* 自动生成：核验器正样本集（n04）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

#define UART_BAUD_VALUE 0x0683UL

void n04(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;
    USART2->CR1 |= USART_CR1_UE;
    while ((USART2->SR & USART_SR_TXE) == 0) { }
    USART2->BRR = UART_BAUD_VALUE;
}
