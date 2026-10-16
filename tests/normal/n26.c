/* 自动生成：核验器正样本集（n26）。
   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void n26(void)
{
    MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x00000007);
}
