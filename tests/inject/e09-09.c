/* 自动生成：核验器注入集（规则 E09，用例 e09-09）。
   预期触发一次 E09；ground truth 见 tests/inject/manifest.json。
   请勿手改：重新生成 python tools/verify_bench.py generate */
#include "synth32.h"

void e09_09(void)
{
    NVIC_SetPriorityGrouping(3U);
    NVIC_SetPriorityGrouping(3U);
}
