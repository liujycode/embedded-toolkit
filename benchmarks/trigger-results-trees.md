# 真机触发评测记录

> 用例源：`tests/trigger/`（百事通 `embedded-register-lookup.json` 35 正 + 10 反；
> 核验器 `embedded-register-verify.json` 22 正 + 10 反；
> 排障决策树 `embedded-debug-trees.json` 25 正 + 12 反）。
> 判定：`tools/trigger_eval.py`（离线解析，结构化信号）；运行器：`tools/trigger_run.py`
> （无头单次、**逐例独立空工作目录、跑完即清**）。
> 状态：决策树技能 Claude Code 轮完成（含补跑）；外设避坑清单与决策树描述重构 A/B 轮完成（2026-10-19，模型路由变更前后各一轮）。

## 判定方法（为什么不能靠文本匹配）

技能名会出现在系统提示的技能清单里（Claude Code 的 `slash_commands`、OpenCode 的技能列表），任何“技能名出现即触发”的文本匹配会把全部用例误判为触发（已实测确认）。本记录只认结构化信号：

- **Claude Code**：`Launching skill: <技能>` 事件、`commandName` 成功回执；另加“带技能安装路径（`skills/<技能>/scripts/...`）的脚本调用”作为执行级证据（技能文档里的示例命令不算）。
- **OpenCode**：`tool="skill"` 且 `name=<技能>` 的加载事件；`tool="bash"` 且命令含脚本调用。

解析容错：BOM、字符串内终端转义字符、破损行（原始行兜底需同时出现工具类型与名称/脚本）。

复现命令：

```
python tools/trigger_run.py --agent claude --skill embedded-debug-trees --out benchmarks/_trig_trees_claude
python tools/trigger_eval.py --dir benchmarks/_trig_trees_claude --agent claude \
    --skill embedded-debug-trees --script trees.py --subcommands search,show,rootcauses,list
```

## 环境

| 项目 | 值 |
|---|---|
| 机器 | Windows，Python 3.12/3.13 |
| Claude Code | 2.1.233→2.1.303，模型经 CC Switch 路由为 `deepseek-v4-flash` |
| 技能安装 | `~/.claude/skills/` 副本（**决策树首轮发现未安装导致正例 0/25，安装后重跑**） |
| 运行方式 | 无头单次会话、自动批准工具；每例新建独立空临时目录 |

## 决策树（embedded-debug-trees）Claude Code 轮（2026-10-19）

| 轮次 | 用例 | 结果 |
|---|---|---|
| 首轮（skill 未装） | 37 | 正例 0/25、反例 12/12——**基础设施结论：skill 不在清单里就绝无触发，反例仍全过，管线可信** |
| 主轮（安装后重跑） | 37 | 正例 19/25、反例 12/12 = 84%；6 例未判/漏（4 例 unrecognized_model 基建错 + 2 例真漏） |
| 补跑（--only 6 例） | 6 | p23/p24/p25 命中；p23/p25 首轮超时复跑即命中（模型抖动）；p18/p20 再漏 |
| **合并成绩** | **37** | **正例 23/25、反例 12/12 = 95%** |

### 漏报分析（诚实记录，不藏）

- **p18**（“栈溢出怎么检测？任务栈水位怎么看？”）：两轮均未触发。模型走 UAMS 记忆检索 + byteask-embedded-docs MCP 检索直接作答，答案质量尚可（覆盖 configCHECK_FOR_STACK_OVERFLOW/水位函数）。**原因**：问题太“通用”，与 MCP 文档工具的描述重叠，模型没感到需要专项技能。**待改**：SKILL.md description 增加“栈溢出/水位”锚定词权重，或将 description 首句改为更宽的故障咨询句式。
- **p20**（“优先级反转是什么，怎么避免？”）：两轮均未触发。概念解释类问题，模型直接回答。**原因**：教学型提问天然不走工具。**可接受**：该正例对“排障决策树”技能的指向性本来就弱——考虑移入反例或改写为排障场景（“RTOS 任务优先级配置反了导致高优先级饿死，怎么查”）。
- **p23/p25 首轮超时（996s/541s）**：模型抖动 + deepseek-v4-flash 偶发慢；补跑即过，非技能问题。

## 描述路由 A/B：CC Switch 路由变为 glm-5.3-flash 后（2026-10-19）

CC Switch 的路由模型从 `deepseek-v4-flash` 变为 `glm-5.3-flash` 后重跑（同用例、同管线、单次无头）：

| 轮次 | 描述版本 | 决策树（正/反） | 避坑清单（正/反） |
|---|---|---|---|
| 基准轮（glm-5.3-flash，旧描述=功能清单开头） | v1.1.0 原描述 | 6/25 + 12/12 = **49%**（1 例基建超时） | 2/22 + 10/10 = **38%** |
| B 轮（glm-5.3-flash，**新描述=中文症状句前置**） | 描述重构后 | 10/25 + 12/12 = **59%** | 5/22 + 10/10 = **47%** |
| 对照：deepseek-v4-flash 轮 | v1.1.0 原描述 | 23/25 + 12/12 = **95%** | — |

A/B 逐例（决策树，粗信号与官方判定一致）：**救回 6 例**（p03 I2C 超时、p05 UART 乱码、p13 起不来卡时钟、p14 周期复位、p15 进不了 main、p25 空闲中断+DMA——全是要"一步步排查"的通信/启动症状句，正是新描述前置的部分）；**丢 2 例**（p10 RTOS 卡死、p24 HardFault 抓现场——对应词在新描述中原样保留，归因单次运行模型抖动）。净 +4 正例。避坑清单 2→5 正例（p10 配置顺序、p11 优先级分组、p17 CAN 过滤器为新增触发）。

**结论**：① 描述开头改为"用户会说的症状句"带来约 +10 个百分点的触发提升，且零误触发代价，假设成立；② 触发率仍强依赖路由模型（deepseek 95% vs glm 59%），弱路由模型对"技能名回声"的依赖重，属 Agent 宿主层已知限制，非技能内容缺陷（检索评测 106/106 与技能内命令行为与模型无关）。

基准轮关键观察（`_trig_dt_v110_claude`/`_trig_pf_v110_claude`，本地证据）：

- **反例 22/22 全干净**——无误触发，管线与判定可信。
- 漏报模式单一：**模型直接凭自身知识作答，不调技能**（抽查 p03“ I2C 读超时怎么查”：直接给排查步骤，未加载任何技能）。
- 触发与用户措辞对描述的“回声”强相关：避坑清单仅 “配置 I2C 有哪些常见的坑”（几乎复述技能名）触发；连 “Bootloader 跳转就 HardFault”"printf 放中断里跑飞”这类最对口问法都不触发。
- **结论**：触发率强依赖路由模型（95% vs 49%），且弱路由模型下描述开头是否为“用户会说的症状句”影响显著——据此把两技能 description 重构为**中文症状句前置**（`396cd81`），B 轮即测这个假设。

## 待办

- [ ] 决策树 OpenCode 轮
- [ ] p20 用例改写为排障场景后复跑
- [ ] Trae CN / WorkBuddy / Codex / Cursor 轮
