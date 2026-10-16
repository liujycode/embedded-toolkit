/* 自动生成：核验器注入集（规则 E03，文件 e03_injections.c）。
   下列每一处注入都应触发一次 E03；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e03_case_01(void)
{
    USART1->CR1 |= USART_CR1_ZZZ;
}

void e03_case_02(void)
{
    USART1->CR1 |= USART_CR1_RXNE;
}

void e03_case_03(void)
{
    USART1->CR1 |= USART_CR1_RE;
}

void e03_case_04(void)
{
    USART1->CR1 |= USART_CR1_IDLE;
}

void e03_case_05(void)
{
    USART1->CR1 |= USART_CR1_PE;
}

void e03_case_06(void)
{
    USART1->CR1 |= USART_CR1_TXEIE;
}

void e03_case_07(void)
{
    USART1->CR1 |= USART_CR1_ABREN;
}

void e03_case_08(void)
{
    USART1->CR1 = USART_CR1_SBRK;
}

void e03_case_09(void)
{
    SET_BIT(USART1->CR1, USART_CR1_LBDF);
}

void e03_case_10(void)
{
    CLEAR_BIT(USART1->CR1, USART_CR1_TXEIE);
}

void e03_case_11(void)
{
    USART1->CR1 |= USART_BRR_DIV;
}

void e03_case_12(void)
{
    USART1->CR1 |= USART_SR_TXE;
}

void e03_case_13(void)
{
    USART1->CR1 |= USART_SR_TC;
}

void e03_case_14(void)
{
    USART1->BRR = USART_CR1_UE;
}

void e03_case_15(void)
{
    TIM1->CR2 |= TIM_CR1_CEN;
}

void e03_case_16(void)
{
    TIM1->CR1 |= TIM_CR2_MMS_Msk;
}

void e03_case_17(void)
{
    TIM1->CR1 |= TIM_CR2_MMS;
}

void e03_case_18(void)
{
    TIM1->CR2 = TIM_CR1_DIR;
}

void e03_case_19(void)
{
    USART1->CR1 |= USART_CR1_PS_EVEEN;
}

void e03_case_20(void)
{
    USART1->CR1 |= USART_CR1_PS_OD;
}

void e03_case_21(void)
{
    USART1->CR1 |= USART_CR1_PS_PS;
}

void e03_case_22(void)
{
    MODIFY_REG(USART1->CR1, USART_CR1_PS_EVEEN, 0);
}

void e03_case_23(void)
{
    USART1->CR1 |= USART_CR1_M0_M0;
}

void e03_case_24(void)
{
    WRITE_REG(USART1->CR1, USART_CR1_PS_ODDD);
}
