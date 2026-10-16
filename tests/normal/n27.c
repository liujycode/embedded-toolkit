/* 自动生成：核验器正样本集（n27）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n27(void)
{
    EXTI->PR = EXTI_PR_P0;
    NVIC_SetPriorityGrouping(3);
    NVIC_EnableIRQ(USART1_IRQn);
}
