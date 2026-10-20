# 知识检索评测（embedded-debug-trees / embedded-peripheral-pitfalls）

用例 = 真实症状/场景查询 + 期望命中的树或坑位（注入式，逐条 ground truth）；
被测实现 = 技能脚本里的检索函数本体（import 复用，测的就是分发代码）。

| 技能 | 用例 | 命中 | 召回 | p@1 | MRR |
|---|---|---|---|---|---|
| embedded-debug-trees（按树） | 84 | 84 | 100.0% | 47.6% | 64.8% |
| embedded-peripheral-pitfalls（按坑位） | 146 | 146 | 100.0% | 97.3% | 98.1% |
| **合计** | **230** | **230** | **100.0%** | **79.1%** | **86.0%** |

## 期望排名 >3 的用例（p@1/MRR 可改进点）

| 技能 | 用例 | 期望目标 | 排名 |
|---|---|---|---|
| debug-trees | 插上之后根本不弹设备也没反应，识别不到，查 DP 上拉和软断开 | usb | 32 |
| pitfalls | 配置 I2C 有哪些常见的坑要注意？ | i2c-pullup | 26 |
| debug-trees | 刷新时画面上下撕裂，想加 TE 双缓冲 | display | 17 |
| debug-trees | Bootloader 跳 App 后 HardFault | boot | 11 |
| debug-trees | I2C 的 SDA 被从机拉死了怎么解救 | comm | 10 |
| debug-trees | 示波器抓 I2C 的 ACK | comm | 10 |
| debug-trees | H7 上 DMA 收到的是旧数据，cache 问题 | dma | 9 |
| debug-trees | 设备管理器一直报 错误43，枚举老失败卡在描述符 | usb | 8 |
| debug-trees | 写完马上读是旧数据，是不是没轮询 busy 标志 | flash | 8 |
| debug-trees | 插上电脑识别不到设备，先量 48Mhz 时钟有没有 | usb | 6 |
| debug-trees | 传输偶发丢字节，怀疑 PMA 缓冲对齐不对 | usb | 5 |
| debug-trees | 在中断里做页擦除程序卡死，还有看门狗复位 | flash | 5 |
| debug-trees | DMA 请求使能没开，配置都对就是不搬 | dma | 5 |
| debug-trees | 我想只收某一个 ID 的报文，其它都滤掉，过滤器掩码怎么配 | can | 4 |
| debug-trees | 配了选项字节读保护后 SWD 连不上，flash 也读不出来 | flash | 4 |
| debug-trees | RTC 唤醒定时器没到点就醒，闹钟周期不对 | rtc | 4 |
| pitfalls | 改了 ARR 新周期不生效 | tim-ug | 4 |

口径：查询经技能自带 tokenize + 同义词 + 反向关键词匹配后，期望的树/坑位出现在命中列表即为命中（召回）；排名=期望目标在命中列表的位置；p@1=期望目标排第 1 的占比；MRR=期望目标倒数排名的均值。召回 100% 是硬门禁，p@1/MRR 首版基线只报告不设门。
