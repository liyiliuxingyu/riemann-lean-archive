# 紧凑 Lean 工程 CI 结果独立复核

复核对象为 [GitHub Actions 运行 45758680116](https://github.com/liyiliuxingyu/riemann-lean-archive/actions/runs/45758680116)，实际验证提交为 `c01eb3d7b21c4884b6c31b492f85635d4cd0669c`。

## 已确认的执行结果

本次同时检查了 GitHub 作业元数据、完整作业日志，以及已下载的原始验收 artifact。结论来自实际执行记录，不仅来自工作流总状态。

- `validation.json` 的 `passed` 为 `true`，13 个阶段全部为 `passed` 且退出码为 0。
- `lake build` 实际输出 `Build completed successfully (9843 jobs).`；9843 是 Lake 报告的构建任务数，不是本工程生产源码模块数。
- 完整构建耗时为报告实测的 **8852.495 秒（约 2 小时 27 分 32 秒）**。
- 独立预期陈述与接口检查器先完成编译，随后完整项目构建成功，再执行公开接口及公理检查。
- 五个实际公开定理分别输出一条 `INTERFACE_OK`，与预期目标的对应关系完整。
- 五个最终出口的 `#print axioms` 均实际输出相同集合：`propext`、`Classical.choice`、`Quot.sound`。
- 构建前后的源文件完整性 JSON 完全一致，均核对了 797 项生产源码/构建配置与 794 个生产模块的 Main 导入闭包。
- 最终依赖锁检查实际通过；完整构建日志没有 `declaration uses 'sorry'` 警告。

| 实际公开定理 | 验收的预期目标 |
| --- | --- |
| `riemannHypothesis` | `ArchiveExpected.RiemannZetaZerosOnLine` |
| `riemannZeta_eq_zero_re` | `ArchiveExpected.RiemannZetaZerosOnLine` |
| `LFunction_ne_zero_of_half_lt_re` | `ArchiveExpected.DirichletLNonvanishingRightOfHalf` |
| `LFunction_eq_zero_re` | `ArchiveExpected.DirichletLZerosOnLine` |
| `LFunction_eq_zero_re_of_isPrimitive` | `ArchiveExpected.PrimitiveDirichletLZerosOnLine` |

## 记录与运行环境

作业标签为 `ubuntu-24.04`，使用官方 Lean 4.35.0，Lean 提交为 `eb6cafb7290e8bd5f2937522d8d804f58f02bafc`，Mathlib 固定为 `56a005855ea17e0b0958f73ec801ae140b0a1679`。作业于北京时间 **2026-11-26 15:29:16** 完成，验证脚本在此前结束并写入成功报告。

原始 artifact 为 `compact-lean-validation-45758680116-1`，ID 为 `15095728132`，含 **16 个普通日志或 JSON 文件**。其 ZIP 大小为 36,324 字节，GitHub 元数据摘要为：

```text
91c79096749483aee821f7b279289615a16360b74216ad28631a9ee486e6192c
```

逐文件摘要、五项接口日志与公理名单见 `ci_log_review.json`；精简执行证据见 `ci_success_excerpt.txt`。原始 artifact 的下载与 ZIP 摘要复核由主任务完成，本复核交叉检查了已解压文件与独立读取的完整作业日志。

脚本开始时可用磁盘为 88,205,934,592 字节，结束时为 70,860,816,384 字节。两者是实际快照，不能据此声称测得了峰值磁盘、峰值内存、CPU 利用率或仅 Mathlib 缓存的体积。

## 验证边界

本轮没有执行 Comparator、其他独立 Lean 内核实现的重放，也没有完成逐条数学语义审查或同行评议。`Challenge.lean` 保留五个上游比较器题面的 `sorry`，排除在生产 Main 导入闭包和默认构建目标之外。

本报告绑定上述实际被测试的提交。后续提交如只改变文档和审计记录，可以另行通过 Git 路径/对象比对确认生产源码与验收脚本未变；若改变证明源码、工具链、依赖或验证程序，应重新执行相应验收。
