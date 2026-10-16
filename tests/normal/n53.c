/* 自动生成：核验器正样本集（n53）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n53(void)
{
    GPIOA->ODR = 0x000000FF;
    GPIOB->ODR = 0x0000FF00;
    SET_BIT(GPIOC->ODR, GPIO_ODR_OD0);
    GPIOC->ODR |= 0x00000100;
}
