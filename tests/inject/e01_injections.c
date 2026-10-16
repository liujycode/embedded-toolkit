/* 自动生成：核验器注入集（规则 E01，文件 e01_injections.c）。
   下列每一处注入都应触发一次 E01；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e01_case_01(void)
{
    TIM2->CR1 |= 0x00000001;
}

void e01_case_02(void)
{
    TIM3->CR1 = 0x00000080;
}

void e01_case_03(void)
{
    TIM4->SR = 0x0000001F;
}

void e01_case_04(void)
{
    SPI1->CR1 = 0x00000400;
}

void e01_case_05(void)
{
    SPI2->CR2 |= 0x00000001;
}

void e01_case_06(void)
{
    I2C1->CR1 |= 0x00000001;
}

void e01_case_07(void)
{
    I2C2->OAR1 = 0x00000050;
}

void e01_case_08(void)
{
    ADC1->CR2 |= 0x00000001;
}

void e01_case_09(void)
{
    ADC2->CR2 = 0x00000001;
}

void e01_case_10(void)
{
    DAC1->CR |= 0x00000001;
}

void e01_case_11(void)
{
    RTC->CRL = 0x00000001;
}

void e01_case_12(void)
{
    CRC->CR = 0x00000001;
}

void e01_case_13(void)
{
    RNG->CR |= 0x00000001;
}

void e01_case_14(void)
{
    CAN1->MCR |= 0x00000001;
}

void e01_case_15(void)
{
    WWDG->CR = 0x0000007F;
}

void e01_case_16(void)
{
    IWDG->KR = 0x0000CCCC;
}

void e01_case_17(void)
{
    UART4->CR1 |= 0x00000001;
}

void e01_case_18(void)
{
    UART5->CR1 |= 0x00000001;
}

void e01_case_19(void)
{
    GPIOD->MODER = 0x00000001;
}

void e01_case_20(void)
{
    GPIOE->ODR = 0x00000001;
}

void e01_case_21(void)
{
    SDMMC1->CLKCR |= 0x00000001;
}

void e01_case_22(void)
{
    ETH->MACCR |= 0x00000001;
}

void e01_case_23(void)
{
    SET_BIT(SPI3->CR1, 0x00000001);
}

void e01_case_24(void)
{
    WRITE_REG(ADC3->CR2, 0x00000001);
}
