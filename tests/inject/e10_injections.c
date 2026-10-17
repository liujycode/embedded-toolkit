/* 自动生成：核验器注入集（规则 E10，文件 e10_injections.c）。
   下列每一处注入都应触发一次 E10；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e10_case_01(void)
{
    USART1->SR = 0x00000020;
}

void e10_case_02(void)
{
    USART1->SR |= 0x00000040;
}

void e10_case_03(void)
{
    USART1->SR &= ~0x00000040;
}

void e10_case_04(void)
{
    SET_BIT(USART1->SR, 0x00000020);
}

void e10_case_05(void)
{
    CLEAR_BIT(USART1->SR, USART_SR_TXE);
}

void e10_case_06(void)
{
    TIM1->CNT = 0x00000010;
}

void e10_case_07(void)
{
    TIM1->CNT |= 0x00000001;
}

void e10_case_08(void)
{
    WRITE_REG(TIM1->CNT, 0x00000010);
}

void e10_case_09(void)
{
    SET_BIT(TIM1->CNT, 0x00000001);
}

void e10_case_10(void)
{
    MODIFY_REG(TIM1->CNT, 0x0000FFFF, 0x00000010);
}

void e10_case_11(void)
{
    RCC->CR |= RCC_CR_HSIRDY;
}

void e10_case_12(void)
{
    RCC->CR = 0x00000400;
}

void e10_case_13(void)
{
    RCC->CR |= 0x00000400;
}

void e10_case_14(void)
{
    RCC->CR |= (1 << 10);
}

void e10_case_15(void)
{
    RCC->CR |= (1U << 10);
}

void e10_case_16(void)
{
    SET_BIT(RCC->CR, RCC_CR_HSIRDY);
}

void e10_case_17(void)
{
    SET_BIT(RCC->CR, 0x00000400);
}

void e10_case_18(void)
{
    WRITE_REG(RCC->CR, 0x00000400);
}

void e10_case_19(void)
{
    MODIFY_REG(RCC->CR, RCC_CR_HSIRDY, RCC_CR_HSIRDY);
}

void e10_case_20(void)
{
    MODIFY_REG(RCC->CR, 0x0000FFFF, 0x00000400);
}

void e10_case_21(void)
{
    RCC->CR = 0x00000500;
}

void e10_case_22(void)
{
    RCC->CR |= RCC_CR_HSION | RCC_CR_HSIRDY;
}

void e10_case_23(void)
{
    RCC->CR.HSIRDY = 1;
}
