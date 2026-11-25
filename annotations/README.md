# 注释分卷：Release 下载清单

本目录保存 57 卷注释数据的说明和公开清单。**完整注释正在分卷展开为普通 TXT 文件，实际完成范围以 [unpacked/](unpacked/) 和其进度清单为准。原 Release 的压缩附件作为备份保留。**

- [全部 Release 附件](https://github.com/liyiliuxingyu/riemann-lean-archive/releases/tag/archive-20261122)
- [57 卷逐卷下载地址、行号范围、大小和 SHA-256](release-parts.json)
- [展开的注释工具包：读取工具、格式说明、预览和验证报告](../solution_annotation_toolkit/)
- [可单独下载的 TXT 样本：原始前 147,492 条记录及注释，22,791,733 字节](../solution_annotation_toolkit/benchmark/prefix_output_v2/solution_annotated.part001.txt)

这个 TXT 是工具包的测试样本，不是完整 Release 第 1 卷。原始工具包 ZIP 继续保留在 Release 供完整归档下载。

## 数据规模与入库范围

| 内容 | 数量或大小 |
|---|---:|
| 独立 Zstandard 压缩卷 | 57 |
| 原始 NDJSON 记录 | 1,080,769,508 条 |
| 解压后的注释文本物理行 | 2,161,539,016 行 |
| 解压后的注释文本 | 168,547,118,127 bytes，约 156.972 GiB |
| 57 卷压缩附件合计 | 18,876,901,037 bytes，约 17.580 GiB |
| 去除注释后的原始 NDJSON | 61,570,595,788 bytes |

**57 卷各自解压后的文本全部超过 100 MiB。**最小的第 57 卷为 337,139,153 bytes，最大的第 29 卷为 3,732,963,027 bytes。这里比较的是解压文本大小；压缩附件的大小另列在清单中。

把文本继续拆成每文件严格小于 100 MiB 的片段，可以满足这一单文件大小预算，但数据总量仍约为 156.972 GiB。按最大 104,857,599 bytes、保留原有 57 卷边界计算，任意字节拆分精确需要 1,640 个文件；允许跨卷合并再拆分时，理论最少为 1,608 个文件。若保留完整行或“注释＋原始记录”对，这些数值只是下限，实际文件数需要在流式拆分时确定。

这是一组规模很大的文本数据。拆分不会减少正文总量；Git 对象、打包、推送和克隆的实际成本需要另行评估，不能从 zstd 压缩大小直接推算。当前全量展开工作使用 48 MiB 整记录对分块，实际数量及完成范围见 [unpacked/](unpacked/)；上述数字仅是旧的大小规划下限。

## 下载并解压一卷

各卷可独立解压。先下载需要的卷，例如 [第 1 卷](https://github.com/liyiliuxingyu/riemann-lean-archive/releases/download/archive-20261122/solution_annotated.part001.txt.zst)，并按 [公开清单](release-parts.json) 核对其压缩字节数和 SHA-256。解压需要已安装 `zstd`。

在保存该压缩文件的目录运行以下 Bash 命令。`noclobber` 会在目标文本已存在时拒绝写入，避免覆盖已有文件：

```bash
(
  set -o noclobber
  zstd --decompress --stdout -- solution_annotated.part001.txt.zst > solution_annotated.part001.txt
)
```

正常完成后，第 1 卷文本应为 **2,776,654,701 bytes**，包含原始第 **1–18,288,865** 条记录及各自注释。解压过程中若失败，可能留下不完整的输出文件；应检查命令退出状态和文件大小，再使用输出。

## 行号的含义

每条原始 NDJSON 记录之前有一行以 `-- @line 原始行号` 开头的中文注释，随后的一行是保持原有字节的 JSON 记录。`@line` 和清单中的 `first_line`、`last_line` 都是**原始 NDJSON 从 1 开始的记录行号**，并且跨 57 卷连续；它们不是解压文本的物理行号。

因此，原始第 1 条记录对应注释文本的前两行；每条记录通常产生一行注释和一行 JSON，本数据的完整回验确认每条记录均具有这一结构。全量原始记录为 1,080,769,508 条，带注释文本则为 2,161,539,016 个物理行。

这些行号用于定位导出的名称、宇宙层级、表达式或声明等数据记录，不是数学证明的步骤编号。带注释的 `.txt` 也不是可直接输入纯 NDJSON 读取器的数据；恢复原始 NDJSON 可使用工具包中的读取及验证工具。

## 清单来源与验证范围

本目录的 [release-parts.json](release-parts.json) 整理自仓库的 [原始分卷元数据](../ndjson-files.public.json)、[Release 附件清单](../release-assets.public.json)，以及注释工具包中的 `parts.jsonl` 和 `independent_verification.json`。下载地址取自已记录的实际 Release 附件地址。

存档的完整验证报告记录了 57 个独立压缩帧、所有压缩卷 SHA-256、逐卷字节数和记录数、连续原始行号，以及恢复原始数据的整体 SHA-256。这里引用该完整回验记录，没有把本次清单整理表述为重新解压全部数据或执行 Lean 内核验证。

现有完整回验报告没有记录全量最大行长；清单将该值保留为空，不以小样本推断全量最大值。
