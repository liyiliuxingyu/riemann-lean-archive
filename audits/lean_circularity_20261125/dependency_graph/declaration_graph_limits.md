# 循环依赖审查：现有数据的层级与边界

当前源码审查基准为 `a132f8e71629fed5febae6733f31b08171f3183a`。本文涉及的归档依赖索引对应较早的原始源码基线 `b32465bf0a42b702d7834fbb5f983fe413fa5aa6`，不冒称它已经随简化源码更新。

## 已独立执行的全量核验

运行 `audit_dependency_index.py`，读取仓库的 `project/lean/RH_AllSources.index.jsonl` 和 `project/lean/dependencies/manifest.json` 所列的五个分卷，未重新下载或拼接生成大型文件。

- 5 个分卷的大小、行数、SHA-256 均与清单相符；按序拼接内容的 SHA-256 为 `1321696d0bd1141923163735d6479916ba1bf4061e2e78c7427fa0e3fe36c431`，与原始清单相符。
- 完整处理 909,822 条记录，所有记录恰有 `source`、`target`、`source_line`、`modifiers`、`in_bundle` 五个字段。
- 索引包含 175,187 个内部模块；753,569 次内部 import，去重后为 753,261 条内部有向边；外部 import 出现 156,253 次，涉及 348 个外部模块。
- 308 条内部 import 边重复出现；所有 import 的 `modifiers` 都为空。
- 对源模块存在性、目标模块的 `in_bundle` 标志和源行号范围逐项检查通过。
- 对完整内部模块图执行 Kahn 拓扑排序，处理全部 175,187 个节点；自导入边为 0，未处理节点为 0。因此该基线的内部模块导入图无有向环。

精确结果见 `baseline_import_archive_verification.json`。这不是编译器运行，也不是声明级常量依赖图的 SCC 检查。

## 为什么这些依赖数据不是定理依赖图

源码依据：

- `project/tools/export_lean_bundle.py:217–218` 的目录整理阶段，只通过 `parse_imports(path)` 填充 `imports` 表。
- 同文件 `267–270` 行从 `imports` 表输出 `source`、`target`、`source_line`、`modifiers`、`in_bundle`。
- `project/provenance/full_export_validation.json:19–25` 明确标记 `lean_compilation_performed=false`、`kernel_export=false`，并说明解析范围为 `standard module header imports only; not declaration dependency analysis`。

因此不能把“模块导入无环”扩展成“所有证明的声明级依赖均已核验无环”，更不能据此排除把目标命题作为参数、类型类字段或定义内容的情况。

## 现有内核导出资料也没有补齐这项检查

仓库有 `solution_annotation_toolkit/source/prefix.ndjson` 的局部样本和完整注释工作的统计与保真记录。当前 `project/lean/original` 目录下没有原工程 `.olean` / `.ilean`；历史下载记录指向的完整 `work/ndjson_annotation/source/solution.ndjson.zst` 与完整注释分卷目录，在本次工作区中均已不存在。没有在本轮下载 7.7 GB 压缩原件或 18.9 GB 注释分卷。

`solution_annotation_toolkit/annotation_summary.json:15` 的已有检查说明，是 N/L/E 三类表引用均指向先前定义，明确写了不是内核类型检查。`independent_verification.json:19–21` 的独立验证是字节、行号和基础对象边界验证，`lean_kernel_verification=false`。

尤其不能混淆两种“先定义”：`solution_annotation_toolkit/schema/format_notes_zh.txt:31` 说明，`const.name` 只要求名称表中的名字先已存在，同名声明可以稍后输出；归纳声明组会出现这种情况。表达式表的编号无前向引用并不自动证明声明常量图无环。

本轮没有完整的声明依赖数据，也没有执行最终 RH 定理的递归常量依赖导出或声明级 SCC 审计。这个限制必须保留在结论中。

## 已核对的双向定义：不是两个定理互证

文件：`project/lean/original/src/Development/ResolutionOfSingularities/EmbeddedResolution/IdealPrincipalization/PrincipalizationCertificate.lean`。

- `10–93` 行是一个 `mutual` 声明组。
- `12–39` 行定义归纳命题 `PrincipalizationCertificate`；其 `toOrder` 构造器（`23–31`）使用 `OrderCertificate`。
- `41–91` 行定义归纳命题 `OrderCertificate`；其 `descend` 构造器（`60–91`）使用 `PrincipalizationCertificate`。
- 两个类型都还有 `memory`、`large` 等基础构造器；`95–105` 行的 `of_two_le` 定理分别直接调用自身对应的 `.large` 构造器。

从源码结构看，这是相互归纳的证书类型，不是“定理 A 使用定理 B 的结论，而定理 B 又使用 A 的结论”。不能仅凭两个类型相互出现就判为循环证明。本轮未编译该原模块。

另一个独立问题是这些证书定义是否表达了所需几何事实：例如 `.large` 构造器只要求阶数至少为 2，就给出对应证书。这一事实是源码直接可见的，但判断是否与数学目标不符还需要追踪证书的解释定理和调用目的；不能仅凭构造器名字或其形式就断言存在解消定理错误。

## 正确的后续声明级审查应获取什么

需要从完整、确实成功构建的原工程环境，或完整内核导出，读取最终声明的实际类型、证明项以及递归常量依赖。应把局部假设与全局常量区分开，并正确处理归纳类型及其构造器/消去器的组关系。纯文本引用图、模块 import 图、表编号顺序各自能说明不同事实，不能互相替代。即使实际常量图无环，仍须展开关键定义并核对最终定理的全部参数，才能判断是否把数学目标提前放进了前提。
