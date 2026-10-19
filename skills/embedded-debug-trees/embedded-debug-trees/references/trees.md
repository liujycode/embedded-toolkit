# 排障决策树正文（人类可读全量版）

> 本文档是 assets/trees.json 的人类可读对照版，内容同源。检索用 `scripts/trees.py`（结构化），通读用本文档。
> 维护纪律：改任何一棵树，**先改 trees.json（权威源），再同步本文档**——两者不一致时以 trees.json 为准。

## 树一：hardfault（代码跑飞 / HardFault）

### 第一步：取 fault 栈帧
- **动作**：判断用 PSP 还是 MSP（EXC_RETURN bit2），取 PC/LR；有 RTOS 先分清是哪个任务的栈
- **判定**：拿到出错 PC 后进入 CFSR 解读分支

### CFSR 按位解读分支

| 分支 | 症状 | 证据动作 | 判定 | 对策 |
|---|---|---|---|---|
| IACCVIOL/MUNSTALL | 非法地址访问 | 查 PC 指向：0xE0000000 段=函数指针未初始化；随机地址=野指针 | 野指针/函数指针 | dump 调用栈找最近数组/指针操作；查函数指针表初始化顺序 |
| PRECISERR | 精确总线错误 | 出错指令可直接定位，查访问的地址 | **RCC 使能遗漏（最高频）**或地址越界 | 核对 RCC 使能位；用 embedded-register-verify 复查全部写入 |
| IMPRECISERR | 非精确总线错误 | 写缓冲延迟 PC 不准 | DMA 目标地址错误/写缓冲 | 核对 DMA M0AR/M1AR；暂关写缓冲复现 |
| UNDEFINSTR | 未定义指令 | 查函数指针跳数据区/向量表错位 | 函数指针/向量表 | 核对 VTOR（Bootloader 必查）；查链接脚本向量表段 |
| STKERR/MSTKERR | 栈溢出（高频！） | 填栈 0xA5 查水位；RTOS 用 uxTaskGetStackHighWaterMark | 栈溢出 | 加大栈/去局部大数组；开 configCHECK_FOR_STACK_OVERFLOW=2 |

### 高频根因排行（实战统计）
1. 中断服务函数里调用非重入/阻塞函数（printf/malloc/延时）
2. 栈溢出（局部大数组/递归/RTOS 任务栈给小了）
3. 外设时钟未开就访问寄存器（RCC 使能遗漏）
4. DMA 缓冲区被编译器优化/放错内存段（DTCM 里 DMA 到不了）
5. 中断优先级超过 BASEPRI 屏蔽线却调用了 FreeRTOS API（FromISR 后缀没加）

### 复现策略
故障偶发难抓 → 加"故障快照"：fault 时把 CFSR/HFSR/栈帧 dump 到保留 RAM 或串口，复位后打印。

## 树二：comm（通信链路不通）

### 第一层：配置对不对（不用仪器）
- 读回验证：RCC 使能位、GPIO MODER/AFR、波特率 BRR
- 回读与预期不符=配置问题，本层解决
- 对策：按"时钟→GPIO→外设→中断→使能"逐项回读；用 embedded-register-verify 复查初始化代码

### 第二层：时序对不对（要仪器）
- I2C：START 后地址对没？ACK 回没？卡在哪个字节？
  - SDA 拉死不释放 → 从机卡总线 → 9 脉冲解救或复位外设电源
- SPI：CPOL/CPHA 与从机手册对没？（**先读手册时序图，四组合试错是浪费生命**）
- UART：波特率误差 <2%？HSI ±1% 不够就换 HSE

### 第三层：数据流对不对
- DMA：缓冲区在 DMA 可达内存段？（H7 DTCM 到不了）长度/宽度/循环模式
- 中断：标志清除顺序（F1 的 I2C"先读 SR 再读 DR"陷阱）
- 空闲中断+DMA：IDLE 先清再使能，NDTR 算长度

## 树三：dma（DMA 异常）

| 节点 | 症状 | 判定 | 对策 |
|---|---|---|---|
| once-only | 只收到第一次 | 非循环跑完即停 | 改 circular 或每次重启+重装 NDTR |
| misaligned | 数据错位/半字当字节 | PSIZE/MSIZE 不匹配/通道映射错 | 宽度对齐外设寄存器；查请求映射表 |
| corrupt | 偶发损坏 | 主程序与 DMA 并发读写/ISR 太慢 | ping-pong 双缓冲；半满/全满双中断 |
| cache | 收到旧数据（H7/F7） | D-Cache 一致性 | 收方向 Invalidate、发方向 Clean；或非 Cache 区+32 字节对齐 |
| not-start | 根本没启动 | 请求链没通 | 外设 DMAR/DMAT 位+DMA 控制器时钟，回读 DMA_CR.EN |

**根因排行**：非循环模式没重启 > Cache 一致性 > 宽度不匹配 > 并发冲突 > 请求源没开。

## 树四：rtos（RTOS 应用异常）

| 节点 | 症状 | 判定 | 对策 |
|---|---|---|---|
| task-not-run | 任务不跑/跑一次停 | 栈溢出/饿死/优先级错 | 查水位；任务循环加阻塞点；理清抢占与时间片 |
| deadlock | 偶发死锁 | 锁排序不一致/FromISR 误用 | 全局统一锁顺序；configASSERT 抓现场；中断一律 xxxFromISR |
| prio-invert | 高优先级被长期阻塞 | 优先级反转 | 用 xSemaphoreCreateMutex（继承）；缩小临界区 |
| nvic-map | 中断里调 API 挂死 | 优先级映射错 | 数值 ≥ configMAX_SYSCALL（**数值大=优先级低，反直觉**）；分组只初始化一次 |

## 树五：boot（启动失败）

| 节点 | 症状 | 判定 | 对策 |
|---|---|---|---|
| clock-stuck | 卡在时钟初始化 | 晶振/PLL 问题 | 切 HSI 缩小范围；查负载电容与 VOS 档位 |
| vtor | Bootloader 跳 App 异常 | 向量表/SP 未重定位 | 跳前关中断；App 开头设 VTOR；核对向量表头两项 |
| reset-source | 周期性复位 | 看门狗循环/电源 | 读 RCC->CSR 分清复位源；查喂狗路径 |
| boot-pins | App 不跑但 SWD 能连 | 进了系统 Bootloader | BOOT0 拉低复位；查 BOOT 外围电路 |
