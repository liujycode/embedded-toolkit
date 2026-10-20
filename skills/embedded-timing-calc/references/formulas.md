# 时序计算公式与阈值依据

> 本文档是各计算器的公式推导与判定阈值出处。**阈值权威源是 assets/thresholds.json**（带 source 字段），本文档是推导说明，两者不一致时以 thresholds.json 为准。

## UART（uart）

- **BRR = round(PCLK / (OSR × Baud))**，OSR=16（标准）或 8（高速模式）
- 实际波特率 = PCLK / (OSR × BRR)
- 判定：误差 ≤ 2% 可用。**依据**：8N1 帧 10 位（含起始位），采样点在每位中央（7/16~9/16），累计漂移不超过采样窗宽度的一半（约 ±3%），工程留裕量取 2%——与 STM32 手册推荐一致（RM0008 USART 章节）
- 误差超限对策：换 HSE/晶振（主频可整除）、降波特率、选 8 倍过采样

## 定时器 PWM（timer）

- **F = PCLK / ((PSC+1) × (ARR+1))**
- 反向推荐：遍历常见 PSC 值算 ARR，按误差升序给前 5 组
- 两个高频坑（详见 embedded-peripheral-pitfalls 的 tim 类）：APB 分频>1 时定时器时钟 = PCLK×2；改 ARR 下个更新事件才生效
- 依据：STM32 RM0090/RM0440 时基单元

## I2C 上拉（i2c-rp）

- **Rp_max = tr_max / (0.8473 × Cb)**——spec Rev7.0 单调 RC 上升沿公式（0.8473=ln(0.7/0.3)，30%→70%）
- **std / fast / Fm+ 三种模式同用 0.8473**：提速不是换系数，而是 spec 把 tr_max 收紧（1000/300/120ns）；Fm+ 的 Cb 上限也更宽（550pF），代入后自然更严。TI SLVA689 同式
- **HS-mode（3.4MHz）不适用本式**：上拉是电流源结构，Rp/Cb 要求按 UM10204 Hs-mode 章节人工核对；工具直接抛 `E_UNSUPPORTED`，不猜系数
- **Rp_min = (VDD − VOL) / IOL**，VOL=0.4V、IOL≥3mA（spec 规定的汲入电流下限）
- 各模式 tr_max/Cb_max：std 1000ns/400pF、fast 300ns/400pF、Fm+ 120ns/550pF、HS 40ns/100pF
- 依据：I2C-bus specification Rev7.0（NXP）、TI SLVA689
- 电容超上限时无解——任何上拉都救不回来，须缩走线/减挂载/降速率

## I2C 耗时（i2c-time）

- **t = ((n+1)×9 + 2) / f_bus**——每字节 9 位（8 数据+ACK），加地址字节，起始+停止约 2 位开销
- 依据：I2C-bus spec Rev7.0 帧结构

## CAN 位时序（can-bit）

- **F_baud = CLK / (BRP × TQ_total)**；**采样点 = (1 + TSEG1) / TQ_total × 100%**
- 段约束按芯片族（`--family`）：
  - **bxCAN**（F1/F4/F0/G0/L 经典）：TQ_total ≤ 25、TSEG1 ≤ 16、TSEG2 ≤ 8
  - **FDCAN**（G4/H7 等）：TQ_total ≤ 385、TSEG1 ≤ 256、TSEG2 ≤ 128
- 求解策略：**先遍历 BRP 找波特率精确整数解**（42M@500k 有 BRP=4/TQ=21、BRP=6/TQ=14 等），再对每个 t **枚举全部合法 (seg1,seg2)**；优先取落在 75-87.5% 且最接近目标的点，否则取最接近的合法点并判 FAIL。不能只试一个 seg1（10M@500k 目标 87.5% 时最优合法点是 85.0%，只试 round 会误判）
- 采样点合法窗 75-87.5%：依据 CiA 301（500k 及以上推荐 87.5%）；下限保传播段长度
- 波特率精度复用 2% 限（CAN 位级仲裁对精度更敏感，2% 已是宽限）

## ADC 源阻抗（adc-rad）

- **Rsrc_max = ts / (Cs × ln(2^(n+2))) − Radc**——采样电容充电到 1/4 LSB（N+2 位）所需时间常数，比 1/2 LSB 口径保守一档
- 默认 Cs=8pF（STM32 常见量级），**具体值随芯片家族差异大，以目标芯片 datasheet 为准**
- **Radc 片内采样开关电阻默认不扣**（输出明确写"未扣 Radc"）；给了 `--radc` 才从结果中扣减，负值按 0 处理
- 依据：ST datasheet 通式 `Rsrc_max = ts/(Cadc×ln(2^(N+2))) − Radc`

## RC（rc）

- **fc = 1/(2πRC)**——一阶低通 -3dB 定义

## SPI（spi）

- **SCK = FCLK / div**；div 必须为 2 的幂（多数控制器 2/4/.../256）

## 采样定理（nyquist）

- **fs ≥ 2 × fbw**（Nyquist–Shannon）；工程建议 5-10 倍（抗混叠滤波器滚降留裕量 + 重建质量）

## 死区占比（deadtime）

- **ratio = dt / (1/fsw) × 100%**；提示级阈值 5%（超过明显压缩有效占空比）
- 死区与 SVPWM/有效矢量时间的配合属电机控制深水区 → 转电机控制专家

## FPGA（fpga-uart / fpga-slack / fpga-pwm）

- **UART**：N = round(CLK/Baud)，整数分频有固有误差；理想分频小数部分大时提示分数分频/换时钟
- **Slack = Tclk − (Tco + Tlogic + Troute + Tsu)**，静态时序分析通式；slack ≥ 0 通过，<1ns 提示 PVT 跨角漂移风险；Fmax = 1/总延时
- **PWM 位深 = log2(CLK/fpwm)**；<8 位（256 级）判不合法——占空比台阶/啸叫；中心对齐（上下计数）有效位深减半，电机语境转电机专家

## 看门狗（wdg）

- **Tout = Presc × Reload / Clk**——IWDG 通式（独立 RC 振荡器口径，STM32 LSI 40kHz）
- 配套纪律：喂狗周期 < 超时 60%（防任务抖动）；喂狗点放主循环不放中断（中断卡死时看门狗要能救）；WWDG 有窗口下限，喂太早也复位
- 依据：STM32 RM0090/RM0440 IWDG 章节

## PLL（pll）

- **f_VCO = Clkin/M × N**；**f_out = f_VCO/P**
- 判定：VCO 必须落在合法窗（默认 100-200MHz，F4 实为 100-432MHz——**以目标芯片 datasheet 为准**，--vcomin/--vcomax 可传）
- M 的取值让 Clkin/M 落在 1-2MHz（spec 输入范围）；P 通常 {2,4,6,8}
- 依据：STM32 RM0090（F4）/RM0440（G4）主 PLL

## 分压电阻（divider）

- **Vout = Vin × R2/(R1+R2)**
- **给分压电流 I（`--iua`）时**：R_total = Vin/I、**R2 = Vout/I**、**R1 = (Vin−Vout)/I**；R1/R2 各自就近取 E24 标称后复算实际 Vout（不是只把总阻当 R1）
- **未给电流时**：R2 取 10k 基准，R1 = R2×(Vin−Vout)/Vout，再 E24 就近并复算
- 标称值不是连续的，误差常被忽略；复算结果以实际 Vout 与误差给出
- 提示链：高阻省电但噪声大 → ADC 口要联查 adc-rad 的源阻抗上限；采样保持电流会让高阻分压读数偏低

## NTC 测温（ntc）

- **R(T) = R25 × exp(Beta × (1/T − 1/T0))**，T 为开尔文，T0=298.15K（25°C）
- Beta（两参数）模型精度 ±1°C 量级；要 ±0.1°C 用 Steinhart-Hart 三系数
- 分压采样建议 NTC 放下臂：高温段阻值下降快，分辨率集中在关注区间
- 依据：Beta 模型（datasheet 通常给 25/50°C 或 25/85°C 两点 Beta）

## RC 建立时间（rc-settle）

- **t_settle = ln(2^nbits) × RC**——RC 阶跃响应 e^(−t/RC) 达到 n 位精度（残差 2^−n）
- 用途：分压+RC+ADC 采样链路里，保证采样窗 ≥ 5×t_settle；与 adc-rad 联查

## 晶振 ppm 漂移（ppm）

- **Δf = f × ppm/1e6**；对 UART 误差的贡献 = ppm/1e4 %
- 双端通信最坏叠加 2×ppm；对照 uart 计算器的 2% 上限——HSI ±1%（10000ppm）直接爆表，这正是 pitfalls 里"HSI 当晶振"坑的量化依据
- 常见值：晶振 ±20ppm、TCXO ±2ppm、HSI/RCO ±0.5%~1%

## FPGA 扩展（fpga-i2c / fpga-debounce / fpga-cdc / fpga-fifo）

- **行为级 I2C（fpga-i2c）**：SCL = CLK/(clk_div×2)——行为级实现每半位计 clk_div 个时钟。I2C 是同步协议、时钟由主控产生，容忍度远高于 UART（10% 提示线）。上板后 SCL 上升沿由开漏+上拉决定，RC 用 i2c-rp 算
- **消抖（fpga-debounce）**：cycles = CLK × T_debounce。两种实现：计数器（位数 = ceil(log2(cycles+1))）或移位寄存器（连续 N 个采样一致才翻转）。**采样前先过 2 级触发器防亚稳态**（外部按键异步进入，这是 FPGA 第一坑）
- **跨时钟域（fpga-cdc）**：无统一公式，纪律清单——单 bit 用两级同步器；多 bit 用握手/异步 FIFO；计数器跨域用格雷码；每域独立异步复位同步释放；用综合工具的 CDC 报告（Vivado report_cdc）兜底。依据：Cummings 经典论文系列（Clock Domain Crossing）
- **异步 FIFO 容量（fpga-fifo）**：稳态条件 out_rate ≥ in_rate（不满足则深度再大也溢出，必须提读速/流控）；突发条件 burst ≤ depth；排空时间 = burst/out_rate。FIFO 指针跨域用格雷码。依据：Cummings（Simulation and Synthesis Techniques for Asynchronous FIFO Design）

## 维护纪律

- 新增阈值：先加 assets/thresholds.json（带 source）→ 再在本文档补推导 → demo 加已知答案回归用例
- 公式有出入时，以官方 spec/datasheet 为准修正本文件与 thresholds.json 的 source 字段

## 常用平台扩展 II（rtc-drift / usb-clk / battery / modbus-silence / flash-wear / spi-time / sensor-lsb）

- **RTC 走时（rtc-drift）**：日误差 = 86400 × |ppm|/1e6（32.768kHz 表晶 ±20ppm → ±1.73s/日）；ppm 允许负值，负=走慢。常年走时选 ±5ppm 晶振或软件补偿（32768 计数校准寄存器）
- **USB 时钟（usb-clk）**：USB FS 需精确 48MHz（12M×4 过采样，0% 容差）。求解：遍历整数分频 + 特判 /1.5（STM32 USBPRE 口径）；**整数可分 ≠ RCC 实际支持该分频**（PLLQ/USBPRE 档位以 RCC 章节为准）。不可整除则换 USB-friendly 主频（72/48/96/168）。USB 时钟错→枚举失败（trees usb 树）
- **RP2040 UART（rp2040-uart）**：BAUDDIV = clk_peri/(16×baud) = IBRD + FBRD/64；**IBRD 16 位整数、FBRD 6 位小数（0-63）**，不是 6.12 定点。FBRD 四舍五入到 64 时向 IBRD 进位并把 FBRD 置 0
- **电池续航（battery）**：hours = mAh × 0.8 / I_avg——8 折含低温/老化/放电平台。IoT 续航第一杠杆 = 睡眠 µA 级与工作 mA 级的占空比（pwr 树）
- **Modbus RTU 帧间隔（modbus-silence）**：silence = 3.5 字符 × 11 bit / baud（9600→4.01ms）；>19200 固定 1.75ms。帧内间隔超值会被拆包，帧间不足会粘连——RTOS 调度抖动高频踩坑
- **Flash 擦写寿命（flash-wear）**：两者都给时 erases/year = writes/year × record_bytes/page_bytes（按页擦除），life = endurance × pages / erases_per_year；缺 `--record` 按一次写入=一次擦除的保守口径并注明。片内典型 10K（F1/F4）/30K（G/L）；记录类必须页轮换（wear-leveling），不够则降频/批量写/外挂 FRAM
- **WS2812（ws2812）**：高电平必查 T0H≈300ns / T1H≈800ns（±150ns）；可选 `--t0l/--t1l` 查低电平（WS2812B 典型 T0L≈850ns / T1L≈450ns）。**未覆盖**：复位低电平 >50µs、型号差异（WS2812B-V5/SK6812 等以各自 datasheet 为准）
- **SPI 耗时（spi-time）**：t = bytes×8/SCK + 片选开销 ~2µs；与 i2c-time 对比——SPI 同字节快 8-40 倍（无地址/ACK 开销），CS 频繁切换时开销不可忽略
- **传感器分辨率（sensor-lsb）**：value = raw × span/2^nbits；**默认双极性 span=2×FSR**（accel ±2g 档 16384 LSB/g，8192→0.5g），单极性用 `--unipolar` 时 span=FSR。量程与分辨率跷跷板，档位系数用错是高频错误
