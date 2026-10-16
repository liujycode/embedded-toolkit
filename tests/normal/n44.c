/* 自动生成：核验器正样本集（n44）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n44(void)
{
    USART1->CR1 |= USART_CR1_M0;
    CLEAR_BIT(USART1->CR1, USART_CR1_M0);
}
