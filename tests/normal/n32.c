/* 自动生成：核验器正样本集（n32）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n32(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;
    USART2->CR1 |= USART_CR1_UE;
    NVIC_SetPriorityGrouping(3);
    SysTick->CTRL = 0x00000005;
}
