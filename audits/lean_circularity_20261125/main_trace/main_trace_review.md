# 最终 RH / GRH 入口的循环论证定向审查

检查提交：`a132f8e71629fed5febae6733f31b08171f3183a`。
以下路径相对 `project/lean/original/src/`。本轮为源码定向审读；未重新构建完整工程，未从最终 `.olean` 导出完整声明依赖图或递归公理集。

## 结论

在已读取的最终入口、半平面归约和 Row0b 组装链中，没有发现“先假定 RH，再把该假设原样交回，最后隐去假设”的实例，也没有发现最终 RH 定理被回调来产生这条链中的 Row0b 输入。这里不能升级成对全部 175,188 个模块的循环论证排除证明。

需要正确区分：`rh_of_every (h : EveryCharacter) : RiemannHypothesis` 是一个明确标出强前提的归约定理；它单独当然不是无条件 RH 证明。最终入口确实另行提供 `everyCharacter`，其来源继续指向 Row0b 及几何和 theta 提升构造。因此不能只因这条归约有强假设，就把它判成循环论证。关键剩余审查对象是强前提的完整生产链及数学定义是否忠实。

## 逐步调用链

1. `Main.lean:4`：`theorem riemannHypothesis : RiemannHypothesis := rhOfAll`。该文件只有两个 import 和五个最终别名，无 section/variable/instance 前提。
2. `Supplements/Kernels/MainTheorems.lean:9`：`rhOfAll := Formalism.VW.rh_of_every allChi`。
3. 同文件 `:7`：`allChi := UpperTheory.FinalTheorems.everyCharacter`。
4. `Development/AutomorphicArithmetic/CharacterBoxes/MainConclusion.lean:10–11`：无参数 `everyCharacter` 取 `everyCharacter_of_row galoisLocalGlobalStrong_recParameter`。
5. 同文件 `:7–8`：`everyCharacter_of_row h` 把 `⟨h, recTExists, h⟩` 与 `vwin_of_row h` 交给 `every_character_of_literature_of_vWin`。
6. `Development/AutomorphicArithmetic/Foundations/GaloisRepresentations/IntegralStructures/RowSrc.lean:6`：无参数 `galoisLocalGlobalStrong_recParameter : Row0b recT`，来自 `galoisRepresentations_of_thetaLift UpperTheory.TP.K.tLiftK`。
7. 同目录 `GaloisRepresentationsOfThetaLift.lean:6`：调用 `galoisLocalGlobalStrong_of_geometry_lift geoOne_holds up`。
8. 同目录 `Development.lean:30–31`：将 `galoisLocalGlobal_of_geometry_lift geo up : Row0 recT` 限制为 `Row0b recT`。
9. 同文件 `:20–28`：`GeoOne → SeedFinOdd`；配合 `congFinOdd_of_ex wtLacEx_holds` 和 `TLiftK`，通过极限、闭合特征多项式、下降构成 `CoreAll`；`rest` 再产生 `Row0 recT`。
10. 几何分支：`.../IntegralStructures/GeometricFlagBases/WeightOneGeometricRealization.lean:7–11` 从 `GlobalTheory.T.lefschetz_fixedPoint_finite_etale_correspondence` 得到 `weight_one_geometric_realization`，再产生 `geoOne_holds`。`GeometricRealizationOfWeightOne.lean:18–25` 将 steps、Kodaira–Spencer 数据和 plan existence 交给 `geoOne_of_parts`。
11. theta 分支：`.../ThetaParseval/ThetaKernels/TLiftK.lean:4–5` 给出 `tLiftK := tLift_holds_k`；`TPGHolds.lean:39–58` 实际组合 Siegel–Weil、延拓、局部模型、真空、Lie 数据和高度输入，再调用 `tLift_of_tools_k`。

这是一条带许多未展开子树的前提生产链，不能把第 9–11 步概括成已在本轮重证。

## 强前提的内容与接口

- `Development/AutomorphicArithmetic/CharacterBoxes/EveryCharacter.lean:13–14`：`EveryCharacter` 是所有 Dirichlet 特征在 `Re(s)>1/2` 的 L 函数非零性（排除平凡特征的极点情况），不是 `True`，也不是该文件中的 RH 字面别名。
- `Formalism/GammaFactorNonvanishing/CritLine.lean:25–28`：取模 1 的平凡特征，由 `LFunction_modOne_eq` 得到 zeta 右半平面非零；`:7–23` 用函数方程将左侧零点反射到右侧。
- `Formalism/GammaFactorNonvanishing/RhOfRight.lean:5–62`：`hz` 是明示参数，证明按实部与 1/2 的大小分情况，调用 zeta 函数方程、Gamma 非零及平凡零点排除；未在该证明中调用最终 RH。
- `.../Foundations/GaloisRepresentations/TypeConditions/WeightsConjBis.lean:54–73`：`Row0b` 量化 CM 数域、素数、秩、正则代数尖点表示与极化配对，要求存在连续半单的 ℓ 进 Galois 表示、权和权多重集并满足局部相容性质。不是 RH 的定义展开。
- `.../Foundations/UnitarySphericalFixing/SatakeParameters/RecT.lean:6` 和 `.../ModularityArgument/AutomorphyLifting/WeakOfAtt.lean:47`：`One.M.Row` 与 `RowT` 都是 `Row0b` 包装。
- `.../ThetaPairLifts/ThirdPlaceSeries/EveryCharacterOfLiteratureOfVWin.lean:215–218`：`OpenLiteratureStatements` 的三个字段为 Row、RecTExists、Row。两个 Row 字段重复使用同一个已提供的 `h`，这是重复打包，不构成 `h` 的生产。
- `.../ThresholdArguments/DenseThresholdCases/VwinOfRow.lean:4–5`：`Row0b h → VWin` 使用 `OpenImageCondition.mk h`、`baseChangeN` 和 `h`。
- 同目录 `TemperedProductOfSquareIntegrable.lean:207–208`：`OpenImageCondition` 只有 `RowT` 字段；`TopMainZj.lean:55–74` 把明确列出的局部、自守、上同调、CM 输入组装到窗口定理。
- `.../CharacterBoxes/ExistsPageN.lean:12–49`：`VWin` 是关于 Sha 长度的有限性及对数加权和的窗口上界，列出具体数值约束与量词；它并未在定义里直接写 RH。本轮未逐项验证这些前提在后续使用处的可实现性。

## 不应误报的两类代码

### 最终别名

`Main.lean:4` 和 `MainTheorems.lean:9` 的短证明是在调用前面得到的声明。只有找出反向依赖，或证明这些前提直接含有目标且未被独立提供，才可据此认定循环。短、重复、同义不是充分证据。

### `Iff.rfl`

`ClaimStrip.lean:100`：`theorem zeta_iff : Zeta ↔ RiemannHypothesis := Iff.rfl`。

`HalfPlane.lean:9–10` 的 `Claim.Zeta` 确实逐项对应锁定 Mathlib 中 `RiemannHypothesis` 的定义（本地固定 Mathlib 源 `Mathlib/NumberTheory/LSeries/RiemannZeta.lean:185–186`）。这个定理证明的是两个命题名称的定义性等价，不会凭空证明任一命题。实际 `Claim.zeta` 位于 `ClaimStrip.lean:73–98`，其显式前提是 `HalfPlane`；最终 `claimAll` 在 `MainTheorems.lean:15–16` 中提供 `allChi`。因此本处 `Iff.rfl` 不是独立的 RH 证明，也不是已发现的循环。

## 检索及限制

随附 `scan_summary.json` 和三个文本结果保留精确 rg 检索模式与命中。最终命题名称的全树检索未见 `rhOfAll`、`allChi` 或 `FinalTheorems.everyCharacter` 回流到以上前提生产链。项目源码未命中简单全局声明形式的 `RiemannHypothesis`、`riemannZeta` 或 `DirichletCharacter.LFunction` 重定义。

这些是文本检索事实，不能排除 namespace/notation/metaprogramming 的所有间接行为。没有完整 `.olean` 环境，因此不能确认全工程每个声明的 elaborated 参数、全部使用的公理以及所有跨模块实际常量引用。也不能凭模块 DAG 或本轮局部读链排除数学定义弱化、前提不可实现、模型偏离或不同命题间的实质等价造成的语义问题。
