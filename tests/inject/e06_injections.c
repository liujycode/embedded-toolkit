/* 自动生成：核验器注入集（规则 E06，文件 e06_injections.c）。
   下列每一处注入都应触发一次 E06；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

RCC->APB1ENR |= RCC_APB1ENR_USART2EN;

void e06_case_01(void)
{
    CLEAR_BIT(USART1->CR1, USART_CR1_TE);
}

void e06_case_02(void)
{
    CLEAR_BIT(USART1->CR1, USART_CR1_PS);
}

void e06_case_03(void)
{
    CLEAR_BIT(USART1->CR1, USART_CR1_OVER8);
}

void e06_case_04(void)
{
    CLEAR_BIT(USART2->CR1, USART_CR1_UE);
}

void e06_case_05(void)
{
    CLEAR_BIT(USART2->CR1, USART_CR1_M0);
}

void e06_case_06(void)
{
    CLEAR_BIT(USART3->CR1, USART_CR1_TE);
}

void e06_case_07(void)
{
    CLEAR_BIT(USART3->CR1, USART_CR1_M0);
}

void e06_case_08(void)
{
    CLEAR_BIT(TIM1->CR1, TIM_CR1_CEN);
}

void e06_case_09(void)
{
    CLEAR_BIT(TIM1->CR2, TIM_CR2_MMS_Msk);
}

void e06_case_10(void)
{
    CLEAR_BIT(GPIOA->ODR, GPIO_ODR_OD0);
}

void e06_case_11(void)
{
    CLEAR_BIT(GPIOB->ODR, GPIO_ODR_OD0);
}

void e06_case_12(void)
{
    CLEAR_BIT(EXTI->PR, EXTI_PR_P0);
}

void e06_case_13(void)
{
    CLEAR_BIT(EXTI->PR, EXTI_PR_P1);
}

void e06_case_14(void)
{
    CLEAR_BIT(RCC->APB1ENR, RCC_APB1ENR_I2C1EN);
}

void e06_case_15(void)
{
    CLEAR_BIT(TIM1->CR1, TIM_CR1_DIR);
}

void e06_case_16(void)
{
    CLEAR_BIT(USART3->CR1, USART_CR1_PS);
}

void e06_case_17(void)
{
    USART1->CR1 &= ~USART_CR1_UE;
}

void e06_case_18(void)
{
    USART2->CR1 &= ~USART_CR1_TE;
}

void e06_case_19(void)
{
    TIM1->CR1 &= ~TIM_CR1_DIR;
}

void e06_case_20(void)
{
    GPIOC->ODR &= ~GPIO_ODR_OD0;
}

void e06_case_21(void)
{
    USART3->CR1 &= ~USART_CR1_OVER8;
}

void e06_case_22(void)
{
    RCC->APB1ENR &= ~RCC_APB1ENR_I2C1EN;
}

void e06_case_23(void)
{
    USART2->CR1 &= ~USART_CR1_OVER8;
}

void e06_case_24(void)
{
    EXTI->PR &= ~EXTI_PR_P0;
}
