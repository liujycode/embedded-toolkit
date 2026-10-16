/* 自动生成：核验器注入集（规则 E09，用例 e09-15）。
   预期触发一次 E09；ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e09_15(void)
{
    /* 初始化中断分组 */
    NVIC_SetPriorityGrouping(3);
    NVIC_SetPriorityGrouping(4);
}
