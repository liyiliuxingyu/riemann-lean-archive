# PrincipalizationCertificate / OrderCertificate 的有限后续审读

审读提交：`a132f8e71629fed5febae6733f31b08171f3183a`。本轮只审读下面 8 个关键文件中的相关段落，没有构建原模块，也没有扩大到整个解消理论。

## 结论

在已核对的直接解释链上，`mutual inductive` 证书通过 `PrincipalizationCertificate.rec` / `OrderCertificate.rec` 做联合结构归纳。解释定理的目标是阶数等于 1 时的中心隔离性质，不是把一个未经证明的几何结论直接从同名假设中原样取出。

此前需要澄清的 `.large` 构造器，在这条解释链上有明确用途：它要求 `2 ≤ m`，而需要证明的隔离性质只有在 `m = 1` 的前提下才提出非空要求。因此这一归纳分支由不等式矛盾消去。不能把 `.large` 的形式本身当作循环证明或几何漏洞证据。

这只排除了本次审读局部结构中的特定误判；没有证明整个解消理论、证书产生算法的所有前提，或 RH 主定理已经通过完整验证。

## 审读文件

所有路径以下列前缀为根：

`project/lean/original/src/Development/ResolutionOfSingularities/EmbeddedResolution/`

| 编号 | 文件 | 本次核对内容 |
| --- | --- | --- |
| 1 | `IdealPrincipalization/PrincipalizationCertificate.lean` | 10–105 行，相互归纳证书的构造器 |
| 2 | `StrictTransformIsolation/SmoothOrderOneCenters.lean` | 定义、辅助引理与 307–360 行直接解释定理 |
| 3 | `StrictTransformIsolation/VanishingIdealHypotheses.lean` | 28–86 行，具体 vanishingIdealAssignment 的假设包与解释实例 |
| 4 | `IdealPrincipalization/CertificateOpenRestriction.lean` | 67–120、390–445 行，证书在开浸入下的传递和联合递归 |
| 5 | `StrictTransformIsolation/RestrictionToOpens.lean` | 40–112、224–255、529–552 行，另一中心隔离性质与联合递归 |
| 6 | `StrictTransformIsolation/StrictTransformSmoothness.lean` | 184–208、625–690、715–820 行，证书的几何用途和自然数阶段归纳 |
| 7 | `IdealPrincipalization/OrderReductionProperties.lean` | 299–346、411–450、530–556 行，算法规格中证书与解消字段的区别 |
| 8 | `IdealPrincipalization/OrderReduction/OrderCertificatesMultiplicityOne.lean` | 135–205、265–292、610–707 行，阶数为 1 的条件性证书构造 |

## 直接解释定理的结构

### 目标没有在证书构造器里原样给出

`SmoothOrderOneCenters.lean:46–55` 定义 `SmoothOrderOneCentersIsolated`。其展开形状为：给定带泛点和测试点的不可约闭集、环境光滑、`m = 1`、消失理想对应子概形光滑、不包含环境不可约分量、泛点不在中心、与记忆集合不交、理想局部相同等条件，推出测试点不可能位于中心。

`307–315` 行的定理

`smoothOrderOneCentersIsolated_of_principalizationCertificate`

以 `hV : IdealSheafGeometryHypotheses V`、`hG : SmoothVanishingHypotheses V` 和证书 `h` 为明确前提，调用 `PrincipalizationCertificate.rec`，并为两种证书同时指定上述隔离性质作为归纳目标。

各分支的作用可直接从源码确认：

- `memory` 分支（316–317、347–348）：中心支集位于记忆集合，与目标中的不交条件矛盾。
- `large` 分支（318–319、349–350）：`2 ≤ m` 与 `m = 1` 矛盾，由 `omega` 完成。
- `toOrder` 分支（320–342）：先建立局部理想相同。若新阶数为 1，调用子证书的归纳假设；若新阶数至少为 2，则与从光滑消失理想得到的实际阶数 1 矛盾。
- `localize` 分支（343–346、351–354）：使用开集上子证书的归纳假设，经已写出的限制引理传回。
- `descend` 分支（355–360）：调用光滑除子上的子证书归纳假设。辅助证明在 182–305 行，处理开支集或实际子理想两种情况，并把几何数据移到子概形。

所以该处使用的是证书结构上的归纳假设，不是把正在证明的全局定理再作为自身证明调用。此项判断基于源码审读，未声称本轮编译了这些模块。

### 另一条解释链也有同样的阶数边界

`RestrictionToOpens.lean:106–112` 的 `OrderOneCentersIsolated` 同样以 `m = 1` 为前提。`529–552` 行的 `orderOneCentersIsolated_of_principalizationCertificate` 同样显式使用两种证书的联合 recursor。`toOrder` 的辅助证明 `224–255` 行通过实际阶数不等式推出新阶数也是 1，再使用子证书归纳假设。

### 开浸入稳定性确实是证书递归

`CertificateOpenRestriction.lean:390–422` 分别使用两个 recursor，归纳目标是“该证书可沿开浸入拉回”。公开包装定理位于 `424–445`。这里的结论还是证书稳定性，不应误说成单凭证书就已推出整个几何解消结论。

## 从抽象假设包到具体几何用途

`VanishingIdealHypotheses.lean:28–29` 给出实际 `vanishingIdealAssignment` 的 `IdealSheafGeometryHypotheses`；`76–80` 行逐字段构造 `SmoothVanishingHypotheses`。其中字段调用 `orderAt_vanishingIdeal_eq_one`、消失理想在开浸入/子概形下的相容性等独立命名引理，而不是直接填入待证的中心隔离命题。

`82–86` 行将这两份具体假设包交给抽象的证书解释定理。因此这段代码确实有消除抽象 `hV` / `hG` 参数的具体实例；本轮没有继续展开其所有来源引理，不能把这点延伸为已验证整个几何基础。

`StrictTransformSmoothness.lean:184–208` 的 `false_of_mem_support_center` 使用阶数 **1** 的证书，并把它转换成上述具体隔离性质；然后连同光滑性、局部一致性、不交条件等，推出测试点属于中心的假设导致矛盾。

同文件 `655–670` 行从算法输出规格的 `.cert` 字段取得该阶段的阶数 1 证书；`715–722` 行交给上述几何解释。`724–820` 行的 `avoidsCenters_strictTransformι_of_smooth` 又对自然数阶段 `s` 做归纳（761 行），从第 `i` 阶段的归纳结论推进到 `i+1`。它明确保留 `hres`、`hB`、`hrad` 等前提和起始对象光滑的假设，不能把这里的兼容性结论当作对任意奇异对象无条件得到光滑性的证明。

## 证书产生一侧的有限检查

`OrderReductionProperties.lean:299–346` 定义的 `IsMaxOrderReduction` 同时有 `.cert` 字段（300–303）和 `.resolves` 字段（326）。**证书和整个吹起序列已经解消，是规格中不同的要求。** 不能从这里直接推断“证书即解消”，也不能将取 `.resolves` 字段的合法规格使用误判成已经无条件构造该规格。

`OrderCertificatesMultiplicityOne.lean:135–148` 的 `orderCertificate_one_of_isSmoothDivisor` 是一个明确的条件性证书构造：输入光滑除子、支集包含，以及“开支集”或该除子子概形上的主化证书，输出环境上的 `OrderCertificate`。`169–192` 行使用 `.descend` 构造器；它没有声称凭空产生下层证书。

较高层的 `continuationOrderCertificate_of_mult_eq_one`（265–271）和 `orderCertificate_coverMarkedBlowupData_of_mult_eq_one`（686–707）保留 `hstar`、`hopen`、`hinv`、`hspec` 等前提。其中 `hspec` 是边界除子降阶规格；该规格内给出的子概形证书条件见 `OrderReductionProperties.lean:547–556`。

这些前提是否在整个算法中按严格下降维数建立、是否存在更远的语义循环，本轮没有追踪完毕。已核对的直接证书消去使用结构归纳，而证书产生部分是有明示前提的构造。当前没有可据此报告的已证实循环证明。
