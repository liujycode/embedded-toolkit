/* 自动生成：核验器注入集（规则 E02，文件 e02_injections.c）。
   下列每一处注入都应触发一次 E02；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e02_case_01(void)
{
    USART1->CR2 |= 0x00002000;
}

void e02_case_02(void)
{
    USART1->CR3 = 0x00000000;
}

void e02_case_03(void)
{
    USART1->GTPR = 0x00000000;
}

void e02_case_04(void)
{
    USART1->RQR = 0x00000001;
}

void e02_case_05(void)
{
    USART1->ICR = 0x00000001;
}

void e02_case_06(void)
{
    USART2->ISR = 0x00000000;
}

void e02_case_07(void)
{
    USART2->TDR = 0x00000041;
}

void e02_case_08(void)
{
    TIM1->CR3 = 0x00000000;
}

void e02_case_09(void)
{
    TIM1->SMCR = 0x00000000;
}

void e02_case_10(void)
{
    TIM1->DIER = 0x00000001;
}

void e02_case_11(void)
{
    TIM1->EGR = 0x00000001;
}

void e02_case_12(void)
{
    TIM1->PSC = 0x0000FFFF;
}

void e02_case_13(void)
{
    TIM1->ARR = 0x0000FFFF;
}

void e02_case_14(void)
{
    GPIOA->IDR = 0x00000001;
}

void e02_case_15(void)
{
    GPIOA->BSRR = 0x00000001;
}

void e02_case_16(void)
{
    GPIOA->AFRL = 0x00000000;
}

void e02_case_17(void)
{
    RCC->CFGR |= 0x00000002;
}

void e02_case_18(void)
{
    RCC->AHB1ENR |= 0x00000001;
}

void e02_case_19(void)
{
    RCC->BDCR = 0x00000001;
}

void e02_case_20(void)
{
    DMA1->IFCR = 0x00000001;
}

void e02_case_21(void)
{
    DMA1->CSELR = 0x00000001;
}

void e02_case_22(void)
{
    WRITE_REG(RCC->APB2ENR, 0x00000001);
}
