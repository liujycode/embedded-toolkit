/* 自动生成：核验器正样本集（n36）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n36(void)
{
    uint32_t sr = USART1->SR;
    if (sr & USART_SR_TXE) { USART1->BRR = 0x00000683; }
}
