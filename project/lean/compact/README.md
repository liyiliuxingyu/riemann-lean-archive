# GRH 紧凑版工程

本目录引入 [lsernau/grh-lean](https://github.com/lsernau/grh-lean) 的 `grh-compact`，固定在提交 `72fead102f663d5c7a407964a13dc0cf9d977207`。这是基于上游完整重写的独立工程；原始归档仍在 [`../original/`](../original/)。本目录没有把旧工程的内部模块逐一替换，也不声称两个 Lean 版本的全部环境已证明等价。

## 实际规模与接口

生产源码 `src/**/*.lean` 共 **794 个文件、7,420,187 字节、112,827 个物理行**；静态去注释计数为 **76,149 行**。全部 794 个模块都被 Main 的显式导入闭包覆盖，未发现可以按不可达性删除的源模块。

`src/Statements.lean` 与原归档逐字节相同，Git blob 为 `1cd1bce93344065936b2b392b23306254e0785ef`。五个公开定理是 `riemannHypothesis`、`riemannZeta_eq_zero_re`、`LFunction_ne_zero_of_half_lt_re`、`LFunction_eq_zero_re`、`LFunction_eq_zero_re_of_isPrimitive`。GRH 的覆盖对象是 Dirichlet L 函数。

原工程使用 Lean 4.33.1 / Mathlib `0df444a360eaa60ab8c11dca51a86af692955474`；本候选固定 Lean 4.35.0 / Mathlib `56a005855ea17e0b0958f73ec801ae140b0a1679`。请在本目录运行 Lake，避免混用构建产物。

## 当前验证状态

**本仓库已实际通过完整构建、五个公开出口的精确类型及公理检查。** [GitHub Actions 运行 45758680116](https://github.com/liyiliuxingyu/riemann-lean-archive/actions/runs/45758680116) 于 2026-11-26 完成，13 个阶段全部通过；`lake build` 用时 8852.495 秒，完成 9843 个构建任务。五个定理的公理均仅为 `propext`、`Classical.choice`、`Quot.sound`。

实际被测提交为 `c01eb3d7b21c4884b6c31b492f85635d4cd0669c`。[原始 validation.json](../../../audits/lean_compact_20261126/ci_run_45758680116/validation.json)、[接口日志](../../../audits/lean_compact_20261126/ci_run_45758680116/public-interface.log)及[公理日志](../../../audits/lean_compact_20261126/ci_run_45758680116/axioms.log)已作为普通文件保存，不依赖临时 artifact 的保留期限。仓库完整性检查会比较当前证明输入与该次成功运行所用输入的哈希。

此前本机因磁盘不足未能取得完整 Mathlib 缓存的失败记录仍保留，它与后来成功的远端构建分别记录。上述成功范围不包括 Comparator、其他独立内核重放或数学同行评议。

详细记录见 [`../../../audits/lean_compact_20261126/`](../../../audits/lean_compact_20261126/) 和 [仓库简化说明](../../../docs/LEAN_COMPACT.md)。从五个出口追溯核心依赖，可先读[中文代码导航](../../../docs/LEAN_COMPACT_GUIDE.md)。

## 构建与验收

安装 `lean-toolchain` 指定的官方 Lean，然后在本目录执行：

```bash
python3 scripts/verify_sources.py --output /tmp/compact-source-check.json
LEAN_NUM_THREADS=2 python3 scripts/ci_validate.py
```

验证脚本浅取九个锁定的依赖、获取 Mathlib 缓存并删除压缩缓存副本，先在纯 Mathlib 环境编译预期陈述，再构建完整默认目标，最后检查五个实际定理的类型、参数和公理。检查结果与日志写入 `verification-output/`；只有所有阶段成功，`validation.json` 的 `passed` 才为 `true`。

`scripts/ArchiveInterfaceCheck.lean` 对实际编译出的定理做内核类型赋值，并检查 `ConstantInfo`，拒绝额外的显式/隐式参数、额外宇宙参数、替换成 axiom 的声明及白名单外公理。允许的公理仅为 `propext`、`Classical.choice`、`Quot.sound`。

`Challenge.lean` 是上游 Comparator 题面，故意含五个 `sorry`；它不在生产源码的 Main 导入闭包或默认构建目标内。不要把整个目录宣传为“没有任何 sorry”。本验证脚本没有执行 Comparator 或另一套独立内核重放。

## 来源与解释范围

全部上游生产 Lean 源码及三份构建配置保持原字节；逐文件哈希和来源记录见 [UPSTREAM.json](UPSTREAM.json)。原上游 README 保存为 [UPSTREAM_README.md](UPSTREAM_README.md)，阅读路线见 [GUIDE.md](GUIDE.md)。Apache 2.0 的 [LICENSE](LICENSE)、[NOTICE](NOTICE)、[ATTRIBUTION.md](ATTRIBUTION.md) 完整保留。

上游改写采用共享的规模估计、已证明的主不等式输入接口、Mathlib 引理及更紧凑的证明表达。部分内部背景定义是当前论证需要的形式，不能仅根据名字认定已完整重建相应文献理论。源码更短、Lean 构建通过或公理名单合格，分别是不同范围的结论；数学语义审查与同行评议仍需单独进行。
