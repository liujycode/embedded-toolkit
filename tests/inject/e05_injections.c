/* 自动生成：核验器注入集（规则 E05，文件 e05_injections.c）。
   下列每一处注入都应触发一次 E05；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

#define BAD_MMS 0x2
#define BAD_MMS_2 (0x1 + 0x2)

void e05_case_01(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x2);
}

void e05_case_02(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x3);
}

void e05_case_03(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 2);
}

void e05_case_04(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 3);
}

void e05_case_05(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0b10);
}

void e05_case_06(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0b11);
}

void e05_case_07(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x1 + 0x1));
}

void e05_case_08(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x1 + 0x2));
}

void e05_case_09(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x4 >> 1));
}

void e05_case_10(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x6 >> 1));
}

void e05_case_11(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x3 & 0x3));
}

void e05_case_12(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x7 & 0x2));
}

void e05_case_13(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, ~(~0x2));
}

void e05_case_14(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 2U);
}

void e05_case_15(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_MASK, 0x2);
}

void e05_case_16(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x7 % 5));
}

void e05_case_17(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, BAD_MMS);
}

void e05_case_18(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, BAD_MMS_2);
}

void e05_case_19(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (int)0x2);
}

void e05_case_20(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x1F & 0x2);
}
