# 知识检索评测（embedded-debug-trees / embedded-peripheral-pitfalls）

用例 = 真实症状/场景查询 + 期望命中的树或坑位（注入式，逐条 ground truth）；
被测实现 = 技能脚本里的检索函数本体（import 复用，测的就是分发代码）。

| 技能 | 用例 | 命中 | 召回 |
|---|---|---|---|
| embedded-debug-trees（按树） | 52 | 52 | 100.0% |
| embedded-peripheral-pitfalls（按坑位） | 68 | 68 | 100.0% |
| **合计** | **120** | **120** | **100.0%** |

口径：查询经技能自带 tokenize + 同义词 + 反向关键词匹配后，期望的树/坑位出现在命中列表（任意排名）即为命中。
