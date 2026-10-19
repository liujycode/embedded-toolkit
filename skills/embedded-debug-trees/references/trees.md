<!-- 本文件由 tools/knowledge_check.py --doc 从 assets/*.json 生成，勿手改。 -->

# 决策树全量参考（自动生成）

## hardfault — 代码跑飞 / HardFault

高频根因（按实战经验排序，非实测统计）：

1. 中断服务函数里调用非重入/阻塞函数（printf/malloc/延时）
2. 栈溢出（局部大数组/递归/RTOS 任务栈给小了）
3. 外设时钟未开就访问寄存器（RCC 使能遗漏）
4. DMA 缓冲区被编译器优化/放错内存段（DTCM 里 DMA 到不了）
5. 中断优先级超过 BASEPRI 屏蔽线却调用了 FreeRTOS API（FromISR 后缀没加）

- **get-frame** 取 fault 栈帧
  - 症状：HardFault 已触发，先定位现场
  - 证据动作：判断用 PSP 还是 MSP（EXC_RETURN bit2），取 PC/LR；有 RTOS 先分清是哪个任务的栈
  - 判定：拿到出错 PC 后进入 CFSR 解读分支
  - **iaccvio** 非法地址访问（IACCVIOL/MUNSTALL）
    - 症状：CFSR.IACCVIOL 或 MemManage 置位
    - 证据动作：查 PC 指向：0xE0000000 段=函数指针未初始化；随机地址=野指针
    - 判定：野指针/函数指针问题
    - 对策：dump 调用栈，找最近的数组/指针操作
    - 对策：检查函数指针表初始化顺序
  - **precise** 精确总线错误（PRECISERR）
    - 症状：CFSR.PRECISERR 置位，出错指令可直接定位
    - 证据动作：查该指令访问的地址——通常是外设没开时钟就访问
    - 判定：RCC 使能遗漏（最高频）或地址越界
    - 对策：核对 RCC->AHB1ENR/APB1ENR/APB2ENR 对应位
    - 对策：用 embedded-register-verify check 复查全部寄存器写入
  - **imprecise** 非精确总线错误（IMPRECISERR）
    - 症状：CFSR.IMPRECISERR 置位，写缓冲延迟导致 PC 不准
    - 证据动作：开启 write-through 或查 DMA 目标地址合法性
    - 判定：DMA 目标地址错误或写缓冲时序
    - 对策：核对 DMA 的 M0AR/M1AR 目标地址
    - 对策：暂时关写缓冲（SCnB 位）复现定位
  - **undefinstr** 未定义指令（UNDEFINSTR）
    - 症状：CFSR.UNDEFINSTR 置位
    - 证据动作：查函数指针是否跳到数据区；查中断向量表位置与编译优化
    - 判定：函数指针/向量表错位
    - 对策：核对 VTOR 偏移（Bootloader 跳 App 必查）
    - 对策：检查链接脚本的向量表段
  - **stkerr** 栈溢出（STKERR/MSTKERR）
    - 症状：CFSR.STKERR 或 MSTKERR 置位
    - 证据动作：填充栈为 0xA5 查水位；RTOS 用 uxTaskGetStackHighWaterMark
    - 判定：栈溢出（高频！）
    - 对策：加大任务栈/去局部大数组
    - 对策：开 FreeRTOS 的 configCHECK_FOR_STACK_OVERFLOW=2
- **snapshot** 复现策略
  - 症状：故障偶发难抓
  - 证据动作：加故障快照：fault 时把 CFSR/HFSR/栈帧 dump 到保留 RAM 或串口，复位后打印
  - 判定：拿到偶发故障的现场证据
- **nocep-fpu** UsageFault：NOCP（FPU 没使能就执行浮点指令）
  - 症状：CFSR 的 NOCP 置位；一跑浮点运算或进入浮点中断就 fault
  - 证据动作：读 CFSR 确认 NOCP；读 SCB->CPACR 看 CP10/CP11 是否使能；查工程的 FPU 选项（__FPU_PRESENT/__FPU_USED）
  - 判定：FPU 未使能或编译选项与硬件不匹配
  - 对策：SystemInit 里使能 CP10/CP11（或开编译器的硬件浮点选项让启动文件代做）
  - 对策：FreeRTOS 注意浮点上下文保存与懒压栈配置
- **lockup** LOCKUP 状态（fault 处理器里又 fault）
  - 症状：整机无响应且复位才恢复；调试器连上看到内核处于 LOCKUP
  - 证据动作：查 HFSR（FORCED/VECTTBL）；配合故障快照看第一现场——是不是在 NMI/HardFault 处理器里又触发了 fault
  - 判定：双重故障进入 LOCKUP
  - 对策：fault 处理器里只做最安全的记录动作（别再碰外设、别再嵌套）
  - 对策：先解决被 FORCED 升级成 HardFault 的原始 fault

## comm — 通信链路不通（I2C/SPI/UART）

高频根因（按实战经验排序，非实测统计）：

1. GPIO 复用模式没配对（AF/开漏/上拉）
2. 外设或 GPIO 时钟未使能
3. SPI 的 CPOL/CPHA 与从机手册不符
4. 波特率/分频计算错误（误差>2%）
5. DMA 缓冲区不可达或 NDTR/标志位处理顺序错

- **layer1-config** 第一层：配置对不对（不用仪器）
  - 症状：链路完全无响应/初始化后外设不工作
  - 证据动作：读回寄存器验证：RCC 使能位、GPIO MODER/AFR、波特率 BRR
  - 判定：回读值与预期不符=配置问题，本层解决
  - 对策：按'时钟→GPIO→外设→中断→使能'顺序逐项回读
  - 对策：用 embedded-register-verify check 复查初始化代码
- **layer2-timing** 第二层：时序对不对（要仪器）
  - 症状：配置回读全对但通信仍失败
  - 证据动作：示波器/逻辑分析仪抓波形：I2C 看 ACK 卡在哪个字节；SPI 比对第一字节位序；UART 看波特率误差
  - 判定：波形与协议不符=时序问题
  - 对策：I2C：SDA 拉死→9 脉冲解救或复位外设电源
  - 对策：SPI：CPOL/CPHA 先读从机手册时序图，四组合试错不如读手册
  - 对策：UART：波特率误差<2%，HSI±1% 精度不够就换 HSE
- **layer3-dataflow** 第三层：数据流对不对
  - 症状：物理层通了但数据不对
  - 证据动作：查 DMA 配置（内存段/宽度/循环）、中断标志清除顺序、IDLE+DMA 不定长方案
  - 判定：数据流配置问题
  - 对策：I2C F1 系：先读 SR 再读 DR 的顺序陷阱
  - 对策：UART 空闲中断：先清 IDLE 再使能，用 NDTR 算长度
  - 对策：缓冲区放 DMA 可达内存段（H7 的 DTCM 到不了）
- **half-duplex** 半双工链路（RS485 等）方向切换
  - 症状：对端收得到我发的，我收不到回包；或报文最后一字节丢
  - 证据动作：查 DE/RE 方向脚的切换时机与极性：是否等发送完成就切回接收
  - 判定：方向控制时机/极性问题
  - 对策：发送完等 TC（发送完成）标志再拉方向脚——TXE 只表示数据寄存器空，最后一个字节还在移位
  - 对策：或用 USART 自带的 RS485 方向控制（CR3 的 DEM/DEAT/DET）

## dma — DMA 异常（丢数据/错位/不启动）

高频根因（按实战经验排序，非实测统计）：

1. 非循环模式跑完即停（没有重启/改 circular）
2. Cache 一致性未处理（H7/F7）或缓冲区在 DMA 不可达内存段
3. PSIZE/MSIZE 与外设寄存器宽度不匹配
4. 缓冲区被主程序与 DMA 同时读写（无 ping-pong）
5. 请求源使能没开（如 USART 的 DMAR 位）

- **once-only** 只收到第一次
  - 症状：DMA 只传一轮，之后无数据
  - 证据动作：查模式位：非循环跑完即停；查接收缓冲/NDTR 是否重装
  - 判定：模式/重启问题
  - 对策：改 circular 模式
  - 对策：每次传输前重启 DMA 并重装计数
- **misaligned** 数据错位/宽度错
  - 症状：数据错位、半字当字节
  - 证据动作：查 PSIZE/MSIZE 与外设寄存器宽度匹配；查 DMA 请求映射表确认通道
  - 判定：宽度/通道映射问题
  - 对策：PSIZE=MSIZE=外设数据宽度
  - 对策：按参考手册的 DMA 请求映射表核对通道
- **corrupt** 数据偶发损坏
  - 症状：大多数正确，偶发帧坏
  - 证据动作：查主程序与 DMA 是否同时读写缓冲（无 ping-pong/双缓冲）；中断处理是否太慢被覆盖
  - 判定：并发/时效问题
  - 对策：做 ping-pong 双缓冲
  - 对策：缩短 ISR 或用半满/全满双中断
- **cache** Cache 一致性（H7/F7）
  - 症状：DMA 收到的数据是旧数据/主核读到旧数据
  - 证据动作：检查 D-Cache 使能状态；对缓冲区做 Invalidate/Clean；确认 32 字节对齐
  - 判定：Cache 一致性问题
  - 对策：收方向：SCB_InvalidateDCache_by_Addr
  - 对策：发方向：SCB_CleanDCache_by_Addr
  - 对策：或把缓冲放非 Cache 区并 32 字节对齐
- **not-start** DMA 根本没启动
  - 症状：配置全做了但没有传输
  - 证据动作：查外设侧 DMA 请求使能（USART 的 DMAR/DMAT 位）+ DMA 控制器时钟
  - 判定：请求链没打通
  - 对策：开外设的 DMA 使能位
  - 对策：回读 DMA_CR 确认 EN 位已置
- **dmamux** DMAMUX 请求映射错（G4/H7/L4+ 等新系列）
  - 症状：DMA 触发不了，或被不相干的请求误触发
  - 证据动作：查 DMAMUX 通道的 DMAREQ_ID 选择；查是否多个通道映射到同一请求线
  - 判定：请求映射/复用问题
  - 对策：按参考手册的 DMAMUX 请求表核对 DMAREQ_ID
  - 对策：确认 MUX 通道与 DMA 通道的对应关系（不是每片都一样）

## rtos — RTOS 应用异常

高频根因（按实战经验排序，非实测统计）：

1. 任务栈太小导致溢出踩 TCB
2. 任务无阻塞点饿死低优先级（看门狗复位是典型症状）
3. 中断里调用非 FromISR API
4. 中断优先级数值与 configMAX_SYSCALL_INTERRUPT_PRIORITY 关系搞反
5. 用二值信号量做资源保护导致优先级反转

- **task-not-run** 任务不跑/跑一次就停
  - 症状：某个任务没有周期执行
  - 证据动作：查任务栈水位（uxTaskGetStackHighWaterMark）；查任务里有没有阻塞点；查优先级抢占配置
  - 判定：栈溢出/饿死/优先级配置错
  - 对策：加大任务栈
  - 对策：任务循环加 vTaskDelay/队列阻塞
  - 对策：理清抢占与时间片
- **deadlock** 偶发死锁
  - 症状：系统跑一段时间卡死
  - 证据动作：查互斥锁获取顺序是否全局一致；查中断里是否误用非 FromISR API
  - 判定：锁排序/中断 API 误用
  - 对策：所有任务按同一顺序拿锁
  - 对策：开 configASSERT 抓现场
  - 对策：中断一律用 xxxFromISR 后缀 API
- **prio-invert** 优先级反转
  - 症状：高优先级任务被低优先级任务长期阻塞
  - 证据动作：查资源保护用的是互斥量（带优先级继承）还是二值信号量
  - 判定：优先级反转
  - 对策：改用 xSemaphoreCreateMutex（继承机制）
  - 对策：缩小临界区范围
- **nvic-map** 中断优先级映射大坑
  - 症状：中断里调 RTOS API 就挂死
  - 证据动作：核对中断优先级数值与 configMAX_SYSCALL_INTERRUPT_PRIORITY；记住 Cortex-M 数值越大优先级越低（反直觉）
  - 判定：优先级映射错误
  - 对策：需要调 RTOS API 的中断：优先级数值必须 ≥ configMAX_SYSCALL...（即逻辑上不高于）
  - 对策：全工程统一 NVIC 分组并只初始化一次
- **tick-dead** 任务卡在 vTaskDelay 不再继续
  - 症状：任务跑到第一个延时/队列等待就永远停住
  - 证据动作：查 SysTick 计数器是否在走；查 SysTick 优先级有没有被应用代码改掉；查有没有临界区把中断关了没恢复
  - 判定：时基没跑或被屏蔽
  - 对策：FreeRTOS 启动时自设 SysTick 优先级——应用别再动它
  - 对策：检查进/出临界区是否成对（PRIMASK/BASEPRI 恢复）

## boot — 启动失败

高频根因（按实战经验排序，非实测统计）：

1. HSE 起振失败（晶振焊接/负载电容）
2. 向量表偏移 VTOR 没设（Bootloader 跳 App）
3. 启动文件堆栈大小不足
4. BOOT0/BOOT1 引脚电平进了系统 Bootloader
5. 看门狗复位循环（IWDG 没喂）

- **clock-stuck** 卡在时钟初始化
  - 症状：上电后卡死在 SystemInit/HSE 等待循环
  - 证据动作：切 HSI 先跑起来；查晶振焊接与负载电容；查 PLL 倍频与 VOS 电压档位
  - 判定：晶振/PLL 配置问题
  - 对策：临时切 HSI 运行缩小范围
  - 对策：查 datasheet 的 VOS 档位与最高频率对应表
- **vtor** Bootloader 跳 App 后异常
  - 症状：Bootloader 正常，跳转后 HardFault/不跑
  - 证据动作：查 App 里是否设置 VTOR；查向量表与链接脚本；查栈顶值（SP 初始化）
  - 判定：向量表/栈指针未重定位
  - 对策：跳转前关中断，App 开头 SCB->VTOR = FLASH_BASE | offset
  - 对策：确认 App 向量表第一项是栈顶地址、第二项是 Reset_Handler
- **reset-source** 复位原因判定
  - 症状：设备周期性复位/复位原因不明
  - 证据动作：读 RCC->CSR（或同系列复位标志寄存器）分清：IWDG/WWDG/软复位/上电/引脚复位
  - 判定：看门狗循环或电源问题
  - 对策：IWDG 复位→查喂狗路径（哪个任务喂、卡在哪没喂到）
  - 对策：引脚复位→查 NRST 电路与干扰
- **boot-pins** BOOT 引脚状态
  - 症状：App 不跑但 SWD 能连
  - 证据动作：查 BOOT0/BOOT1 电平；读 DBGMCU 确认 CPU 在哪个区执行
  - 判定：从系统 Bootloader 启动了
  - 对策：BOOT0 拉低（GND）后复位
  - 对策：检查 BOOT 引脚的外围电路
- **swd-locked** SWD 连不上（看似起不来）
  - 症状：以为程序没跑，但上电电流正常；SWD 偶尔能连
  - 证据动作：查 PA13/PA14（SWDIO/SWCLK）是否被初始化代码配走；查是否进了低功耗（SWD 断连）；用 Connect under Reset 试
  - 判定：调试口被软件抢走或低功耗断连
  - 对策：初始化代码保留 SWD 引脚复用
  - 对策：Connect under Reset（拉低 NRST 时连接）
  - 对策：调试期低功耗要开 DBGMCU 的 DBG_STOP/DBG_STANDBY 保持调试连接

## pwr — 低功耗与唤醒异常

高频根因（按实战经验排序，非实测统计）：

1. 唤醒后系统时钟没重配（外设全乱了：乱码/定时不准）
2. 唤醒源没配对或唤醒标志没清（睡死叫不醒）
3. 有中断标志没清干净——刚进停机立刻被唤醒，量不到低电流
4. 调试器连接改变低功耗行为（DBGMCU）

- **stop-clock** 唤醒后外设乱码/定时不准
  - 症状：停机模式唤醒后 UART 乱码、定时器变慢
  - 证据动作：读回 RCC 时钟状态寄存器：唤醒后系统时钟常回落到 HSI/MSI（PLL 已关）
  - 判定：唤醒后时钟未重配
  - 对策：唤醒后第一时间重跑时钟初始化（重启 PLL 并切换）
  - 对策：或外设时钟源改用唤醒后仍可用的源，并重算波特率/分频
- **wakeup-src** 睡死叫不醒
  - 症状：进入停机/待机后唤醒不了
  - 证据动作：逐项核对唤醒源：EXTI 线与边沿、RTC 闹钟/唤醒定时器；查唤醒标志（WUF 等）是否在进睡前清掉
  - 判定：唤醒源配置/标志未清
  - 对策：进睡前先清唤醒标志，再使能唤醒源，最后进低功耗
  - 对策：待机模式的唤醒源只有少数特定引脚/RTC——查手册的唤醒源表，别按停机模式的经验配
- **sleep-not-enter** 进不了低功耗（电流降不下来）
  - 症状：调了 WFI 但整板电流没变
  - 证据动作：查未清的外设中断标志（一进停机立刻被唤醒）；查外设时钟是否全关、引脚是否悬空漏电
  - 判定：标志未清/外设未关
  - 对策：进睡前清干净全部外设标志、关闭不用的外设时钟
  - 对策：配 GPIO 为模拟输入防悬空漏电；量电流波形找唤醒瞬间
- **dbg-block** 调试器挂着正常，拔了就异常
  - 症状：联调时低功耗/时序行为与脱机不一致
  - 证据动作：查 DBGMCU 的 DBG_STOP/DBG_STANDBY（调试期冻结低功耗）；排查是否依赖了调试器在场的时序
  - 判定：调试器改变时序/低功耗行为
  - 对策：需要脱机复现时关掉调试冻结位，或改用故障快照/串口打印
  - 对策：时序敏感逻辑不依赖调试期时序
