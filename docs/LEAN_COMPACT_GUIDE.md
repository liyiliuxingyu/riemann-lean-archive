# 紧凑版 Lean 代码导航

本文依据上游提交 `72fead102f663d5c7a407964a13dc0cf9d977207` 的实际源码和 [上游 GUIDE](../project/lean/compact/GUIDE.md)，说明声明之间的调用关系与阅读顺序。它是代码结构导读，不是人工数学证明，也不构成“逻辑无漏洞”或与原归档完整等价的结论。

## 1. 先看五个公开出口

先读只导入 Mathlib 的 [Statements.lean](../project/lean/compact/src/Statements.lean)，核对命题的量词、区间和例外条件，再读 [Main.lean](../project/lean/compact/src/Main.lean)。五个出口共享中间结果，没有各自复制整套推导。

| 公开声明 | 源码直接使用的结果 | 阅读重点 |
| --- | --- | --- |
| `riemannHypothesis` | `New.zeta_zeros_on_line New.grh` | 返回 Mathlib 的 `RiemannHypothesis`。 |
| `riemannZeta_eq_zero_re` | `riemannHypothesis` | 以前一出口给出 `RiemannZetaZerosOnLine`；保留平凡零点与 `s = 1` 的排除条件。 |
| `LFunction_ne_zero_of_half_lt_re` | `New.grh` | 任意非零模数的 Dirichlet 特征；保留 `χ ≠ 1 ∨ s ≠ 1`。 |
| `LFunction_eq_zero_re` | `New.zeros_on_line New.grh` | 将右半平面非零转成 `0 < Re(s) < 1` 内零点的结论。 |
| `LFunction_eq_zero_re_of_isPrimitive` | `LFunction_eq_zero_re N χ` | 将一般特征的结果专用于原始特征；原始性参数仍在公开类型中。 |

这里的推广对象是 Dirichlet L 函数。不要仅凭名称 `grh` 推广到其他种类的 L 函数。

## 2. 从出口往回读的六个关键位置

`New.zeros_on_line` 与 `New.zeta_zeros_on_line` 都在 [New/Main.lean](../project/lean/compact/src/New/Main.lean) 末尾；两者显式接收同一个半平面非零命题。继续沿下表回看它的构造。

| 顺序 | 声明与位置 | 源码在此连接什么 |
| --- | --- | --- |
| 1 | `New.grh`，见 [New/Main.lean](../project/lean/compact/src/New/Main.lean) | 选择 `ε`，把特征提升到模数 `18480 * q`，调用解析判据 `entireL_ne_zero_of_primeError_le`；需要的素数误差界由下一项提供。 |
| 2 | `eventually_primeError_le_rpow`，同 [New/Main.lean](../project/lean/compact/src/New/Main.lean) | 通过 [DataExist.lean](../project/lean/compact/src/New/Data/DataExist.lean) 的 `exists_data` 构造大尺度数据，并用 [OneSidedCriterion.lean](../project/lean/compact/src/New/Endgame/OneSidedCriterion.lean) 的 `IsPolar.exists_window_sub_mul_le` 选择第二尺度，将下一项变成渐近误差界。 |
| 3 | `star_inequality`，同 [New/Main.lean](../project/lean/compact/src/New/Main.lean) | 将一个共同形式族的余体积上、下界相比较，消去 `mainHeight`，得到 `D.m * D.remainder ≤ D.logB ^ 2 * D.budget`。 |
| 4 | `Data.exists_family_covolumeSq_le`，见 [LongForms.lean](../project/lean/compact/src/New/Endgame/LongForms.lean) | 把 A、B 的结果打包为同一族的线性无关性、维数下界、指数界和余体积上界；调用处一次拆包即可使用。 |
| 5 | `Data.integral_forms_long`，同 [LongForms.lean](../project/lean/compact/src/New/Endgame/LongForms.lean) | 对满足条件的形式族给出下界；复用 `heightLe_volume_rows`、`heightLe_volume_ratio_sq` 与高度非负性。上游称此为 C。 |
| 6 | `Data.short_forms`、`Data.enough_forms`，见 [ShortAndEnough.lean](../project/lean/compact/src/New/Endgame/ShortAndEnough.lean) | 分别提供短形式及其指数控制、足够大的张成空间。上游称二者为 A、B，第四项把它们组合起来。 |

以上是依赖导航，省略了各个引理内部的大量论证。要审查数学内容，应继续展开各输入的实际类型、定义和证明体。

## 3. 共享引理怎样减少重复

- **统一处理大小估计。** [Magnitudes.lean](../project/lean/compact/src/New/Data/Magnitudes.lean) 的 `Data.HasLogBound` 分别记录 `|F| ≤ exp l` 与 `exp l ≤ F`，为乘法、加法、倒数和幂提供实例。`D.le_of_hasLogBound` 把表达式比较归结为指数比较，因此各处不必重写相同的尺度运算。实例与默认 `by grind` 参数仍须提供证明，不能将它们当成省略了前提。
- **一次构造，共用上下界。** `Data.exists_family_covolumeSq_le` 统一选择形式族；`star_inequality` 把这同一族交给 `Data.integral_forms_long`。读这里时，应核对传入的线性无关性、维数、指数和各嵌入下的界是否一一对应。
- **复用解析接口。** [OneSidedCriterion.lean](../project/lean/compact/src/New/Endgame/OneSidedCriterion.lean) 将窗口选择与“误差界推出非零”分别封装；`New.grh` 不再重新展开全部积分与解析估计。
- **零点对称性只处理一次。** [ZeroSymmetry.lean](../project/lean/compact/src/Lib/General/NumberTheory/ZeroSymmetry.lean) 的 `LFunction_one_sub_eq_zero` 通过原始特征及非零 Euler 因子处理一般特征；`New.zeros_on_line` 调用它并处理 gamma 因子条件。这里不能只保留原始特征情形。

## 4. 想继续删冗余，从哪里动手

1. 按 `Statements → Main → New/Main → Endgame` 阅读，先确定希望保留的公开接口。多个出口共用一个证明，是接口复用；不能据此把公开声明当作无用代码删除。
2. 先检查 `Endgame` 中重复的代数整理、大小估计和形式族拆包，判断是否能复用已有引理；再查 `Data/Magnitudes` 是否已有所需实例。短小证明本身不一定值得再次抽象。
3. 再按 [上游 GUIDE 的目录分工](../project/lean/compact/GUIDE.md) 深入：A 主要看 `Curve`、`Columns`、`TwistedHecke`、`Core`、`Seesaw`；B 看 `Filling`、`RealPlace`、`DiscreteSeries`；C 从 `Heights`、`Rows`、`Exchange` 继续向所导入的模块追溯。
4. 删除声明或 `import` 前检查实例、`simp`、`grind` 属性及自动生成声明的使用。文本搜索没有显式引用，不等于没有依赖；导入图无环，也不等于已排除所有数学上的循环论证。
5. 每次只改一处可说明的重复，保留命题类型及假设；重建受影响模块和最终出口，比较五个出口的完整类型与公理依赖，再判断是否值得保留。`first` 的不同分支可能承担不同目标，不能仅凭“备选分支”就删除。

后续若改动紧凑版源码，应记录为相对于固定上游提交的新补丁，并同步记录验证结果，避免混淆“原样引入”与“自行精简”。
