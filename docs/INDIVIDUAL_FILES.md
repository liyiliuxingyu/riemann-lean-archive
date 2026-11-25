# 独立文件与归档映射

日期：2026-11-25。检查基准：`b32465bf0a42b702d7834fbb5f983fe413fa5aa6`。

本次把尚未展开的小型归档继续放入普通 Git，便于直接打开、下载和比较。正式 Lean 源码树、原始索引、Release 附件及历史审计的数学结论没有修改。

> 后续更新：57 卷完整注释正在继续展开上传，实际完成范围见 [完整注释目录](../annotations/unpacked/)。本页记录此前 643 个小型归档展开文件的范围，其中保留大卷压缩附件的安排已由后续工作推进。

## 可直接阅读的内容

| 来源 | 当前普通文件位置 | 本次展开文件数 | 展开字节数 |
| --- | --- | ---: | ---: |
| `Lean_geometry_audit_20261123.zip` | [几何专项审计](../audits/lean_geometry_20261123/) | 14 | 101,005 |
| `Lean_logic_audit_20261123.zip`，含内部 gzip 的继续展开 | [逻辑审计](../audits/lean_logic_20261123/) | 223 | 37,746,202 |
| `ctex-kit-source.tar.gz` | [CTeX 对应源码](../project/third_party/ctex-kit-source/) | 405 | 12,083,057 |
| 工具包内的小型注释测试卷 | [独立 TXT](../solution_annotation_toolkit/benchmark/prefix_output_v2/solution_annotated.part001.txt) | 1 | 22,791,733 |
| **合计** | 不包括新增说明、清单和核验脚本 | **643** | **72,721,997** |

保留包内相对目录、文件字节和历史证据。仅将归档最外层目录映射为表中的目录名。CTeX 原包最外层目录是 `ctex-kit-13a22565bdd14d750b604c2f1ed0fa1938cb6cd4`；原可执行位也保留。

逻辑审计中的 `trust_scan/matches.jsonl.gz` 进一步展开为 [matches.jsonl](../audits/lean_logic_20261123/trust_scan/matches.jsonl)，共 34,978,592 字节、88,282 条 JSON 记录。原压缩成员不再放入当前目录。TXT 样本含原始前 147,492 条 NDJSON 记录及各自注释；它与 Release 中包含 18,288,865 条记录的完整第 1 卷不是同一文件。

这些较大的文本可能超过 GitHub 网页预览限制，但已经是可单独下载的普通 Git 文件。

## 为什么还有压缩文件

当前普通 Git 树保留的唯一压缩文件是：

```text
solution_annotation_toolkit/benchmark/prefix_output_v2/solution_annotated.part001.txt.zst
```

它只有 2,893,018 字节，现有 `tools/test_verify_annotations.py` 直接用它测试压缩读取。保留它使原工具包及其测试入口继续可用，同时提供上表中的解压 TXT。

Release 的 60 个原附件保持原样。其中 57 卷完整注释合计解压 168,547,118,127 字节，各卷均超过 GitHub 普通 Git 的 [100 MiB 单文件上限](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。继续切片可降低单文件大小，但会把约 168.55 GB 的生成文本引入版本库，因此本次保留这些 Release 压缩附件例外。它们的[逐卷清单及下载办法](../annotations/)已经提供；没有声称完整正文已展开上传。

原始 `RH_AllSources.lean` 汇编超过 1 GB，其全部 175,187 个模块及 3 个配置已按原路径放在 [project/lean/original/](../project/lean/original/)。依赖索引也已经是 [5 个未压缩 JSONL 分卷](../project/lean/dependencies/)，无需再解压。

## 原件与历史清单

本次用展开目录替代了主分支的三份归档文件。原件可从固定提交取得：

| 原件 | 固定历史链接 | SHA-256 |
| --- | --- | --- |
| 几何审计 ZIP | [原文件](https://github.com/liyiliuxingyu/riemann-lean-archive/blob/b32465bf0a42b702d7834fbb5f983fe413fa5aa6/audits/Lean_geometry_audit_20261123.zip) | `58b715bcfc9e4781b236f461b8219ec26ab2ea56e5c5d10bde979e201b01e0e6` |
| 逻辑审计 ZIP | [原文件](https://github.com/liyiliuxingyu/riemann-lean-archive/blob/b32465bf0a42b702d7834fbb5f983fe413fa5aa6/audits/Lean_logic_audit_20261123.zip) | `4152332b4087b7fa1ad1d3e7b041cf45e644c3e104b5c63071dad9e6932521a1` |
| CTeX 源码 tar.gz | [原文件](https://github.com/liyiliuxingyu/riemann-lean-archive/blob/b32465bf0a42b702d7834fbb5f983fe413fa5aa6/project/third_party/ctex-kit-source.tar.gz) | `d7390ae719a3b06fa647fa3923cc819f917b92a94886d30a12485c6687bfc83f` |

CTeX 原归档也保存在原工程 Release ZIP 中。没有重写 Git 历史或删除原 Release。

包内的 `SHA256SUMS.txt`、`project-files.public.json`、`solution_annotation_toolkit/toolkit_files.json` 和此前展开记录保持其历史含义。尤其是逻辑审计的原校验表仍引用 `trust_scan/matches.jsonl.gz`，它描述的是原 ZIP 布局；不能拿它把现在的 JSONL 误报成内容缺失。需要原 gzip 的精确字节时，应从固定原 ZIP 抽取该成员。重新压缩 JSONL 不保证得到同一份 gzip 字节。

当前布局使用 [unpacked-files-20261125.json](unpacked-files-20261125.json) 的 `files` 清单核验，其中给出全部 643 个展开文件的路径、大小、SHA-256、Git 文件模式及来源映射。

## 完成的检查

- 原始索引的 175,190 个唯一路径与主分支完整 Git 源码树逐项一致，缺失 0、多余 0。使用 NUL 分隔读取路径，正确处理 394 个非 ASCII 路径；没有使用可能截断的递归网页 API 列表作为全量清单。
- 两个审计 ZIP 的 237 个文件全部完整读取、CRC 校验和写后比较通过；原内部 SHA-256 校验表的 235 项全部匹配，两个校验表本身保持原字节。
- 嵌套 gzip 全量解压通过 CRC 和长度检查，88,282 条 JSON 全部可解析；当前 JSONL 的哈希已独立保存。
- CTeX tar.gz 的原始 SHA-256 匹配既有工程清单；405 个常规文件全部回读比较，拒绝路径逃逸、链接和特殊文件。
- 样本 zstd 的压缩哈希匹配原清单，完整解压成功，解压大小匹配 22,791,733 字节；另计算 TXT 的 SHA-256。

从仓库根目录运行以下命令，可重新读取并核验本次的全部 643 个展开文件：

```bash
python3 tools/verify_expanded_files.py
```

本次检查处理文件完整性和可浏览性，没有重新计算全部 1 GB 原 Lean 源码的 SHA-256，没有执行原工程全量构建，也没有对历史数学论证作新的正确性认证。
