/* 自动生成：核验器注入集（规则 E08，文件 e08_injections.c）。
   下列每一处注入都应触发一次 E08；逐条 ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

RCC->APB1ENR |= RCC_APB1ENR_USART2EN;

void e08_case_01(void)
{
    *(volatile uint32_t *)0x40013800 = 0x00000001;
}

void e08_case_02(void)
{
    *(volatile uint32_t *)0x4001380C = 0x00000683;
}

void e08_case_03(void)
{
    *(uint32_t *)0x40004400 = 0x00000001;
}

void e08_case_04(void)
{
    *(volatile uint32_t *)0x4000440C = 0x00000001;
}

void e08_case_05(void)
{
    *(volatile uint32_t *)0x48000000 = 0x00000001;
}

void e08_case_06(void)
{
    *(volatile uint32_t *)0x48000400 = 0x00000001;
}

void e08_case_07(void)
{
    *(volatile uint32_t *)0x48000814 = 0x00000001;
}

void e08_case_08(void)
{
    *(volatile uint32_t *)0x40012C00 = 0x00000041;
}

void e08_case_09(void)
{
    *(volatile uint32_t *)0x40012C04 = 0x00000001;
}

void e08_case_10(void)
{
    *(volatile uint32_t *)0x40021058 = 0x00000001;
}

void e08_case_11(void)
{
    *(volatile uint32_t *)0x40020000 = 0x00000001;
}

void e08_case_12(void)
{
    *(__IO uint32_t *)0x40010414 = 0x00000001;
}

void e08_case_13(void)
{
    *(volatile uint32_t *)0x40021000 = 0x00000001;
}

void e08_case_14(void)
{
    *(volatile uint32_t *)0x40013804 = 0x00000001;
}

void e08_case_15(void)
{
    *(volatile uint32_t *)0x40004404 = 0x00000001;
}

void e08_case_16(void)
{
    *(volatile uint32_t *)0x40012C50 = 0x00000001;
}

void e08_case_17(void)
{
    *(volatile uint32_t *)0xDEAD0000 = 0x00000001;
}

void e08_case_18(void)
{
    *(volatile uint32_t *)0xDEADBEEF = 0x00000001;
}

void e08_case_19(void)
{
    *(volatile uint32_t *)0x20000000 = 0x00000001;
}

void e08_case_20(void)
{
    *(volatile uint32_t *)0x40000000 = 0x00000001;
}

void e08_case_21(void)
{
    *(volatile uint32_t *)0xFFFFF000 = 0x00000001;
}

void e08_case_22(void)
{
    *(uint32_t *)0x48004000 = 0x00000001;
}
