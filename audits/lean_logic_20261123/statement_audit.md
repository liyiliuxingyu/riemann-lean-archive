# Lean 数学陈述与关键证明链审查

日期：2026-11-23（北京时间）。本子审查只做源文件完整性核对和指定节点的静态数学阅读，未运行 Lean 内核。

## 结论

在本次实际阅读的终点陈述、函数方程归约、字符降到原始字符的归约，以及一个关键积分非消失引理中，**没有定位到可以确认的逻辑漏洞**。这不是对完整工程的通过结论。完整证明所需的所有传递依赖没有由本子审查逐个重证或编译。

已经核实：保留的 85 个原项目选取源文件均与完整 bundle 索引记录的 SHA256 一致。另从 bundle 按偏移抽取了 Main、Statements、MainTheoremsAll、RowSrc、GaloisRepresentationsOfThetaLift、IntegralStructures/Development，抽取时验证字节数及 SHA256。没有改动原文件。

## 1. 目标没有在入口变成较弱命题

原项目 `src/Main.lean:4` 是：

```lean
theorem riemannHypothesis : RiemannHypothesis := rhOfAll
```

它没有显式的额外假设参数。`Statements.lean:3–4` 中的 `RiemannZetaZerosOnLine` 是：所有 ζ 零点，除去负偶整数和 s=1，实部为 1/2。这与固定 Mathlib commit 中的 `RiemannHypothesis` 定义一致。这里排除 s=1 的理由来自 Mathlib 原定义本身：形式系统给亚纯函数在极点处也赋了值，数学陈述需要排除该点；不是本项目额外删掉困难零点。

一手核对地址：

https://raw.githubusercontent.com/leanprover-community/mathlib4/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/NumberTheory/LSeries/RiemannZeta.lean

本地选取 Mathlib 文件 `Mathlib/NumberTheory/LSeries/RiemannZeta.lean:185–186` 给出同一定义。本次没有重新对整个 Mathlib 依赖树进行字节或内核校验。

对完整 bundle 的相关定义和 notation 文本定位，没有发现项目另行定义 `RiemannHypothesis` 或 `riemannZeta` 的命中。存在许多名称为 `RiemannHypothesisOf...` 的条件性中间命题；它们的名称本身不能作为目标偷换的证据。文本定位不是 Lean 名称解析的替代品，最终应以 elaboration 后的类型和常量依赖为准。

## 2. 最后的解析归约：没有发现漏掉边界情况

主要路径是：

`UpperTheory.FinalTheorems.everyCharacter` → `allChi` → `Formalism.VW.rh_of_every` → `Formalism.VW.rh_of_right` → `rhOfAll` → `_root_.riemannHypothesis`（在模块 Main 中声明）。

`EveryCharacter.lean:13–14` 的条件是对所有非零模数、所有 Dirichlet 字符，在 Re(s)>1/2 时 L 函数不为零，排除主字符且 s=1 的极点组合。它是真正的强不消失结论，不是定义为 True 的占位符。

`Formalism/GammaFactorNonvanishing/RhOfRight.lean:5–62` 的归约把零点按实部小于、等于、大于 1/2 分为三类。右侧直接矛盾；左侧以函数方程把 s 反射到 1-s。代码实际处理了以下条件：

- 由 ζ(0)=-1/2 排除 s=0，进而保证反射点不等于 1；
- 反射点实部大于 1/2，因此不落在非正整数；
- Γ(1-s) 因实部为正而不为零；
- 余弦因子若为零，会迫使 s 为负偶整数、0，或落入与 Re(s)<1/2 冲突的分支；
- 最后将各因子的非零性与函数方程给出的乘积为零矛盾。

`CritLine.lean:11–32` 和 `CharacterBoxes/ClaimStrip.lean` 还分别处理原始字符和非原始字符。非原始字符步骤需要有限 Euler 因子不为零，代码用 |ψ(p)|≤1 和 p^{-Re(s)}<1 得到这一点。静态阅读未发现把“分母可能为零”忽略掉的步骤。

这些检查只能支持“这些短归约没有观察到明显错误”。它们不证明输入 `EveryCharacter` 本身成立。

## 3. EveryCharacter 不是由入口裸假设提供，但大依赖仍未验证

`CharacterBoxes/MainConclusion.lean:7–11` 中先给出带 `Row0b` 参数的归约，再将其应用于 `galoisLocalGlobalStrong_recParameter`，得到不带显式参数的最终 `everyCharacter`。

已继续读到以下包装：

- `IntegralStructures/RowSrc.lean:6` 将 theta lift 定理输入表示构造。
- `IntegralStructures/GaloisRepresentationsOfThetaLift.lean:6` 将 `geoOne_holds` 输入同一构造。
- `IntegralStructures/Development.lean:19–31` 组合几何种子、同余输入、迹极限、闭合性和下降，再限制到 `Row0b`。
- `.../DenseThresholdCases/VwinOfRow.lean:4–5` 用 Row0b、基变换及输入组合定理导出 VWin。

因而不能仅凭 `everyCharacter_of_row` 有参数就指控原工程把 RH 当作假设。最终包装确实提供了一个被称作定理的值。反过来，包装中写着 `theorem`、参数已被应用，也不能替代对这些提供者及其全部依赖的编译与公理审计。

`ExistsPageN.lean:44–49` 的 VWin 只对满足 WinPair 条件的辅助素数对给出窗口。这个定义单独不保证素数对存在。后续 `SupplyChi.lean` 使用供给定理和 admissibleClassesTwistedChar；本次没有把这整个存在性链完整重证。因此这里只记录阅读边界，不把该条件量词本身误报为“空集漏洞”。

## 4. 积分非消失引理的假设足以支撑所读论证

读了 `ThetaParseval/SchurStep.lean:183–189` 中 AbsNe 的完整类型，以及 `ThetaParseval/BlockDeterminants/AbsNe.lean:5–64` 的实现。

该引理明确要求 H 的测度非零且有限、K 的测度有限、整体 f 可积、κ≠0、r>0，以及 K 外尾积分严格小于 K 的测度。代码先用 Fubini 与 H 的正测度导出 s·c₀ 可积，随后把积分分成 K 上常值主项和补集尾项。主项绝对值为 μ(K)r，尾项绝对值严格更小，因此总积分不为零。

未发现遗漏 κ≠0、对不可积函数非法交换积分、将非严格界当作严格界的具体问题。K 的正测度不必另作假设：非负尾积分严格小于 μ(K) 已强制 μ(K)>0。

## 5. 必须避免的验收误判

工程附带的 `project/reference/lean/EndpointReduction.lean:74` 是：

```lean
theorem rh_of_every (h : EveryCharacter) : RiemannHypothesis :=
  rh_of_right (zeta_right_of_every h)
```

即使这份小文件单独成功编译，结论也只是 `EveryCharacter → RiemannHypothesis`。它没有构造 `EveryCharacter`，不能据此宣称完整黎曼猜想证明已经通过验证。文件自身的注释已说明这一边界，因此这是验收注意点，并非该文件的隐藏漏洞。

本子审查没有获得实际执行的 `#print axioms riemannHypothesis` 结果，也没有完整重建所有依赖。不能报告“零额外公理”或“全部内核通过”。下一步应在固定依赖和原始模块边界下实际构建，打印最终定理类型及公理依赖；如有可疑自定义公理、sorryAx、外部编译信任路径或构建失败，再沿实际依赖链定位。

## 6. 追加检查：紧支撑版本的元程序复制

信任扫描定位了 `Formalism/HermitianCurvature/HermitianCurvatureProofs/CutCptCopy.lean`。它把一组声明的类型和证明项中的常量同时替换，生成后缀为 Cpt 的新声明。三个特殊替换指向紧支撑版本的 form positivity、size standard 和 vector isomorphism 定理。其 `copyAll` 使用 `addDecl` 添加改写后的声明；并非单纯把旧证明的名字换掉而保留未修改类型。

针对数学前提，追加阅读发现：

- `ModuleFormPosCompactSupport.lean:8–12` 的 `FormPosCpt` 明确要求每个系数满足 `CptCoef`，实现实际使用该条件选择共同 ε 和支撑界 R。
- `VectorIsomorphismCompactSupport.lean:13–116` 保留输入系数的紧支撑假设，并证明变换后系数仍满足对应条件。
- `SizeStandardCompact.lean:18–40` 的共同 ε、R 构造仍显式依赖有限族中的所有系数满足紧支撑条件。
- `CutMainCpt.lean:102–119` 的 `limPos_of_limEvTCpt` 不是直接删除紧支撑条件：它使用 `limit_of_module_forms` 产生紧支撑近似，对近似应用非负性，再以两次 `ge_of_tendsto` 传到所需极限。

所以，本次没有在这个可疑点确认“偷偷去掉紧支撑条件”的问题。仍需实际构建来确认所有自动复制声明的改写类型和值确实匹配；不应仅凭元编程的存在认定绕过内核，也不应仅凭调用 `addDecl` 就声称完整项目已通过核验。

## 证据文件

- `statement_audit.json`：已阅读源文件/选取范围、SHA256、分类结论。
- `statement/selected_source_verification.json`：85 个选取源文件与完整 bundle 索引的逐项一致性结果。
- `statement/extracted/`：按索引恢复并验证过的 6 个原始模块。
- `statement/StatementSemanticsAudit.lean`：只导入 Mathlib 的目标陈述等价性与符号消歧检查；生成本报告时未运行。
- `statement/FullProjectAxiomsAudit.lean`：供完整工程构建后运行的五个入口定理类型与公理清单检查；生成本报告时未运行。

本报告的“未发现”始终限定在上述范围，不能外推为对 175,187 个原项目模块的数学正确性保证。
