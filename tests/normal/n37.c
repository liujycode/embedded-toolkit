/* 自动生成：核验器正样本集（n37）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n37(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;
    USART2->CR1 |= USART_CR1_UE;
    SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);
    TIM1->CR1 |= TIM_CR1_CEN;
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, TIM_CR2_MMS_ENABLE);
}
