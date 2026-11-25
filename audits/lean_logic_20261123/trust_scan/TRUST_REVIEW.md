# Lean 源码信任边界审查

## 结论

本次没有在项目自有源码中发现显式 `sorry`、额外 `axiom`、本地原生求值证明路径、关闭内核检查的选项，或覆盖 `Lean` / `Init` / `Mathlib` 标准模块的文件。自定义策略确实直接构造或赋予证明项，但针对它们进行的最小实际测试显示：正确的证明可接受，把 `True.intro` 当作 `False` 的证明则被 Lean 4.33.1 内核明确拒绝。

这只能排除本次审查覆盖的若干直接漏洞方式，不能认定完整黎曼猜想证明已在本机通过验证。完整项目及全部外部依赖没有由本子审查从零编译；词法扫描也不等于对每个证明项进行内核验证。

## 范围与可复现性

- 归档：`RH_AllSources.lean`，SHA256 `b2ee6d0afdf4472ca2d135e4f1157d740d33622c70ed664882d5532333881444`。
- 模块：175,187 个；原始源码 1,030,531,854 字节、17,374,215 行；配置文件 3 个。
- 以归档元数据的精确字节长度读取各模块，逐一复核 SHA256；全部一致。没有把归档边界或其他模块的文本误归入当前模块。
- 扫描前屏蔽行注释、嵌套块注释、普通及原始字符串，保留行号。没有出现未闭合注释/字符串警告；也没有字符串内部含敏感扫描词而需要额外解释的情形。
- `scan_bundle.py` 可复跑完整扫描。`summary.json` 包含全部关键词的显式零值。`matches.jsonl.gz` 保留完整命中记录，`key_evidence.json` 列出具有审查价值的 218 项命中（元程序、宏、高风险名称的选项及检查命令）。
- 本范围不包含 Mathlib、Lean、Aesop 等外部包的完整自定义定义扫描。最终定理可能通过外部依赖继承公理，必须另查最终 elaborated declaration 的完整依赖。

## 主要统计

| 类别 | 源码级命中 | 解释 |
|---|---:|---|
| `sorry` / `sorryAx` / `admit` | 各 0 | 仅指被审查源码中的显式词法命中 |
| `axiom` / `axiomDecl` | 各 0 | 不排除外部依赖或错误恢复产生的公理 |
| `unsafe` / `unsafeCast` / `extern` / `implemented_by` | 各 0 | 未见这些直接扩大信任基础的项目自有代码 |
| `native_decide` / `native` / `bv_decide` / `trustCompiler` / `ofReduceBool` / `ofReduceNat` | 各 0 | 同时覆盖 `decide +native` 的 `native` 词 |
| `skipKernelTC` / `debug.skipKernelTC` / `trustLevel` | 各 0 | 配置中也没有关闭内核检查的参数 |
| `elab` | 4，分布于 3 个文件 | 2 个策略、1 个诊断命令、1 个复制声明命令 |
| `partial` | 2，分布于 2 个文件 | 两个元程序的递归实现 |
| `addDecl` | 2，位于同一文件 | 只提交 `defnDecl` 和 `thmDecl` |
| `run_tac` | 32，分布于 16 个文件 | 主要是 `revertAll`、已有假设赋值和构造已有定理的应用 |
| `run_cmd` / `modifyEnv` | 各 5 | `BuildAid.D1` 至 `D5` 的建议搜索名单修改 |
| `macro` | 87，分布于 64 个文件 | 策略组合、局部术语简写和上述策略的包装 |
| `set_option` | 88,139，分布于 75,197 个文件 | 多数是资源、实例搜索、自动隐式参数和 linter 设置 |
| 与核心/依赖模块同名的项目模块 | 0 | 检查 `Init`、`Lean`、`Std`、`Mathlib`、`Aesop` 等常用根名 |

## 需要解释而不应直接判为漏洞的代码

### 1. `kexactB` 直接给目标赋值

文件 `src/Formalism/LocalToGlobal/IndefiniteReal/HeckeNonvanishing/Imports.lean` 第 5–8 行：先 elaboration 输入项，再 `g.assign (← instantiateMVars v)`。这省略了常规 `exact` 的一些 elaborator 检查。它的输出仍必须通过声明的内核检查，不能由此推出任意命题。

已用原样策略代码构造两个最小测试：`True` 的证明成功；把 `True.intro` 交给 `False` 目标失败，日志明确为 `(kernel) declaration type mismatch`。

### 2. `kcopy` 递归重建构造器与投影

文件 `src/Formalism/LocalToGlobal/NumberFieldFamilies/OwnStruct.lean` 第 18–58 行：它按目标的函数或结构形状重建 lambda、字段投影及构造器应用，最后赋予目标。第 60–64 行的 `#kcopy_probe` 是诊断命令。`partial` 修饰元函数 `copyAt`，不等于增加任意数学公理。

正向 `True ∧ True` 测试成功；将 `True.intro` 赋予 `False` 失败，明确是内核类型不匹配。元函数若产出错误字段组合，应导致拒绝或编译错误，不能据其名称认定其替换是数学等价；真实项目中的构造仍要实际编译复检。

### 3. `cpt_copy_thms` 复制并替换定理依赖

文件 `src/Formalism/HermitianCurvature/HermitianCurvatureProofs/CutCptCopy.lean` 第 16–30、63–89 行：它收集相关常量，把若干定义/定理名改为紧支撑版本或添加 `Cpt` 后缀，同时替换声明的 `type` 和 `value`。第 78、82 行分别使用 `addDecl (.defnDecl ...)`、`addDecl (.thmDecl ...)`；没有插入 `axiomDecl` 的分支。

Lean 4.33.1 的 `Lean/AddDecl.lean` 第 22–34 行表明，内核路径是否跳过检查由 `debug.skipKernelTC` 控制。本项目扫描没有该选项。为验证实测路径，独立构造 `addDecl` 正负例：正确 `True` 定理成功，错误 `False` 定理被内核拒绝。该最小实验验证 API 行为，不等于已经运行本项目全部复制命令。

数学陈述还需要确认紧支撑条件在下游被合理消除，而不是仅因复制命令成功就认为原结论成立；此问题属于主报告中的关键依赖审查。

### 4. 名称含 “unsafe” 的选项

`allowUnsafeReducibility true` 有 37 处；`quotPrecheck false` 有 7 处；`hygiene false` 有 31 处。固定 Lean 4.33.1 源码显示，前者允许某些本来受限的可约性属性更改，可能影响 `simp` 和实例搜索索引；后两者涉及语法引用的名称预检查与宏名称捕获。它们不是 `debug.skipKernelTC`。

同时打开这三个选项后，用 `kexactB True.intro` 证明 `False` 的负例仍被内核拒绝。宏的名称捕获可能影响读者对表面代码的理解，因此需要展开后核对实际定理类型；这一点不能仅靠关闭或打开选项来担保。

### 5. 其他命中

`BuildAid/D1.lean` 至 `D5.lean` 第 4 行只向 `Lean.LibrarySuggestions.nameDenyListExt` 增加若干名称，影响建议检索。其代码没有直接修改定理声明。

补充扫描中出现的 `IO.` 和 `System.` 都是数学命名空间/结构成员名称，不能据此报告为外部进程执行。13 处类似 elaborator 属性的命中均为 `@[elab_as_elim]`。以 `#` 开头的其他命中包括基数记号 `#X`，不应误计为执行命令。补充扫描未发现额外环境插入 API。

## 实际小规模测试

工具链为本项目固定的 Lean 4.33.1。记录在 `minimal_probes/results.json`，复跑入口是 `minimal_probes/run_probes.py --lean /path/to/lean`。

| 测试 | 预期 | 实际 |
|---|---|---|
| `KExactPositive.lean` | 正确 `True` 证明成功 | 退出码 0 |
| `KCopyPositive.lean` | 正确 `True ∧ True` 证明成功 | 退出码 0 |
| `AddDeclPositive.lean` | 正确 `True` 定理可加入 | 退出码 0 |
| `KExactNegative.lean` | 错误 `False` 证明被内核拒绝 | 明确的内核类型不匹配 |
| `KCopyNegative.lean` | 错误 `False` 证明被内核拒绝 | 明确的内核类型不匹配 |
| `AddDeclNegative.lean` | 错误 `False` 定理不能加入 | 明确的内核类型不匹配 |
| `OptionsNegative.lean` | 三个选项同时开启仍拒绝错误证明 | 明确的内核类型不匹配 |

负向测试成功的判据不是“返回错误码”而已，必须出现指定的内核类型不匹配，并排除测试自身语法错误。早期 `AddDecl` 测试曾有语法/monad 使用错误，已修正后重新执行；当前报告及结果只采用修正后的实测日志。

## 官方资料与本地证据

- [Lean.AddDecl 官方 API](https://lean-lang.org/doc/api/Lean/AddDecl.html)：声明添加与内核检查控制。
- [Lean.ReducibilityAttrs 官方 API](https://lean-lang.org/doc/api/Lean/ReducibilityAttrs.html)：可约性属性。
- [Lean.Elab.Quotation.Precheck 官方 API](https://lean-lang.org/doc/api/Lean/Elab/Quotation/Precheck.html)：语法引用预检查。
- 固定版本源代码摘录与完整文件 SHA256：`lean_core_option_evidence.json`。以这些固定版本证据为本次测试解释的直接依据。

## 剩余验证缺口

需要成功编译真正的最终目标、输出其递归公理集合，并对实际编译/导出的证明进行完整复核，才可把这些局部排除结论推进到完整证明的可信结论。未发现明显后门不等于已经证明全部数学构造正确，也不能把人工抽查代替 175,187 个模块及依赖的完整内核验证。
