/* 用内置演示芯片核验：python scripts/verify.py check examples/verify_demo.c --demo
   期望：报 3（E03 一行、E10 两行），其余通过——合成数据，仅用于演示。 */
#include "etk_demo.h"

void demo_init(void)
{
    USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;   /* 通过 */
    USART1->CR1 |= USART_CR1_XXX;                 /* E03：位域不存在 */
    USART1->CR1 = 0x00000000;                     /* 芯片默认：等于复位值 */
    USART1->SR = 0x00000020;                      /* E10：SR 只读 */
    GPIOA->MODER = 0x00000005;                    /* 通过 */
    TIM1->CNT = 0x00000001;                       /* E10：CNT 只读 */
    EXTI->PR = 0x00000001;                        /* 通过（写 1 清零语义） */
    TIM1->CR1 |= TIM1_CR1_CEN;                    /* 通过 */
}
