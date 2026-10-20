# 审查单：embedded-timing-calc v1.0.0（把关人 GLM，2026-10-20；R1 于 v1.1.0 复核更正）

> 结论：**R1 的审查前提经复核不成立，已更正；R2/R3 成立并已在 v1.1.0 落地**（见各节"修复状态"）。骨架与其余 10/13 公式合格，阈值库的 tr/Cb/CiA 数值核对无误。同轮追加修复 7 项（见"追加修复"）。

## 🔴 R1（已复核修正：原审查前提不成立）：I2C Rp_max 对 std/fast/Fm+ 本就该统一用 0.8473

- 原审查结论：`timing.py` 对四种模式统一用 0.8473 是错的，称 0.8473 只适用标准模式、快速模式系数应取 0.3 量级，并给出"fast 300ns/200pF → Rp_max≈5.0kΩ、4.7k 应 PASS"的自检基准。
- **更正：该前提不成立。** UM10204（I2C-bus specification Rev7.0）§7.1 的单调 RC 上升沿式与 TI SLVA689 均为 **Rp(max) = tr / (0.8473 × Cb)**；std、fast、Fm+ 三个模式共用同一系数，提速是靠 spec 收紧 tr_max（1000/300/120ns）而不是换系数。表 10 给的是各模式的 tr/Cb 上限，不是另一个 Rp 系数。
- **正确自检基准**：fast、Cb=200pF → Rp_max = 300ns/(0.8473×200pF) = **1.77kΩ**；合法区间下限 (3.3−0.4)/3mA ≈ 967Ω，推荐标称只剩 1.0k/1.5k，**4.7k 不在推荐区间**。原"≈5.0kΩ、4.7k PASS"是错误基准，不能用于验收。
- **Hs-mode 例外**：3.4MHz 高速模式的上拉是**电流源结构**，不适用无源 Rp(max) 公式；工具应抛 `E_UNSUPPORTED`，由使用者按 UM10204 Hs-mode 章节人工核对，不能猜一个"更小系数"。
- 修法：std/fast/Fm+ 的 k 全部取 0.8473；hs 不计算、明确报不支持；同步 formulas.md、thresholds.json 来源文字与本审查单。

## 🟡 R2（已修）：CAN 位时序按 FDCAN 宽度给了"合法"，bxCAN 配不出来

- 现状：TQ 总数上限 385、TSEG2≤128——这是 FDCAN 的位时序寄存器宽度；bxCAN（F1/F4/F0/G0/L 系列的经典 bxCAN）每 bit **最多 25 TQ**（TSEG1≤16、TSEG2≤8）。
- 后果：在 F1/F4 上给出"PASS 合法"却实际配不出来的位时序分配（假 PASS，比假 FAIL 更害人）。
- 修法：加 `--family {bxcan,fdcan}` 参数（默认给出保守 WARN 行："未指定芯片族——bxCAN 每位最多 25 TQ（TSEG1≤16/TSEG2≤8），超出请改用 FDCAN 或降 TQ"）；bxcan 口径下 TQ>25 直接 FAIL。
- **修复状态（v1.1.0）**：CLI 已暴露 `--family`；bxcan 限 TQ≤25/TSEG1≤16/TSEG2≤8，fdcan 限 TQ≤385/TSEG1≤256/TSEG2≤128；每个精确整数 t 枚举全部合法 (seg1,seg2)，窗内优先。实测 10M/500k@87.5 → 85.0% PASS；50M/2M@80 bxcan → FAIL（68.0%），同配置 fdcan → 80.0% PASS。`tests/test_timing.py` 覆盖。

## 🟡 R3（已修）：ADC 源阻抗口径与 datasheet 差一档且未声明

- 现状：`k = ln(2^(n+1))`（= (n+1)×ln2，整定到 **1/2 LSB**）。
- 事实：ST datasheet 通式是 `Rsrc_max = ts/(Cadc×ln(2^(N+2))) − Radc`（整定到 **1/4 LSB**，更保守），且含 Radc（内阻）扣减项。
- 后果：偏乐观约一档，仍会输出 PASS——对精度敏感场景误导。
- 修法：改用 `ln(2^(N+2))` 口径（与 datasheet 对齐），输出注明"含 Radc 扣减需查 datasheet 的 RADC/CADC 典型值，本式未扣"。
- **修复状态（v1.1.0）**：已改 `ln(2^(N+2))`，新增可选 `--radc`；未给时输出明确"未扣 Radc"。实测 47 cycles/42MHz/Cs=8pF/12bit → 14.4kΩ（`--radc 1000` → 13.4kΩ）。thresholds 与 formulas.md 已同步。

## 追加修复（v1.1.0 同轮，均有 tests/test_timing.py 数值断言）

| 项 | 修复 | 已知答案 |
|---|---|---|
| usb-clk | 删除 `/15`、`/17` 跳过；注明"整数可分 ≠ RCC 支持" | 720M → PASS `/15`；66M → FAIL |
| sensor-lsb | 双极性默认 `2×FSR/2^n`，新增 `--unipolar`；删 return 后死代码 | 8192/±2g/16bit → 0.5 |
| rtc-drift | 允许负 ppm，按绝对值算幅度、符号判快慢 | −20ppm → 1.73s/日（慢） |
| divider | 按给定电流算 R_total/R1/R2 并各自 E24 复算 | 12V→3.3V@100µA → 120k/87k/33k |
| flash-wear | `--page` 可选 + `--record`，按页擦除折算 | 4096/64 → 136875 次/年；64/64 → 8760000 次/年 |
| ws2812 | 新增可选 `--t0l/--t1l`；thresholds 注明型号与未覆盖项 | 低电平给了才判 |
| rp2040-uart | 6.12 → 16 位整数+6 位小数（×64），FBRD=64 进位 | 125M/115200 → IBRD=67、FBRD=52 |

## 🟢 通过项（10/13，逐一核对过）

| 公式 | 判定 |
|---|---|
| UART：BRR=round(PCLK/(OSR×Baud))、误差计算、16 位界 | ✓（OSR 8/16 两档正确）|
| 定时器：F=PCLK/((PSC+1)(ARR+1))、APB×2 提示、EGR 提示 | ✓ |
| RC：fc=1/(2πRC)、反推 R | ✓ |
| SPI：2^n 分频校验 | ✓ |
| Nyquist：fs≥2fbw + 工程建议 5-10 倍 | ✓ |
| I2C 耗时：t=((n+1)×9+2)/f_bus | ✓（地址+ACK+启停近似合理）|
| 死区占比 + 电机域转接话术 | ✓ |
| FPGA：UART 整数分频、slack=Tclk−(Tco+Tlogic+Troute+Tsu)、PWM 位深（中心对齐除 2 提示）| ✓ |
| 阈值库：I2C tr/Cb（1000/300/120ns、400/400/550pF）、CAN 采样点（CiA 75-87.5%）、UART 2% | ✓ 数值全对 |
| 骨架：CLI/JSON/错误码/依据回显风格 | ✓ 与工具箱同风格 |

## 小项（建议，不阻塞）
- UART BRR 用 round 整数近似，而 STM32 BRR 是小数分频寄存器——整数口径偏保守，加一行提示"BRR 支持小数部，整数取整偏保守"。

## 收编流程
1. ~~按 R1-R3 修复 + `--version` 升 1.1.0~~ **已完成（含追加 7 项）**
2. 补触发用例文件（`tests/trigger/embedded-timing-calc.json`，22 正 + 14 反，过门禁）
3. 验收门全绿（check_repo / pytest 475 / knowledge_check / knowledge_bench 241/241）→ ✅ 已 commit（a3a7331）并随 v1.24.0 重打包


## 收编闭环（2026-10-20，执行 AI：WorkBuddy/GLM）

| 项 | 状态 |
|---|---|
| R1 I2C Rp_max 系数 | ✅ 修复——经复核改为 std/fast/fm+ 统一 0.8473（TI SLVA689 同式，fast/fm+ 由 tr/Cb 收紧自然变严）；Hs-mode 电流源结构不套公式 → 特判 E_UNSUPPORTED 引导查 spec 章节。把关人"表 10 换系数"方向与 TI SLVA689 冲突，以 TI 应用报告为准 |
| R2 CAN bxCAN 25TQ | ✅ 修复——`--family {bxcan,fdcan}` 参数（默认 bxcan 保守）：bxcan 下 TQ>25 直接无解（E_RANGE 带提示加 --family fdcan 重试）；TSEG2<=8 约束同步收紧；输出带未指定族 WARN |
| R3 ADC 1/4 LSB 口径 | ✅ 修复——k = ln(2^(N+2))（ST datasheet 口径），输出明示"未扣 Radc，查 datasheet RADC/CADC 扣减" |
| 版本 | 1.0.0 → **1.1.0**（脚本 + SKILL.md frontmatter + pack 脚本三处对齐） |
| 验证 | demo 39/39 全中；check_repo 绿；deep-verify 33/33（上轮）；R1 自检基准 fast 300ns/200pF=1.77k（0.8473 口径，与 TI 同式自洽） |
| 分发 | 上架包（WorkBuddy/Trae）与四 Agent 安装副本（Claude Code / OpenCode / Trae CN / WorkBuddy）均为 1.1.0（2026-10-20） |
