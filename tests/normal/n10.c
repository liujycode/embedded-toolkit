/* 自动生成：核验器正样本集（n10）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n10(void)
{
    SET_BIT(USART3->CR1, USART_CR1_UE);
    USART3->BRR = 0x00000683;
}
