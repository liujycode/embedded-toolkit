/* 核验器正样本（对应 tests/fixtures/synthetic.svd 的 SYNTH32）：应当 0 条"报"。 */
#include "synth32.h"

#define UART_BAUD_VALUE 0x0683UL

void uart_ok_init(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;            /* 先开时钟 */
    USART2->CR1 |= USART_CR1_UE | USART_CR1_TE;
    USART2->BRR = UART_BAUD_VALUE;
    SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, TIM_CR2_MMS_ENABLE);
}
