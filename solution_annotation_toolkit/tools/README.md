# NDJSON 逐行中文注释工具

这个工具读取 Lean 内核导出格式 `3.1.0` 的 NDJSON，将每条记录对应的中文解释写在原始记录上一行。它用于本次 `solution.ndjson.zst` 的完整注释交付，保留原记录的字节、顺序以及原有换行。

它解释序列化记录及其引用关系，不执行 Lean 内核的类型检查，也不把表达式节点自动解释为独立的数学证明步骤。

## 编译依赖

- 支持 C++17 的 `g++`，以及 POSIX 文件和 `mmap` 接口。
- OpenSSL 的 `libcrypto` 库与开发头文件。
- Zstandard 的 `libzstd` 库与开发头文件；下面的输入解压命令还需要 `zstd` 命令行程序。
- 附带的 simdjson `3.9.4` 单文件版本：`vendor/simdjson.h` 与 `vendor/simdjson.cpp`。来源、SHA256 和许可证见同目录的 `PROVENANCE.json` 与 `LICENSE.simdjson`。

在本工具目录执行：

```bash
g++ -O3 -DNDEBUG -std=c++17 -pthread \
  annotate_ndjson.cpp vendor/simdjson.cpp \
  -lzstd -lcrypto -o annotate_ndjson
```

最终交付版本的源码和可执行文件哈希见 `engine_build_info.json`。可执行文件适用于本次构建的 Linux 环境；其他环境可从源码重新编译。

## 输入与输出格式

程序从标准输入读取未经压缩的 NDJSON。每条输入记录输出为：

```text
-- @line 123 E45：函数应用，以E12为函数、E13为实参。
{"app":{"arg":13,"fn":12},"ie":45}
```

以上数字只示范格式。真实注释使用该原行的实际行号、字段值与引用编号。

- `N` 表示名称表；`N0` 是匿名名称。
- `L` 表示宇宙层级表；`L0` 是零层级。
- `E` 表示表达式表；表达式表没有隐含预定义条目，当前来源从 `E0` 开始。
- 三种编号分别编号，不能混为一张表。`bvar` 的数字是 de Bruijn 绑定索引；`proj.idx` 是从零开始的字段序号，两者都不是 `E` 引用。
- 每条注释以一个 LF 结束；下一条原始记录逐字节保留，包括其 CRLF 或 LF。如果最后一条原始记录没有末尾 LF，工具也不补上。
- 注释内的控制字符、Unicode NEL 及行/段分隔符转成可见转义，原始 JSON 不改写。特别长的 `natVal` 或 `strVal` 可能在注释中显示标明长度的预览，完整值始终保留在紧随其后的原行。

带注释的 `.txt` 文件不再是 NDJSON，也不是 `.lean` 源码。移除各条 `-- @line ...` 注释行即可恢复原始 NDJSON；严格的还原与校验应使用随交付提供的独立验证工具。

## 本次来源的完整处理示例

输入原件来自：

<https://math.mit.edu/~drew/grh/solution.ndjson.zst>

以下示例在包含 `source/solution.ndjson.zst` 和 `tools/annotate_ndjson` 的工作目录执行。`state` 和 `annotated_parts` 必须不存在或为空。

```bash
set -o pipefail
zstd -dc --long=30 source/solution.ndjson.zst 2>decompress.log |
  tools/annotate_ndjson \
    --state-dir state \
    --output-dir annotated_parts \
    --summary annotation_summary.json \
    --level 1 --workers 2 --shard-mib 320 \
    --expected-bytes 61570595788 \
    --expected-sha256 5ea74b912147c5c93cc2b6d70cc727cf908df2f62ac6a20480a3fa02f6be244e \
    2>annotation_progress.jsonl
```

这是流式处理：程序不把约 61.57 GB 的原文或整张表达式图写成中间文件。名称的父节点和组件写入 `state/names.idx` 与 `state/names.utf8`，以便在名称和声明行显示完整名称；表达式和层级通过编号范围验证引用。

原始 zstd 输入帧使用 1 GiB 窗口，因此解压示例启用了 `--long=30`。输出的每个压缩分卷都是可以单独解压的完整 zstd 帧，按完整原始记录切分。

## 参数

| 参数 | 含义 |
| --- | --- |
| `--state-dir DIR` | 必填；名称组件索引的工作目录，须新建或为空。 |
| `--summary FILE` | 必填；全部成功后写入总体 JSON 摘要。 |
| `--output-dir DIR` | 分卷输出目录，须新建或为空。 |
| `--stdout` | 把未压缩的注释文本写到标准输出，替代分卷输出；适合小样本。 |
| `--level N` | zstd 压缩级别，默认 `1`。 |
| `--workers N` | zstd 压缩工作线程数，默认 `2`。 |
| `--shard-mib N` | 每卷达到的压缩字节阈值，默认 `320` MiB；在一个完整缓冲块结束后切分，实际卷会略大于阈值。 |
| `--max-lines N` | 只处理前 N 条记录，用于样本基准；摘要明确标记输入未全部消费。 |
| `--expected-sha256 HEX` | 完整输入必须匹配的原始 NDJSON SHA256。 |
| `--expected-bytes N` | 完整输入必须匹配的原始 NDJSON 字节数。 |

默认分卷阈值留有余量。若任何最终压缩卷超过 `400` MiB，程序报错，不将该卷标为完成。

## 分卷与验证清单

输出文件名为 `solution_annotated.part001.txt.zst`、`part002` 等。正在写入的文件带 `.partial` 后缀；结束压缩并完成本卷哈希后才改为最终文件名。

`parts.jsonl` 每卷一条 JSON，固定包含九个字段：

| 字段 | 含义 |
| --- | --- |
| `file` | 本卷文件名。 |
| `first_line` / `last_line` | 该卷覆盖的原始行号，首尾均包含。 |
| `records` | 原始记录数，应等于 `last_line - first_line + 1`。 |
| `original_bytes` / `original_sha256` | 从该卷移除注释后恢复的原文长度与 SHA256。 |
| `annotated_bytes` | 本卷解压后的带注释文本字节数。 |
| `compressed_bytes` / `compressed_sha256` | 实际压缩分卷长度与 SHA256。 |

各卷的原始行号区间连续，不能重叠或遗漏。总体摘要另外记录原文总长度、SHA256、各记录类型数量、三张表的定义数量、输出压缩总大小、耗时与完成状态。源输入截断、未知记录类型、未知字段、错误字段类型或引用错误都会使程序以非零状态退出。

`success: true` 只表示本程序完成了其解析、注释和完整性检查；它不是 Lean 证明验证成功的断言。独立验证器应再次从最终分卷恢复原文并核对官方原文长度和 SHA256。

## 格式约束与语义边界

本实现覆盖格式 `3.1.0` 的 24 种顶层记录。它针对本次官方文件所采用的连续索引分配方式，要求名称和层级从 1、表达式从 0 连续编号；所有名称、层级、表达式表引用必须指向已定义编号。常量引用的名称已存在，不表示该名称所指的声明必须已经出现。

数值 ID、序号和计数字段由无符号 64 位整数读取，超界时失败；`hints.regular` 另按格式限制到 UInt32。`natVal` 本身保留任意长度的十进制字符串。此程序不声称支持所有可能的、索引分配不同的第三方导出文件。

注释特别区分以下语义：`all` 是同组名称而非依赖全集；`def.hints` 是展开优先级提示；`letE.nondep` 是 elaborator 标记；归纳类型的 `isReflexive` 涉及构造器接受返回该类型的函数；递归器的 `k` 是 K-like 归约标记。详细字段依据与固定版本的官方源码记录在本次交付的格式说明中。
