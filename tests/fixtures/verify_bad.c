/* 核验器夹具（对应 tests/fixtures/synthetic.svd 的 SYNTH32）：故意混入各类错误。
   期望结果见 tests/test_verify.py；注释里的行号与实际行号一致。 */
#include "synth32.h"

#define UART_BAUD_VALUE 0x0683UL

void uart_bad_init(void)
{
    USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;      /* 通过 */
    USART1->CR1 |= USART_CR1_XXX;                    /* E03：位域 XXX 不存在 */
    USART1->CR1 |= USART_BRR_DIV;                    /* E03：宏属于 BRR，而写的是 CR1 */
    USART1->CR1 |= USART_CR1_PS_EVEEN;               /* E03：PS 后的 EVEEN 不是枚举（拼写错误） */
    USART1->CR1 |= USART_CR1_PS_ODD;                 /* 通过：枚举名后缀 */
    USART1->CR1 = 0x00000000;                        /* 芯片默认：写入等于复位值 */
    USART1->SR = 0x00000020;                         /* E10：SR 是只读寄存器 */
    TIM1->CR1 = 0x1FFFF;                             /* E04：TIM1.CR1 只有 16 位 */
    TIM2->CR1 |= TIM_CR1_CEN;                        /* E01：TIM2 不存在 */
    USART1->CR9 = 0x00000001;                        /* E02：CR9 不存在 */
    *(volatile uint32_t *)0x40013800 = 0x00000001;   /* E08：硬编码地址（= USART1.CR1） */
    USART2->CR1 |= USART_CR1_UE;                     /* E07：未见 USART2EN 时钟使能 */
    CLEAR_BIT(USART1->CR1, USART_CR1_M0);            /* E06：M0 复位为 0 且本文件未见置位 */
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x2);     /* E05：0x2 不是 MMS 的合法枚举 */
    RCC->CR = 0x00000400;                            /* E10：含只读位域 HSIRDY（bit10） */
    DMA1_Channel1->CCR |= 0x1;                       /* 未判定：簇寄存器命名（DMA1 的 CH1） */
    SysTick->CTRL = 0x00000005;                      /* 未判定：内核外设 */
    USART1->CR1 |= FOO_BAR;                          /* 未判定：无法映射的标识符 */
    USART1->CR1 |= UART_BAUD_VALUE;                  /* 通过：文件内数值宏 */
    SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);         /* 通过 */
    NVIC_SetPriorityGrouping(3);                     /* E09：与下一处重复设置 */
    NVIC_SetPriorityGrouping(3);
}
