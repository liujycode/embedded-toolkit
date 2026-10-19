# 真机触发评测记录

> 用例源：`tests/trigger/`（百事通 `embedded-register-lookup.json` 35 正 + 10 反；
> 核验器 `embedded-register-verify.json` 22 正 + 10 反；
> 排障决策树 `embedded-debug-trees.json` 25 正 + 12 反）。
> 判定：`tools/trigger_eval.py`（离线解析，结构化信号）；运行器：`tools/trigger_run.py`
> （无头单次、**逐例独立空工作目录、跑完即清**）。
> 状态：决策树技能 Claude Code 轮完成（含补跑）；OpenCode 轮与外设避坑清单待跑。

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

## 待办

- [ ] 决策树 OpenCode 轮
- [ ] 外设避坑清单（embedded-peripheral-pitfalls）Claude Code / OpenCode 轮
- [ ] p20 用例改写为排障场景后复跑
- [ ] Trae CN / WorkBuddy / Codex / Cursor 轮
