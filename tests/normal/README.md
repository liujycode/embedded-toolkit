# 正样本集（核验器误报率量化的语料）

- **生成方式**：`python tools/verify_bench.py generate`（幂等；本目录文件与
  `manifest.json` 都是生成物，请勿手改）。
- **内容**：54 个不含注入的文件（自写标准初始化 + 常见写法：寄存器直写、
  CMSIS 宏、RCC/HAL 时钟使能、读状态轮询、局部指针、HAL 调用、内核外设写等）。
- **预期**：每个文件 0 条“报”。“未判定”（内核外设、簇命名、HAL 调用）与
  “芯片默认”（写入等于复位值）不视为误报，单独统计（见 `benchmarks/verify-recall.md`）。
- **判定**：`python tools/verify_bench.py check`；阈值：报文件占比 ≤ 5%（规格 §2.8）。
- **芯片**：合成芯片 SYNTH32（`tests/fixtures/synthetic.svd`，自编，非厂商数据）。
