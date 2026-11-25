# Release 内容展开记录

日期：2026-11-23。原 Release：[archive-20261122](https://github.com/liyiliuxingyu/riemann-lean-archive/releases/tag/archive-20261122)。

> 后续更新：2026-11-25 将两份审计 ZIP、CTeX 源码归档及小型嵌套压缩内容继续展开，见[独立文件说明](INDIVIDUAL_FILES.md)。本页下列数量和校验记录描述 2026-11-23 的归档布局；当前 Git 中的 CTeX 源码归档已由其全部展开文件替代。

<!-- full-annotation-completion-note -->
> 当前状态：57 卷完整注释已全部展开为 **3,380 个独立 TXT 文件**，合计 **168,547,118,127 字节**，覆盖 **1,080,769,508 条原始 NDJSON 记录**。现可[直接浏览与下载全部 TXT](../annotations/unpacked/)，详细统计见[完成清单](../annotations/unpacked/progress.json)。原 Release 附件保留。下列正文仍记录 2026-11-23 的归档布局与当时的核验范围；其中“尚未入库”等表述只描述历史状态。
<!-- /full-annotation-completion-note -->

## 已放入普通 Git 的内容

| 原始内容 | 仓库路径 | 处理结果 |
| --- | --- | --- |
| 完整工程 ZIP 中的 267 个常规成员 | `project/` 原有成员 | 与 ZIP 全部逐文件比对一致，保留原字节 |
| `RH_AllSources.lean` 中的原始模块与配置 | `project/lean/original/` | 恢复 175,187 个 Lean 模块及 3 个配置；保留相对路径 |
| ZIP 内 `RH_AllSources.index.jsonl` | `project/lean/RH_AllSources.index.jsonl` | 68,614,751 字节原件直接提取 |
| ZIP 内 `RH_AllSources.dependencies.jsonl` | `project/lean/dependencies/` | 214,948,999 字节原件按完整行拆为 5 卷，附清单与还原程序 |
| `solution_annotation_toolkit.zip` | `solution_annotation_toolkit/` | 全部 58 个文件，19,600,269 字节，保留两个程序的可执行位 |

源码树的总大小为 1,030,536,719 字节，其中 Lean 正文为 1,030,531,854 字节。三个配置是 `lakefile.toml`、`lake-manifest.json`、`lean-toolchain`；在 `project/lean/original/` 目录使用原工具链与依赖配置。模块目录没有被扁平化或按网页列表大小重新拆分，源码和导入语句没有修改。

1,101,883,390 字节的单文件汇编仍可从 Release 下载；普通 Git 保存从该汇编恢复的全部模块与配置，没有另放一个无法通过普通 Git 单文件限制的同名占位文件。此汇编是无损源码容器，不是已验证可以直接编译的单一 Lean 模块。

依赖索引分卷是未压缩 JSONL，分卷边界在完整行之后。运行 `python3 project/lean/dependencies/join_parts.py` 可还原完整原件；内容不同的已有目标文件会被拒绝覆盖。随机访问索引是原件本身，不需要还原。

## 当时尚未解压入普通 Git 的部分（2026-11-23）

57 个 `solution_annotated.partNNN.txt.zst` 的完整解压正文尚未入库。压缩总计 18,876,901,037 字节，解压总计 **168,547,118,127 字节**（168.547 GB，约 156.972 GiB）。最小一卷 337,139,153 字节，最大一卷 3,732,963,027 字节，全部超过普通 Git 的单文件上限。

GitHub 对普通 Git 文件设置 [100 MiB 限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。进一步分块可以满足单文件限制，但会把约 168.55 GB 的生成文本带入版本库；原始大小不等于 Git 的压缩对象大小。GitHub [仓库限制页面](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits)中的 10 GB `.git` 大小属于推荐上限，不能据此声称超过就绝对不能上传。

Git LFS 会在 Git 中保存指针、在另一存储系统保存正文；GitHub Free 的单文件上限为 2 GB，免费存储额度为 10 GiB，本数据量会超过该额度。此次没有开通付费存储。完整正文继续保留在原 Release 的压缩附件中。参见 [LFS 单文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)与 [LFS 计费说明](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)。

[annotations/](../annotations/) 保存逐卷的公开元数据、下载地址和解压方法，不把目录存在解释为完整注释正文已经展开。

## 核验范围

- 工程 ZIP：全部 270 个成员完整读取并核对 SHA-256；267 个既有工程文件与成员一致。内部校验清单的 269 项全部匹配。
- 源码树：本次重新读取 175,190 个文件，逐项核验大小与 SHA-256，全部与原索引匹配；另计算 Git blob SHA-1 供暂存后核对。
- 依赖索引：逐卷核验后实际连接并重新读取全部 214,948,999 字节；完整 SHA-256 为 `1321696d0bd1141923163735d6479916ba1bf4061e2e78c7427fa0e3fe36c431`。
- 工具包：58 个展开文件全部与 ZIP 原成员逐字节哈希核对；内部 57 项清单通过。未执行其中的二进制程序。
- 注释正文：本次使用已有全量独立复核报告、公开清单与当前压缩文件大小及帧头检查，未再次完整解压约 168.55 GB 正文。
- 本次没有执行原工程全量 Lean 构建、最终定理的完整递归公理审计或全量独立内核复核。

上传时以全部新增文件的 Git blob 标识和文件模式核对暂存内容；上传后比较本地与远端提交及 Git 树标识。包含 175,000 多文件的递归 GitHub API 列表可能被截断，因此不能将一个截断列表作为完整路径核验。远端提交与树标识核验也不等于重新从 GitHub 下载每个文件计算 SHA-256。

原 Release 及其标签保留为原归档版本；此次展开提交位于 `main` 分支。机器可读目录映射见 [release-expansion.json](release-expansion.json)。
