/* 自动生成：核验器正样本集（n03）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

#define UART_BAUD_VALUE 0x0683UL

void n03(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;
    SET_BIT(USART2->CR1, USART_CR1_UE);
    MODIFY_REG(USART2->CR1, USART_CR1_TE, USART_CR1_TE);
    USART2->BRR |= UART_BAUD_VALUE;
}
