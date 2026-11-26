# lsernau/grh-lean 简化参考审查

日期：2026-11-26。固定提交：72fead102f663d5c7a407964a13dc0cf9d977207。

本报告仅为源码静态审查，没有执行完整构建、公理闭包打印、Lean 内核重放或独立检查器。编译验证须另记实际结果。

## 采用范围

适合把整个 grh-compact 工程作为独立简化候选，再核对原工程的五个公开定理接口。上游明确说许多步骤更换了论证，内部对象和目录也重写，因此它不是可以无条件套在旧工程上的删行补丁。最终定理名称一致不等于全部中间定义和定理都与原工程等价。

两版都有 Statements、Main、Lib 和 New 模块，应分别作为独立 Lake 工程，不能混入同一模块搜索路径。上游固定 Lean v4.35.0 和 Mathlib 56a005855ea17e0b0958f73ec801ae140b0a1679；不能直接假设与原 4.33.1 环境兼容。

## 实际源码规模

统计范围仅是各工程 src/**/*.lean，不含 Mathlib、Challenge、脚本、文档、缓存和注释导出数据。

| 指标 | grh | grh-compact |
|---|---:|---:|
| Lean 模块 | 803 | 794 |
| Lib 模块 | 495 | 573 |
| New 模块 | 306 | 219 |
| 源码字节 | 30,050,271 | 7,420,187 |
| 物理行 | 477,124 | 112,827 |
| 非空行 | 432,527 | 95,030 |
| 屏蔽注释后的非空代码行 | 299,902 | 76,149 |
| Main 显式导入闭包内模块 | 803 | 794 |

从 readable 到 compact，源码字节减少约 75.31%，物理行减少约 76.35%，非注释代码行减少约 74.61%。模块数仅减少 9 个，主要缩短发生在证明与内部接口。以上不是相对我们原 175,187 模块的减少率，也不是包含 168 GB 注释的整个仓库体积变化。

两版显式内部导入图均无环，Lib→New 边数为 0；所有 src 模块都在 Main 导入闭包内，没有可按不可达性直接删除的模块。两个版本也均没有重复的显式 import。导入图无环不等于完整的定理依赖或数学循环性审计。

逐文件字节、行数、导入和 SHA-256 见 grh_files.json、grh-compact_files.json；汇总见 upstream_static_review.json。扫描屏蔽嵌套注释及字符串，不是 Lean 解析器。

## 可借鉴的具体方法

1. 固定最终陈述。两版 src/Statements.lean 的 Git blob 相同：1cd1bce93344065936b2b392b23306254e0785ef，且只导入 Mathlib。Main 的五个定理类型是这些命题或 Mathlib 的 RiemannHypothesis，没有额外的 Data 或几何见证条件。
2. 集中主归约。compact src/New/Main.lean 集中 star_inequality、eventually_primeError_le_rpow、New.grh 和两个零点对称性归约；已证明的 exists_family_covolumeSq_le 封装上下界输入。
3. 共享规模估计。src/New/Data/Magnitudes.lean 的 HasLogBound 保存实际不等式，组合乘法、求和、幂的指数；Data.le_of_hasLogBound 将最后比较归约到尺度条件。默认参数中的 by grind 仍需证明，不是免证假设。
4. 用库引理缩短末端推导。compact src/New/Main.lean 的 New.zeros_on_line、New.zeta_zeros_on_line 明显短于 readable src/New/Main.lean 的对应证明，类型仍相同，适合优先做隔离编译和类型/公理对照。
5. 保留可读版的阅读入口。短脚本使用更多点记法、匿名参数、grind 和压缩布局，不自动意味着更易读或编译更快，本次没有速度实测。

不能把压缩理解为统一删除某类 tactic。屏蔽注释后，readable 的 first 词法出现次数为 42，compact 为 90；后备分支必须逐处验证。

## 信任边界

### 最终陈述与内部定义

五个公开结果覆盖 RH、ζ 非平凡零点、Dirichlet L 函数在右半平面的非零性、临界带零点和本原特征特例。不能宣传为所有自守 L 函数的 GRH。最终陈述只用 Mathlib 的复数、ζ 和 Dirichlet L 函数；实际采用仍应比较编译后的完整类型、宇宙参数和公理闭包，尤其是跨 Mathlib 版本时。

上游指南承认一些背景理论只采用此证明足够用的弱形式。实际例子：compact src/Lib/GaloisRep/Main/AttachedDefs.lean 的 Attached 使用任意正精度 η 下、mostFrobenii 过滤器上的特征多项式系数接近；SphericalCompat 对局部多项式要求消去 Frobenius，而不是直接要求全部标准特征多项式结论。这些是定义及证明，不是新公理，但不能仅凭名称声称完整重建文献中的全部标准理论。

未搜到旧工程 anyGeometry、GeoP、IsGeoOf、HasTrueSurf 的标识，不足以证明旧几何争议已解决；这里的内部对象已经重写。

### 源码静态筛查

两版 src 均未见这些扫描词：axiom、sorry、admit、unsafe、implemented_by、extern、elab_rules、macro、run_elab、run_tac、evalExpr、addDecl、partial、skipKernelTC、trustLevel、ofReduceBool、native_decide；也未见本地 syntax、elab、initialize、builtin_initialize 声明。此结果只代表静态筛查，不能替代实际公理闭包、完整编译和内核检查。

两版 Challenge.lean 各有五个有意保留的 sorry，供 Comparator 题面使用。它们位于 src 外，不被 Main 导入，也不在 defaultTargets 中。不能误报整个仓库零 sorry。comparator.json 比较五个最终定理，允许 propext、Quot.sound、Classical.choice，设置 enable_nanoda=true；配置不等于执行成功。

compact 的 src/Lib/General/LinearAlgebra/Base.lean 调整实例优先级、经典可判定性和全局 simp 集；IsVoid 是 IsEmpty 的同义定义。readable 的主要全局设置在 src/Lib/Speed.lean。这些可能影响内部陈述的实例选择，不能不验证就全局套用到旧工程。Statements 不导入它们，但实际编译类型仍应核对。

### 上游自报与本次实测

readable README 自报完整构建、三项公理、nanoda/con-leche/con-ron 和 Comparator；compact README 自报完整构建、Lean 内核重放、三项公理和 Comparator。Comparator 的自报运行使用替代 sandbox，要求约 64 GB 内存。仓库 scripts 只有 PrintAxioms.lean；不能把文档中的历史声明写成本次环境已经通过的检查。

根 README 明确仅机器检查，尚没人类数学家完整阅读，也没有配套论文。应区分构建通过、形式陈述与预期一致、数学界接受三个不同问题。

## 集成建议

- 导入完整固定版本 compact 工程，保留 LICENSE、NOTICE、ATTRIBUTION.md、lean-toolchain、lake-manifest.json，记录来源提交和逐文件哈希。
- 保留原归档；建立候选入口和五项接口对照。候选验证前不要整体删除原 175,187 模块。
- 以实际构建、最终公理输出和接口检查作为替换门槛；不让 Challenge 成为生产证明依赖。
- 巨型归档仓库的 CI 只检出候选子目录，避免把 168 GB 注释当作 Lean 构建输入。

## 主源

- [README.md](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/README.md)
- [grh-compact/README.md](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/README.md)
- [grh/GUIDE.md](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh/GUIDE.md)
- [grh-compact/src/Statements.lean](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/src/Statements.lean)
- [grh-compact/src/Main.lean](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/src/Main.lean)
- [grh-compact/src/New/Main.lean](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/src/New/Main.lean)
- [grh-compact/src/New/Data/Magnitudes.lean](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/src/New/Data/Magnitudes.lean)
- [grh-compact/src/Lib/General/LinearAlgebra/Base.lean](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/src/Lib/General/LinearAlgebra/Base.lean)
- [grh-compact/src/Lib/GaloisRep/Main/AttachedDefs.lean](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/src/Lib/GaloisRep/Main/AttachedDefs.lean)
- [grh-compact/lakefile.toml](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/lakefile.toml)
- [grh-compact/comparator.json](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/comparator.json)
- [grh-compact/NOTICE](https://github.com/lsernau/grh-lean/blob/72fead102f663d5c7a407964a13dc0cf9d977207/grh-compact/NOTICE)
