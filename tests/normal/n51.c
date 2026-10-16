/* 自动生成：核验器正样本集（n51）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n51(void)
{
    #define PCLK1_HZ 42000000UL
    #define BAUDRATE 115200UL
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;
    USART2->CR1 |= USART_CR1_UE;
    USART2->BRR = PCLK1_HZ / BAUDRATE;
}
