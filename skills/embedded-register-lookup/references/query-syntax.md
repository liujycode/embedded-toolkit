# 查询语法与输出字段

所有子命令都支持：`--svd`、`--chip`、`--project-dir`、`--format text|json`、`--out`。

## 查询路径

```
外设.寄存器.位域
外设->寄存器            （与点号等价）
外设.簇.寄存器           （簇内寄存器，例如 DMA1.CH1.CCR）
```

- 大小写不敏感：`usart1.cr1.ue` 与 `USART1.CR1.UE` 相同。
- 寄存器名和位域名相同时（如 `TIM1.CNT`），两层都存在时优先按寄存器解析；要查位域请写全 `TIM1.CNT.CNT`。
- 只写到外设（`USART1`）返回全部寄存器；只写到簇（`DMA1.CH1`）返回簇内寄存器。

## 子命令

| 子命令 | 作用 | 示例 |
|---|---|---|
| `lookup <路径>` | 查外设、寄存器、位域 | `lookup USART1.CR1.UE` |
| `addr <地址>` | 地址反查 | `addr 0x4001380C` |
| `search <关键词>` | 按名称或描述搜索，`--limit` 控制条数 | `search baud --limit 20` |
| `decode <寄存器> <值>` | 按位域解码寄存器值 | `decode RCC.CR 0x00040002` |
| `list` | 列出全部外设、基地址、派生关系 | `list` |

`decode` 的参数必须是寄存器，给位域会返回 `E_INPUT_INVALID`。

## 地址反查的四种结果

| `kind` | 含义 |
|---|---|
| `exact` | 地址正好是一个或多个寄存器的起始地址（别名时可能有多个） |
| `inside_register` | 地址落在某寄存器内部，`offset_in_register` 为字节偏移 |
| `gap` | 在某外设范围内，但前面最近的寄存器之后没有定义寄存器（多为保留区） |
| `unmapped` | 不在任何外设地址范围内 |

## JSON 信封

```json
{
  "ok": true,
  "tool": "embedded-register-lookup",
  "version": "1.0.0",
  "results": [ { "kind": "...", "label": "已核验", "source": { ... } } ],
  "warnings": [],
  "errors": []
}
```

失败时 `ok` 为 `false`，`errors[0]` 含 `code`、`message`、`hint`，部分错误还有 `details`：

| 错误码 | `details` 字段 |
|---|---|
| `E_SVD_NOT_FOUND` | `tried`：已尝试的位置列表 |
| `E_SVD_PARSE` | `line`、`column` |
| `E_PERIPH_NOT_FOUND`、`E_REG_NOT_FOUND`、`E_FIELD_NOT_FOUND` | `suggestions`：最接近的候选名 |
| `E_INPUT_INVALID` | 无 |
| `E_INTERNAL` | 无（请附上输出提交 issue） |

## 寄存器结果字段

`register` 对象：`name`、`offset`（如 `0x0C`）、`address`（如 `0x4001380C`）、`size`（位宽）、`access`、`reset`（十六进制，宽度随位宽）、`reset_mask`、`description`。

`fields` 数组每项：`name`、`bits`（单比特写作 `5`，多比特写作 `15:0`）、`lsb`、`msb`、`width`、`access`、`reset`（该字段的复位值，十进制）、`description`、`enums`。

`enums` 每项：`name`、`value`、`pattern`（二进制图样，`x` 表示任意值）、`description`。

## 证据标签

| 标签 | 本技能何时输出 |
|---|---|
| 已核验 | 结果直接来自 SVD |
| 需查手册、需实测、未判定 | 本技能不输出（解码的未定义位用 `undefined_bits` 字段表示，不打标签） |
