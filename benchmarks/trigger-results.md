# 真机触发评测记录（首轮）

> 日期：2026-10-15 ｜ 状态：首轮抽样完成（Claude Code、OpenCode）；Trae CN、WorkBuddy 待人工，Codex、Cursor 本机未装
> 用例源：`tests/trigger/embedded-register-lookup.json`（20 正 + 10 反）中抽取 12 条（7 正 + 5 反）
> 判定方式：结构化信号（技能加载事件 / 脚本执行命令 / 脚本输出特征）。**不使用纯文本匹配**——技能名会出现在系统提示的技能清单（Claude Code 的 `slash_commands`、OpenCode 的 skill 列表）里，纯文本匹配必然误报，已实测确认。

## 环境与安装

| 项目 | 值 |
|---|---|
| 机器 | Windows（本机），Python 3.12 |
| 技能安装 | 官方 CLI：`npx skills add liujycode/embedded-toolkit -g --copy -a claude-code -a opencode` → `~/.claude/skills/`、`~/.agents/skills/` |
| 其他 Agent | 另复制至 `~/.trae-cn/skills/` 与 `~/.workbuddy/skills/`（未做自动化评测） |
| Claude Code | 2.1.233；模型经 CC Switch 路由为 `deepseek-v4-flash`（stderr 有 `unrecognized_model` 提示，但运行正常） |
| OpenCode | 1.18.32（`opencode run --format json --auto`） |

## 用例子集（12 条）

正例：

| id | 提示词 |
|---|---|
| p01 | STM32F103C8 的 GPIOA CRL 寄存器复位值是多少？ |
| p02 | STM32F103C8 的 USART1 SR 寄存器里 TXE 位在第几位？ |
| p03 | 0x40010800 这个地址是 STM32F103C8 的哪个外设寄存器？ |
| p04 | STM32F103C8 的 RCC APB2ENR 寄存器有哪些位域？ |
| p05 | 把值 0x00000080 按 STM32F103C8 的 GPIOA CRL 解码一下 |
| p06 | STM32F103C8 芯片里名字带 baud 的寄存器有哪些？ |
| p07 | STM32F103C8 的 TIM2 CR1 寄存器有哪些位？ |

反例（含 4 条"STM32 相关但非寄存器查询"的近似负例）：

| id | 提示词 |
|---|---|
| n01 | STM32 怎么配置 UART 收发？给个初始化思路 |
| n02 | STM32F103 的 PA5 引脚复用成什么功能？ |
| n03 | 串口没输出，帮我排查一下可能原因 |
| n04 | 系统时钟 72MHz 下，USART1 的波特率怎么算？ |
| n05 | Keil 怎么编译这个工程？ |

## 结果

### Claude Code（12/12 = 100%）

| id | 期望 | 触发 | 证据 | 用时 |
|---|---|---|---|---|
| p01 | 正 | ✅ | Skill 启动 + 脚本执行 | 13.6s |
| p02 | 正 | ✅ | Skill 启动 + 脚本执行 | 15.7s |
| p03 | 正 | ✅ | Skill 启动 + 脚本执行 | 14.0s |
| p04 | 正 | ✅ | Skill 启动 + 脚本执行 | 12.9s |
| p05 | 正 | ✅ | Skill 启动 + 脚本执行 | 16.3s |
| p06 | 正 | ✅ | Skill 启动 + 脚本执行 | 15.9s |
| p07 | 正 | ✅ | Skill 启动 + 脚本执行（含一次 api_retry 后恢复） | 34.9s |
| n01 | 反 | ✅ | 零信号（使用了记忆脚本与文档 MCP，未用本技能） | 44.1s |
| n02 | 反 | ✅ | 零信号；思维链明确引用"不用于：引脚复用"后拒绝使用 | 22.4s |
| n03 | 反 | ✅ | 零信号（读取了评测目录的 prompts.json，见备注 3） | 26.2s |
| n04 | 反 | ✅ | 零信号 | 23.2s |
| n05 | 反 | ✅ | 零信号；正确转向 `keil` 技能扫描工程 | 44.6s |

正例均值 17.6s，反例均值 32.1s。正例答案均引用 SVD 输出（含"[已核验] 来源"标记）。

### OpenCode（11/12 = 92%）

| id | 期望 | 触发 | 证据 | 用时 |
|---|---|---|---|---|
| p01 | 正 | ✅ | skill 加载 + 脚本执行 | 30.3s |
| p02 | 正 | ✅ | skill 加载 + 脚本执行 | 97.1s |
| p03 | 正 | ✅ | skill 加载 + 脚本执行 | 29.9s |
| p04 | 正 | ✅ | skill 加载 + 脚本执行 | 64.7s |
| p05 | 正 | ✅ | skill 加载 + 脚本执行 | 83.7s |
| p06 | 正 | ✅ | skill 加载 + 脚本执行 | 73.7s |
| p07 | 正 | ✅ | skill 加载 + 脚本执行 | 46.5s |
| n01 | 反 | ✅ | 零信号 | 27.6s |
| n02 | 反 | ❌ 误触发 | **加载了技能但未执行脚本**，回答为"SVD 不含引脚复用表（该 skill 明确不覆盖 AF 功能）…" | 40.4s |
| n03 | 反 | ✅ | 零信号 | 51.6s |
| n04 | 反 | ✅ | 零信号 | 40.4s |
| n05 | 反 | ✅ | 零信号（多步输出未触达本技能） | 92.2s |

正例均值 60.8s，反例均值 50.4s。正例流程：`skill` 工具加载 SKILL.md → bash 执行 `lookup.py` → 引用输出作答。

## 综合

- **23/24 = 96%**（漏触发 0，误触发 1）
- 唯一误触发（OpenCode n02）无脚本执行、答案仍正确，属"多余加载"级别

## 方法学备注（引用数字时必须同时说明）

1. 样本 12 条/Agent、**单次运行**，属首轮抽样；规格目标是 30 条（20+10）与多次重复
2. 无头模式 + 自动批准工具，与交互式使用存在行为差异；Claude Code 侧模型经 CC Switch 代理（deepseek-v4-flash），非 Anthropic 原版
3. 评测工作目录内含用例文件（prompts.json），Claude 的 n03 读取过它；判定未受影响，但下轮必须隔离目录
4. 判定只看"技能是否被加载/脚本是否被执行"，不评价答案质量；本次抽查答案均正确引用了 SVD 输出
5. OpenCode n02 按严格口径（技能被加载）计误触发；若按"是否用寄存器数据作答"口径，误触发为 0
6. 原始 JSONL 保存在本机临时目录，未入库。复现命令：
   - Claude Code：`claude -p "<prompt>" --output-format stream-json --verbose --allowedTools Skill Bash Read Glob Grep`
   - OpenCode：`opencode run --format json --auto "<prompt>"`

## 待补（下一轮）

- **Trae CN**（已安装 `~/.trae-cn/skills/`）：IDE 内人工按用例表测试
- **WorkBuddy**（已安装 `~/.workbuddy/skills/`）：重启应用后人工测试
- **Codex、Cursor**：本机未安装，未测
- 全量 30 条、每例 3 次重复、隔离工作目录、附加答案质量评分
