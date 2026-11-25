# riemann-lean-archive

黎曼猜想相关 Lean 源码、中文数学说明、可恢复的源码单文件汇编，以及 `solution.ndjson.zst` 逐行中文注释的工程归档。

本仓库整理文件、保存出处并提供恢复与核验方法。文件汇编、哈希核验和 NDJSON 注释的成功，不能代替 Lean 内核对数学证明的检查。本次整理及后续有限审查没有完成本机完整原工程构建、最终定理的完整递归公理审计或全量独立内核复核。中文数学稿仍有明确标出的上游论证未完全展开，不是独立完整的新证明。

<!-- full-annotation-expansion-status -->
## 完整注释附件展开进度

57 卷完整注释正在按完整记录对分块上传，已完成 20/57 卷。实际目录、逐卷核验结果和下载入口见 [annotations/unpacked/](annotations/unpacked/)。原始 Release 附件作为备份保留。
<!-- /full-annotation-expansion-status -->

## 交付内容与目录

Release 中的源码汇编已恢复为完整模块树，工程索引和注释工具包也已展开到普通 Git 文件。原工程常规成员及后续展开的第三方源码可直接按文件阅读，随机访问索引按原字节提取；大于单文件上限的依赖索引按完整行拆为 5 卷。`audits/` 的两份有限审查及复核证据也已展开。

**完整注释的最新展开与上传状态见上方进度及 annotations/unpacked/。** 全部 60 个原 Release 附件仍在 [归档 Release](https://github.com/liyiliuxingyu/riemann-lean-archive/releases/tag/archive-20261122) 中，已有逐项 SHA-256 核验记录。此次展开的范围、核验方法和剩余部分见 [展开说明](docs/RELEASE_EXPANSION.md)。

| 文件或资料 | 内容与大小 | 现在的位置 |
| --- | --- | --- |
| 完整 Lean 模块树 | 175,187 个 `.lean` 模块及 3 个配置文件；1,030,536,719 字节 | [project/lean/original/](project/lean/original/) |
| 最终入口与命题 | 保持原始源码 | [Main.lean](project/lean/original/src/Main.lean)、[Statements.lean](project/lean/original/src/Statements.lean) |
| `RH_AllSources.index.jsonl` | 原始随机访问索引；68,614,751 字节 | [project/lean/RH_AllSources.index.jsonl](project/lean/RH_AllSources.index.jsonl) |
| 依赖索引 | 原件 214,948,999 字节，拆为 5 个完整行分卷，可逐字节还原 | [project/lean/dependencies/](project/lean/dependencies/) |
| 中文 PDF、TeX、分章与排版资源 | 31 页 PDF、`ctexbook` 工程、TikZ 图、随附字体及许可证 | [project/](project/) |
| 源码级数学说明 | 13 个阶段说明及 33 个关键模块原文 | [project/proof_process/](project/proof_process/) |
| 注释工具包 | 原 ZIP 的 58 个文件保留；新增 22,791,733 字节的独立 TXT 样本 | [solution_annotation_toolkit/](solution_annotation_toolkit/) |
| 两份审计及证据 | 237 个展开文件；压缩扫描记录已转为 JSONL | [audits/](audits/) |
| CTeX 对应源码 | 原源码包的全部 405 个文件 | [project/third_party/ctex-kit-source/](project/third_party/ctex-kit-source/) |
| 57 卷完整注释 | 压缩合计 18,876,901,037 字节；解压约 168.55 GB | [独立 TXT 与实时进度](annotations/unpacked/)；[原附件清单](annotations/) |
| `RH_AllSources.lean` | 1,101,883,390 字节的可恢复源码汇编；完整内容已恢复为上述模块树 | [独立 Release 附件](https://github.com/liyiliuxingyu/riemann-lean-archive/releases/download/archive-20261122/RH_AllSources.lean)，工程 ZIP 内也有一份 |
| 完整工程 ZIP | 270 个原始成员；286,288,695 字节 | [riemann-human-readable-project.zip](https://github.com/liyiliuxingyu/riemann-lean-archive/releases/download/archive-20261122/riemann-human-readable-project.zip) |

`project-files.public.json` 仍记录原始工程 ZIP 的 270 个成员，不是当前整个仓库的文件总表。`ndjson-files.public.json` 保存 57 卷的文件名、原始行号区间、字节数与哈希；新增 [annotations/release-parts.json](annotations/release-parts.json) 还给出解压大小及实际下载地址。[docs/release-expansion.json](docs/release-expansion.json) 记录此次展开的目录映射和范围。

克隆仓库后，可以直接阅读 `project/lean/original/src/` 中的源码，无需先下载巨型汇编。原模块路径与 `import` 保持一致；源码根目录为 `project/lean/original/`，其中的 `lakefile.toml` 设置 `srcDir = "src"`。部分目录文件数很多，网页列表可能不便浏览；本地克隆和按完整路径打开文件能避免依赖网页的完整目录展示。

依赖索引的精确还原命令（从仓库根目录运行）：

```bash
python3 project/lean/dependencies/join_parts.py
```

脚本会核验全部分卷与完整输出的大小、SHA-256 和行数；已有不同内容的输出文件不会被覆盖。原始工程 ZIP 解压后根目录仍为 `riemann_human/`，其内部 `SHA256SUMS.txt` 与 `verify_package.py` 适用于原 ZIP 布局。普通 Git 目录用模块树和分卷表示两个巨型原件，不能直接据原 ZIP 清单声称这两个单文件已经存在。

## 2026-11-25：优先提供独立文件

此次检查将主分支完整 Git 路径清单与原索引逐项比对：175,187 个 Lean 模块及 3 个配置均存在，没有缺失或多余路径。非 ASCII 路径采用 NUL 分隔读取，避免 Git 的显示转义影响计数。这是路径完整性检查，没有重新读取全部源文件做哈希或运行全工程证明检查。

新增 **643 个从归档展开的文件**：两份审计及证据 237 个、CTeX 源码 405 个、完整测试样本 TXT 1 个。主分支中的两份审计 ZIP 和 CTeX 源码 tar.gz 已由这些普通文件替代，原件仍可从固定 Git 历史或原工程 Release 取得。

- [逻辑审查报告](audits/lean_logic_20261123/审查报告.txt)与 [anyGeometry 专项报告](audits/lean_geometry_20261123/专项核查报告.txt)可直接打开。
- [注释 TXT 样本](solution_annotation_toolkit/benchmark/prefix_output_v2/solution_annotated.part001.txt)包含原始前 147,492 条记录及注释；它不是完整 Release 的第 1 卷。
- 普通 Git 当前只保留一个 2,893,018 字节的 `.zst`，供现有压缩读取测试使用。57 卷约 168.55 GB 的完整注释继续展开为独立 TXT，实际完成范围见上方进度；原 Release 附件保留。
- 布局映射、原件取回办法、哈希和检查范围见[独立文件说明](docs/INDIVIDUAL_FILES.md)与[逐文件清单](docs/unpacked-files-20261125.json)。

校验本次展开的 643 个文件：

```bash
python3 tools/verify_expanded_files.py
```

## 校验下载

完整工程 ZIP 的 SHA-256：

```text
1ce852981028f86d7a47931db6aff339805759b17c1621646189c357bd5baf2d
```

独立 `RH_AllSources.lean` 文件的 SHA-256：

```text
b2ee6d0afdf4472ca2d135e4f1157d740d33622c70ed664882d5532333881444
```

`solution_annotation_toolkit.zip` 的 SHA-256：

```text
ca60fc4c602768a1ec8b05f478167116d9d9ec06e5803da7cd1364029db76e3d
```

在解压后的 `riemann_human/` 目录内运行 `python3 verify_package.py`，可按随包的 `SHA256SUMS.txt` 检查工程文件。逐卷哈希以公开清单为准。

## 合并的 Lean 文件怎样使用

`RH_AllSources.lean` 使用 `lean-source-bundle-v1` 格式，是能够恢复原目录结构的源码汇编。原模块的正文、`import`、`private`、作用域和证明体保留在汇编中。它不作为可直接编译的单一 Lean 模块交付；应先恢复原模块树，再按固定工具链和依赖构建。直接执行 `lean RH_AllSources.lean` 不属于本工程已验证的使用方式。

汇编保存 175,187 个原模块，共 17,374,215 行、1,030,531,854 字节原始 Lean 源码，另保存 3 个工程配置。导入分析记录了 753,261 条项目内部直接导入边，未发现缺失的内部或未知导入；Mathlib 等外部依赖仍需按原配置准备。

需要 Python 3.11 或更新版本。解压完整工程后进入 `riemann_human/`，核验汇编内部全部模块：

```bash
python3 tools/export_lean_bundle.py verify --bundle lean/RH_AllSources.lean
```

恢复到不存在或为空的目录，然后逐文件读回比较：

```bash
python3 tools/export_lean_bundle.py restore --bundle lean/RH_AllSources.lean --destination restored/lean
python3 tools/export_lean_bundle.py verify --bundle lean/RH_AllSources.lean --against-root restored/lean
```

只抽取 `Main` 模块时可运行：

```bash
python3 tools/extract_one_module.py --bundle lean/RH_AllSources.lean --index lean/RH_AllSources.index.jsonl --module Main --output selected/Main.lean
```

完整恢复不依赖外部随机访问索引，因为汇编自身带有边界、长度、哈希和配置文件。原工程固定 Lean `v4.33.1` 与 Mathlib 提交 `0df444a360eaa60ab8c11dca51a86af692955474`。恢复成功之后仍须准备相应工具链和依赖，才能另行进行构建或证明检查。`tools/RHEntry.lean` 是调用原公开定理的小型入口，本次整理没有在本机编译它。

## 中文数学稿及其边界

`黎曼猜想_人类可读证明主线.pdf` 为 31 页中文稿，源文件采用 `ctexbook` 的默认正文字号和默认中文 Fandol 字体；目录采用正常字号，图形由 TikZ 生成。随包保存可编辑 TeX、分章、CTeX/xeCJK/zhnumber 资源、Fandol 字体及其许可证。

稿件展开了由明确引用的“算术窗口”结论推出 RH 的解析论证，并进一步解释非负部分和、若干量词顺序、窗口缩放、截断余量、有限特征正交及统一阈值等步骤。自守与 Galois 表示构造、模性长度窗口、几何宿主内部构造，以及部分尺度和厚薄区域估计仍依赖上游结果，尚未全部转写为独立的纸面证明。

因此，应把它读作有明确依赖和待展开部分的数学说明。`proof_process/` 的 TXT 与 JSON 是源码级说明和原文导出，不是逐个 tactic 的状态日志，也不是独立内核所需的最小依赖闭包。

继续编辑分章后，在 `riemann_human/` 中执行：

```bash
python3 assemble.py
python3 build_pdf.py 黎曼猜想_人类可读证明主线.tex
```

构建需要 XeLaTeX、latexmk、pdfinfo 与标准数学/TikZ 包。随包的 `texmf/` 补充中文排版资源；工具不自动安装外部软件。

## NDJSON 逐行注释

注释对象是上游发布的 [solution.ndjson.zst](https://math.mit.edu/~drew/grh/solution.ndjson.zst)。NDJSON 记录描述导出的 Lean 名称、宇宙层级、表达式和声明；它们不是一行对应一条自然语言数学推理的证明文本。

注释工具保留每条原始记录，紧邻记录给出中文字段解释和原始行号；57 卷均可独立解压。工具包包含格式说明、前 2,000 行预览、示例和读取工具。请先打开工具包中的 `solution_annotated_README_zh.txt`、`schema/format_ndjson.md` 及 `tools/VERIFY_USAGE_ZH.txt`，按实际文件布局运行工具。

| 项目 | 已保存的生成与独立复核记录 |
| --- | ---: |
| 原始记录数 | 1,080,769,508 |
| 原始 NDJSON 字节数 | 61,570,595,788 |
| 注释文本字节数 | 168,547,118,127 |
| 57 卷压缩字节合计 | 18,876,901,037 |
| 原始记录类型未识别数 | 0 |

从全部注释卷恢复出的原始 NDJSON 的 SHA-256 为：

```text
5ea74b912147c5c93cc2b6d70cc727cf908df2f62ac6a20480a3fa02f6be244e
```

此前的独立核验报告覆盖全部 57 卷的压缩哈希、原始分卷哈希、字节数、行号连续性、每行非空注释以及全局原文哈希。名称、层级和表达式引用的顺序检查属于导出结构检查。该流程没有执行 Lean 内核类型检查，也不保证中文解释已展开每个声明的数学意义。

## 2026-11-23 有限审查补充

对固定源码版本 `40e56bab026552e089d7afcfeff08d2defb9c005` 的后续有限审查确认，`anyGeometry` 定义为恒真谓词，确实进入最终证明的源码引用路线；相关弱构造使用包含恒真字段、零体积、零度数和零映射的退化模型。因此，`geo`、`Geometry` 等字段名不能自动解释为已经建立真实非退化几何；中文稿对几何链的叙述仍须与实际定义逐项核对。

这些局部事实尚未定位固定标准最终命题中的无效推理，也不能支持“绝对不存在漏洞”的保证。此前常见关键词扫描未发现问题，不能替代语义审查。相关独立小实验没有导入原 RH 工程，不能代替完整证明检查；外部发布的完整检查记录也不属于本机重跑结果。

本节依据 [Lean 逻辑审查报告与证据](audits/lean_logic_20261123/) 及 [anyGeometry 专项核查与证据](audits/lean_geometry_20261123/)，只概括该两项有限审查的结论与边界。

## 已完成的核验与没有声称完成的事项

源码汇编阶段，全部 175,187 个原模块及 3 个配置完成了字节与哈希核验，并实际恢复到目录后逐文件读回比较。中文稿此前完成 PDF 构建与 31 页版面检查。NDJSON 注释此前完成全部 57 卷的独立回读核验，报告保存在对应工具包中。

本次上传准备对最新工程 ZIP 的全部 270 个成员进行了完整解压读取和 SHA-256 计算：ZIP 成员 CRC 通过，内部校验清单的 269 个文件全部匹配。另核对了 NDJSON 工具包的文件大小与 SHA-256，并逐项比对下载索引和工具包内 57 卷清单的公开字段。本次上传准备没有重新下载全部注释卷、没有重跑全工程 Lean 构建或独立内核检查，也没有再次排版 PDF。


2026-11-23 的进一步展开对全部 175,190 个恢复后的源码及配置文件重新计算了 SHA-256，并与原索引逐项核对，全部一致。索引按工程 ZIP 的原字节提取；5 个依赖分卷实际重新连接、读回并核对完整原件的 SHA-256；工具包的 58 个展开文件与 ZIP 逐文件核对。提交时另核对每个新增文件的 Git blob 标识及文件模式，以防暂存过程改变字节。这些是文件完整性检查，不是新的数学证明验证。

完整工程中的 `provenance/`、`evidence/`、`接续状态.json`，以及注释工具包中的生成和复核报告，记录各阶段的具体范围。文件完整性、源码可恢复性与数学证明的正确性应分别评估。

## 来源与许可

原始资料入口为 [MIT 发布目录](https://math.mit.edu/~drew/grh/)。原工程最初以 14 个分卷提供；源码整理时原站返回 HTTP 403，因此该次完整源树来自发布页所指公开镜像的固定提交 `40e56bab026552e089d7afcfeff08d2defb9c005`。原分卷预期哈希和实际使用的镜像记录分别保存在工程 `provenance/` 中；本仓库不把镜像恢复描述成重新下载了原始 14 个分卷。

上游代码、字体、排版组件和注释工具依赖各自适用的许可证保持有效。完整工程保留 Fandol `COPYING`、对应 CTeX 源码归档和既有来源记录；注释工具包保存 Lean、lean4export 和 simdjson 的许可证及版本记录。本仓库没有为全部上游材料重新指定统一许可证。

归档范围仅限本次黎曼项目。旧版重复工程、可再生的构建缓存和预览图、临时下载材料、个人文件下载链接以及认证材料不属于普通仓库内容。

## 仓库中的小型工具与附件清单

[release-assets.public.json](release-assets.public.json) 列出全部 60 个已上传 Release 附件，状态为 `complete`，并保存实际下载地址、附件 ID 和服务器文件名。[SHA256SUMS.release.txt](SHA256SUMS.release.txt) 保存相应 SHA-256。将校验文件和下载附件放在同一目录，可用 `sha256sum -c SHA256SUMS.release.txt` 核验；缺失附件会明确报错。

本仓库的三个 `tools/` 文件从完整工程原样复制，来源与哈希见 [tools/SOURCE.json](tools/SOURCE.json)。如果只下载了独立 `RH_AllSources.lean`，并将它放在仓库根目录的 `downloads/` 下，可直接运行：

```bash
python3 tools/export_lean_bundle.py verify --bundle downloads/RH_AllSources.lean
python3 tools/export_lean_bundle.py restore --bundle downloads/RH_AllSources.lean --destination restored/lean
python3 tools/export_lean_bundle.py verify --bundle downloads/RH_AllSources.lean --against-root restored/lean
```

完整恢复不需要额外索引。随机访问索引现也位于 `project/lean/RH_AllSources.index.jsonl`；已经克隆仓库时，可直接使用 `project/lean/original/` 中恢复好的模块。进行 Lean 构建仍需要原定工具链和外部依赖。来源和许可文件的位置见 [docs/SOURCES.md](docs/SOURCES.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
