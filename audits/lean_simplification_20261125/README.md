# Lean 冗余代码清理：2026-11-25

本目录记录 `simplify/lean-redundancy-20261125` 分支的第一批实际修改及验证边界。基线是 [b32465b](https://github.com/liyiliuxingyu/riemann-lean-archive/commit/b32465bf0a42b702d7834fbb5f983fe413fa5aa6)，固定 Lean 4.33.1。

## 已实际删除

全部 175,187 个 Lean 文件经过导入头部扫描。这一批删除 **20,058 条完全重复的普通 import 行**，涉及 **19,897 个文件**：其中 19,750 条是重复 `import Mathlib`，308 条是重复的项目内部模块导入。

每个文件保留首次出现的 import，只删除后续相同、独占一行、不携带注释的 import。源码净减少 **326,844 字节**，约占原 Lean 源码的 **0.0317%**；行数由 17,374,215 减为 17,354,157。模块、定理、证明体和配置均保留，不能把这个数字解释为减少了同样数量的数学推理步骤。

典型改动：

```diff
 import Mathlib
 import CompanionTheory.SpectralGeometry.LocalGlobalProofs.AdelicAnalysis.TprodComplementSplitFinset
-import Mathlib
```

完整逐文件清单见 [duplicate_import_changes.jsonl](duplicate_import_changes.jsonl)，包括修改前后 SHA-256、基线行号和删除字节数；实际修改可在 Git 提交差异中查看。

## 已实际通过的检查

1. 从固定 Git 基线读取全部 19,897 个原始 blob，逐项核对原 SHA-256；按清单删除指定整行后，与当前文件逐字节比较并核对新 SHA-256。保留下来的源码字节完全一致。
2. 用官方 Lean 4.33.1 的 `Lean.parseImports'` 解析 **39,794 个修改前后头部**。全部文件的唯一 import 四元组集合、首次出现顺序、module 标志以及两个不同 meta 标志的隐式 Init 导入均保持一致。此步骤仅解析头部，没有加载项目依赖或 elaboration 项目声明。
3. 独立小实验将重复 `Init`/`Std` 导入去重。修改前后都编译通过，测试命题及其公理检查输出一致；1,114 个实际导入模块和 117,079 个声明的名称、类型、值及宇宙参数逐项一致。这个小实验不能替代全工程构建。
4. 清理工具经过独立代码审阅，补上了注释分隔符边界检查：带有 `/-`、`-/` 等非普通模块 token 的删除候选会被拒绝，避免仅凭头部解析结果误删跨行块注释的起始行。

另已独立核对基线到工作树的全部源码差异：恰为清单列出的 19,897 个修改，未出现额外源码修改、删除、重命名或权限变化，三个构建配置也逐字节不变。结果见 [source_scope_verification.json](source_scope_verification.json)。

详细结果见 [import_cleanup_verification.json](import_cleanup_verification.json) 与 [import_probe/verification.json](import_probe/verification.json)。后者列举的环境内可用公理不是本工程 RH 定理的公理依赖；小实验定理本身的公理依赖为空。

## 如何复核

在仓库根目录运行，确保 `lean` 指向工程锁定的 4.33.1：

```bash
python3 audits/lean_simplification_20261125/verify_import_cleanup.py --repo .
```

也可用 `--lean /path/to/lean` 指定编译器。复核器只读源码，利用 `git ls-tree` 与长驻 `git cat-file --batch` 读取基线，再调用随附的 [ParseImportJsonl.lean](ParseImportJsonl.lean)。需要本地保有基线提交，浅克隆未包含该提交时应先获取它。临时源码和解析结果会在检查结束后清理。

复核器核验清单列出的修改；它不是任意未来修改的全项目正确性检查。`--skip-lean-parser` 只运行字节检查，报告会明确记录跳过官方解析器。完整编译仍需要另行准备工程固定的 mathlib 版本及全部项目依赖。

注释边界反例的回归命令：

```bash
python3 audits/lean_simplification_20261125/test_comment_delimiter_regression.py
```

本目录还保留 `audit_imports.py`、`audit_mathlib_prefix.py` 与 `selfcheck_import_audit.py`，用于重新扫描当前源码和复核静态算法；基线统计对应修改前的固定提交。

## 为什么没有批量删除文件

基线的 `Main` 导入闭包及 Lake 默认目标闭包都覆盖全部 **175,187** 个内部模块，没有可以仅按这些入口的不可达性直接删除的模块。这只说明模块导入可达，不说明每个声明都对最终定理必不可少。

全树有 9 组、23 份同字节文件，其中只有 2 组、9 个文件是纯 import 转接。其他组包含真实声明，有的还有 private lemma。模块路径也是接口的一部分，不能仅凭文件正文相同就删除其中一份。[Lean 官方模块说明](https://lean-lang.org/doc/reference/latest/Source-Files-and-Modules/)明确了文件名、目录与模块名的联系。

## 更大范围候选及下一步

静态图共发现 497,165 条具有替代传递路径的直接导入边，涉及 145,909 个文件。另有 116,483 个文件在本批去重后符合更严格的 Mathlib 前缀模式；模拟这些前缀删除后，Main 的依赖优先遍历序列仍逐项一致。但这没有覆盖任意元程序对直接 import 元数据的观察，也没有减少 Main 的模块闭包，因此没有批量应用或声称编译提速。

还发现三个重复的 Gamma 因子非零证明，以及一处可直接引用标准商映射连续性引理的证明。这些声明级改动需要比较修改前后的实际 Lean 类型和公理依赖，未在本批导入清理中冒称完成。

后续应先对基线和本分支完成 `lake build Main`，再使用固定版本支持的 `lake shake --keep-public --explain` 分析已生成 `.olean` 中的真实依赖；审阅结果后才使用写入选项。命令和条件参见 [Lake 官方文档](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/)。此处列的是下一阶段入口，本次未执行全工程构建或 shake 全工程分析。

## 归档与数学核验边界

原 Release、源码汇编、旧随机访问索引和原始哈希清单仍对应归档基线；本分支的 `project/lean/original/` 路径沿用原工程布局，其中的源码字节已按本记录修改。不要用原归档哈希清单要求精简工作版逐字相同。

本次没有完成原 RH 工程的全量构建、最终定理的完整递归公理审计或独立内核复核。本次文件去重也不提供新的 RH 数学证明。
