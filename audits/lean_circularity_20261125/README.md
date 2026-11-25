# 循环证明定向核查：2026-11-25

审查源码固定在 [`a132f8e71629fed5febae6733f31b08171f3183a`](https://github.com/liyiliuxingyu/riemann-lean-archive/tree/a132f8e71629fed5febae6733f31b08171f3183a)，即重复导入和四项局部证明精简后的版本。

**本轮没有定位到能够确认的循环证明。当前内部模块导入图无环；已读取的 RH 主链、弱几何接口及证书解释链中，也没有找到未证明结论互相支撑的具体实例。这不等于已经证明整个工程不存在循环论证。** 完整工程未在本轮构建，最终定理的实际声明依赖闭包及递归公理集合未全量核验。Lean 源码未修改。

机器可读结论见 [audit_result.json](audit_result.json)。

## 检查层级与实际结果

| 层级 | 本轮实际检查 | 结论及限制 |
| --- | --- | --- |
| 源码身份 | 当前全部 `.lean` 清单及每个 Git blob 都与固定提交核对 | 175,188 个模块、17,354,157 行、1,030,204,932 字节一致 |
| 模块导入图 | 753,264 条去重内部边；Kahn 拓扑排序，并逐边检查依赖在使用方之前 | 全部节点处理完成，自导入 0，内部有向环 0；外部包不展开 |
| 显式信任信号 | 原始文本与屏蔽注释/字符串后的词法扫描 | `axiom`、`sorry`、`admit`、`sorryAx`、`unsafe`、`native_decide`、`skipKernelTC` 各 0；不是最终定理的公理审计 |
| 最终 RH 主链 | 从 `Main` 追到 `EveryCharacter`、`Row0b` 的组装与几何/theta 输入 | 所读主链未发现把最终 RH 当成前提后再返回 RH |
| 几何条件 | 展开 `anyGeometry`、`geoOf`、`OAt`、`GeoCl`，追实际调用与余体积界 | 确认使用弱几何参数；未定位到 `True` 直接转为强 `geoOf` 的桥接 |
| 相互归纳证书 | 读定义及中心隔离的直接解释定理，续查 8 个关键文件 | 使用联合结构归纳；`.large` 分支因阶数条件矛盾被排除，未发现这条有限链中的循环证明 |
| 编译器行为示例 | 固定 Lean 4.33.1，3 个仅依赖 Init 的正反例 | 条件恒等和合法递归接受；无下降的直接自证明确被拒绝。示例不是原工程验证 |

新扫描的完整统计、源码哈希汇总和拓扑顺序摘要见 [structure/structure_summary.json](structure/structure_summary.json)。关键字的具体位置见 [trust_token_matches.json](structure/trust_token_matches.json)。

## 一、主入口有强前提，但没有把它留在最终参数里

`Main.lean:4` 是：

```lean
theorem riemannHypothesis : RiemannHypothesis := rhOfAll
```

本轮核对到的主要源码调用关系为：

1. `riemannHypothesis` 调用 `rhOfAll`。
2. `rhOfAll` 把 `allChi` 交给 `rh_of_every`。
3. `allChi` 来自 `UpperTheory.FinalTheorems.everyCharacter`。
4. `everyCharacter` 把 `galoisLocalGlobalStrong_recParameter` 交给 `everyCharacter_of_row`。
5. 该 `Row0b` 实例来自 `galoisRepresentations_of_thetaLift tLiftK`。
6. 后者调用 `galoisLocalGlobalStrong_of_geometry_lift geoOne_holds tLiftK`。

这里记录源码中的调用关系，不表示本轮已经从头重证每个节点。`GeoOne` 与 `TLiftK` 后面仍有本轮未全部展开的子树。

`EveryCharacter` 是所有相应 Dirichlet L 函数在右半平面的非零性；它很强，并非恒真条件，也不应直接称为与普通 RH 完全同一个命题。`rh_of_every (h : EveryCharacter) : RiemannHypothesis` 单独是条件归约。最终源码通过无参数的 `everyCharacter` 另行提供这个前提，其生产链继续指向 `Row0b`、几何输入与 theta 提升。已读组装点没有只把 RH 假设原样返回。

`MainConclusion.lean:7–8` 把同一个 `Row0b h` 同时用于文献条件包 `⟨h, recTExists, h⟩` 和算术窗口 `vwin_of_row h`。多次使用同一个已提供的前提不构成对该前提的循环证明；真正需要审查的是它的生产链。

完整路径、行号和检索结果见 [main_trace/main_trace_review.md](main_trace/main_trace_review.md)。

## 二、`anyGeometry := True` 确实弱化了条件，但不能据此确认循环

`Development/AbelianVarietyTheory/Definitions/AutomorphicMembership/OverIx.lean:16–19`：

```lean
def geoOf (Q : ∀ D : D7, GlobalTheory.ShFam.KitClass D) : GeoP := fun D J X =>
  (∃ c : ℕ, 0 < c ∧ GlobalTheory.ShFam.IsGeoOf (Q D) J c X) ∧
    GlobalTheory.ShFam.Pad.HasTrueSurf X

def anyGeometry : GeoP := fun _ _ _ => True
```

这两个谓词的强度明显不同。`GeoCl` 是带 `base`、`step` 的归纳闭包，因此 `geoCl anyGeometry` 可以从 `GeoCl.base trivial` 得到；闭包并没有恢复失去的强几何要求。

同时核对到三个必须保留的细节：

1. `OAt` 还包含独立的 `lam : LamAre ...` 字段。选择 `anyGeometry` 只使 `geo` 字段平凡，不会按定义使整个记录成为 `True`。
2. `NotLamAreShift.lean:152–161` 分开给出 `oAt_any` 和 `oAt_geoOf`。后者仍要求 `0 < c` 及 `IsGeoOf` 的见证；在这两个接口中未发现从恒真直接获得强几何条件的步骤。
3. `SiegelEisensteinSecondTermHypotheses.lean:44–73` 的实际主路线确实使用 `geoCl anyGeometry`，但仍显式接收并使用 `CovolumeBoundOfX`。调用者在 `EveryCharacterOfLiteratureOfVWin.lean:810–813` 另外通过 `topCovolSlim2_use_alt_alt` 提供这一数值界，不能把它说成由 `trivial` 直接产生。

另外，`geoDegenerate` 等退化模型确实存在，部分体积、次数和点集取零或单点；`TupPinsOfMuIsW.lean:211–213` 的 `divEx_of_ox` 也确实忽略三个文献输入，再调用弱模型构造。这些是需要如实解释的源码事实。它们提示应核对形式化模型与人类几何叙述是否一致，但在没有补齐后续依赖证据前，不能直接等同于循环证明或错误证明。

16 个文件的精确片段、哈希和引用链见 [geometry/geometry_circularity_review.json](geometry/geometry_circularity_review.json)。

## 三、真正的 `mutual` 定义使用了结构归纳

`PrincipalizationCertificate.lean:10–93` 相互定义两个归纳证书：

- `PrincipalizationCertificate.toOrder` 接收 `OrderCertificate`。
- `OrderCertificate.descend` 接收子概形上的 `PrincipalizationCertificate`。

这种类型间双向出现本身不是两个定理互证。本轮进一步找到 `SmoothOrderOneCenters.lean:307–360` 的直接解释：它调用 `PrincipalizationCertificate.rec`，同时为两种证书指定归纳性质，递归分支使用子证书的归纳假设。

其中看似过弱的 `.large` 构造器只要求 `2 ≤ m`，但解释目标 `SmoothOrderOneCentersIsolated` 在第 46–55 行要求 `m = 1`；两个 `.large` 分支据此用矛盾消去（第 318–319、349–350 行）。这条局部用途有明确解释，不能把它当成已经发现的漏洞。

证书进一步用于阶数 1 的中心避让；`StrictTransformSmoothness.lean:761` 的阶段证明对自然数作归纳。算法规格中的 `cert` 与 `resolves` 是不同字段，证书并不等于完整解消结论。更高层 `hstar`、`hspec` 等前提的全部来源未在本轮追完。

完整有限续查见 [dependency_graph/certificate_followup.md](dependency_graph/certificate_followup.md)。

## 四、两个容易误读的现象

### `Iff.rfl` 只证明命题定义等价

`ClaimStrip.lean:100` 的：

```lean
theorem zeta_iff : Zeta ↔ RiemannHypothesis := Iff.rfl
```

只说明两个命题名称按定义相同，不会因此证明其中任一个成立。实际 `Claim.zeta` 在第 73–98 行，明确使用 `HalfPlane` 前提；最终组装通过 `allChi` 提供相应条件。

### 没有公理依赖，也可能仍有假设

实际用固定 Lean 4.33.1 编译了：

```lean
theorem conditional (P : Prop) (h : P) : P := h
#check conditional
#print axioms conditional
```

它成功编译且公理依赖为空，但完整类型仍保留 `(h : P)`，所证明的是条件命题。相对地，`theorem badCircular (P : Prop) : P := badCircular P` 明确因无法证明递归终止而被拒绝。合法递减递归示例则成功；该示例实际依赖 `propext`、`Quot.sound`，不能误写成没有公理。

完整命令、版本、三个源码的 SHA-256 和日志见 [dependency_graph/probes/verification.json](dependency_graph/probes/verification.json)。这些示例只解释工具行为，没有导入或核验原 RH 工程。

## 五、验证边界

- 当前完整扫描是源码身份、模块导入图及词法信号检查，不是声明级证明依赖图。
- 自制头部扫描器不是对全部模块运行官方 Lean 解析器。本轮未对全部声明 elaboration。
- 注释/字符串屏蔽不是完整 Lean lexer，字符字面量、插值表达式、quoted identifier 和 Unicode 标识符边界需要谨慎解释。本次相关高风险词的 raw counts 与 masked counts 均为零，隐藏字符串信号与词法警告均为零；仍不能由此替代编译后公理审计。
- 全树存在 4 处 `elab`、87 处 `macro`、2 处 `addDecl`、32 处 `run_tac`。这些需要结合实际产生的声明审查，不能把它们的存在本身视为漏洞，也不能靠文本零命中排除一切生成行为。
- 原工程完整 `.olean` 和完整原始内核导出在当前工作区不可用。本轮没有构建完整工程、重新计算最终 RH 的递归公理集合，或建立全量实际常量依赖图。
- 已有依赖索引是 import 索引。NDJSON 注释工具的名称/层级/表达式编号顺序检查，也不是声明常量的无环证明。数据来源及归档基线核验见 [declaration_graph_limits.md](dependency_graph/declaration_graph_limits.md)。

更强的核验需要完整构建产物，检查最终定理的真实类型、所有显式/隐式参数、递归公理依赖及实际证明项，并正确处理归纳声明组和合法递归。同时还需审读关键定义及前提，判断它们是否表达预期数学命题。Lean 官方说明也明确区分“一个形式命题有证明”和“这个命题就是人们想证明的数学陈述”：参见 [Validating a Lean Proof](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) 与 [Theorems](https://lean-lang.org/doc/reference/latest/Definitions/Theorems/)。

## 复现与证据定位

在仓库根目录重新执行当前源码结构检查（只读源码，输出写到临时目录）：

```bash
python3 audits/lean_circularity_20261125/audit_structure.py \
  --repo . \
  --commit a132f8e71629fed5febae6733f31b08171f3183a \
  --output /tmp/lean-circularity-structure
```

脚本复用同仓库 `audits/lean_simplification_20261125/audit_imports.py` 的头部解析及 Kahn 算法，记录其哈希，并逐边独立核对拓扑位置。需要本地保有上述固定提交且源码内容与之相同。

三份 Init-only 示例可分别用固定 Lean 4.33.1 编译；`BadCircular.lean` 的预期结果是终止性错误，其余两份预期成功。示例源码未改，当前命令与结果已完整保存在验证 JSON 中。

所引用关键源码的定位和 SHA-256 见 [selected_source_evidence.json](selected_source_evidence.json)。报告记录的是本轮实际检查范围；未完成的完整证明验证没有被标成完成。
