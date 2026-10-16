# 回归集（真实误报案例）

按规格 §2.8：每一个在真实代码上出现的误报案例，修掉之后把对应的最小复现文件
放到本目录（`<id>.c`），每次发版必须全部通过（0 条“报”）。

- 判定入口：`python tools/verify_bench.py check`（含回归集检查），
  或 `python -m pytest tests/test_verify_bench.py::test_regress_corpus_clean`。
- 文件要求：只保留最小复现所需的代码；可以在文件头注释里写清来源与当时
  误报的规则（E0x）与信息。
- 说明：四个 Agent 的真实代码试跑（`benchmarks/verify-dogfood.md`）中的误报
  已全部修掉；修完的最小复现会逐步补入本目录。
