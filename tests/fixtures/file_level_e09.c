/* 仅文件级 E09：两处中断分组设置，没有任何可核验的寄存器写入。 */
void nvic_init(void)
{
    NVIC_SetPriorityGrouping(3);
    NVIC_SetPriorityGrouping(2);
}
