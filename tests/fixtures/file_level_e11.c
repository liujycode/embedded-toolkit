/* 仅文件级 E11：先置 DMA 通道 EN，再写计数寄存器。 */
void dma_init(void)
{
    DMA1_Channel1->CCR |= DMA_CCR_EN;
    DMA1_Channel1->CNDTR = 0x00000100;
}
