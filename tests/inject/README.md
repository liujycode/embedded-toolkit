# 注入集（核验器召回率量化的 ground truth）

- **生成方式**：`python tools/verify_bench.py generate`（幂等；本目录文件与
  `manifest.json` 都是生成物，请勿手改）。
- **内容**：每类注入 ≥ 20 处，对应规则 E01–E10。单文件多注入的规则见
  `<rule>_injections.c`；E07/E09 是文件级判定，一例一文件（`e07-NN.c` / `e09-NN.c`）。
- **ground truth**：`manifest.json` 中每条 `{id, rule, file, line}`——期望该文件
  该行触发该规则（类别与行号都要命中，见 `tools/verify_bench.py check`）。
- **判定**：`python tools/verify_bench.py check`（CI 同款；召回目标见规格 §2.8：
  E01–E06/E08–E10 ≥ 90%，E07 ≥ 80%）。结果快照见 `benchmarks/verify-recall.md`。
- **芯片**：全部针对合成芯片 SYNTH32（`tests/fixtures/synthetic.svd`，自编，
  非厂商数据），只依赖 SVD，不需要真实硬件。
