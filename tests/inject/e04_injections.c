/* 自动生成：核验器注入集（规则 E04，文件 e04_injections.c）。
   下列每一处注入都应触发一次 E04；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e04_case_01(void)
{
    TIM1->CR1 = 0x00010000;
}

void e04_case_02(void)
{
    TIM1->CR1 |= 0x00010000;
}

void e04_case_03(void)
{
    TIM1->CR1 = 0x0001FFFF;
}

void e04_case_04(void)
{
    TIM1->CR1S = 0x00010000;
}

void e04_case_05(void)
{
    GPIOA->ODR = 0x00010000;
}

void e04_case_06(void)
{
    GPIOB->ODR |= 0x00018000;
}

void e04_case_07(void)
{
    GPIOC->ODR = 0x000FFFF1;
}

void e04_case_08(void)
{
    USART1->CR1 = 0x100000000;
}

void e04_case_09(void)
{
    USART1->BRR |= 0x800000000;
}

void e04_case_10(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x8);
}

void e04_case_11(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x9);
}

void e04_case_12(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xA);
}

void e04_case_13(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xB);
}

void e04_case_14(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xC);
}

void e04_case_15(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xD);
}

void e04_case_16(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xE);
}

void e04_case_17(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xF);
}

void e04_case_18(void)
{
    SET_BIT(TIM1->CR1, 0x00010000);
}

void e04_case_19(void)
{
    WRITE_REG(TIM1->CR1, 0x00010000);
}

void e04_case_20(void)
{
    CLEAR_BIT(TIM1->CR1, 0x00010000);
}

void e04_case_21(void)
{
    MODIFY_REG(TIM1->CR1, TIM_CR1_CEN, 0x00010000);
}

void e04_case_22(void)
{
    MODIFY_REG(TIM1->CR1, TIM_CR1_CEN | TIM_CR1_DIR, 0x00020000);
}

void e04_case_23(void)
{
    MODIFY_REG(GPIOA->MODER, GPIO_MODER_MODE0_Msk, 0x00010000);
}
