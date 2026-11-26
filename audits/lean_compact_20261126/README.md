# 紧凑版引入与验证记录

本目录记录参照 `lsernau/grh-lean@72fead102f663d5c7a407964a13dc0cf9d977207` 进行的源码简化工作。

- `REFERENCE_REVIEW.md`：上游具体简化方法、定义与信任边界。
- `upstream_static_review.json`：可读版与紧凑版的同口径统计、导入图与静态筛查。
- `baseline_source_audit.json`：原工程既有固定审计，原 `src` 子树与本轮基线相同。
- `compact_static_check.json`：本轮候选实际重新散列与导入检查。
- `semantic_review.json`、`semantic_review.txt`：五个目标及 Mathlib 端点定义对照、实际验证边界。
- `local_build_attempt.json`、`local_cache_failure_excerpt.txt`：本机工具链安装通过，但全缓存因磁盘不足失败的记录。
- `root_layout_probe.json`：独立纯 Lean 项目中实际验证辅助模块的输出和导入路径。
- `integration_snapshot.json`：全部 807 个上游文件的哈希，以及原始源码、注释目录的 Git 子树不变检查。

## 已完成的完整 CI 验收

[运行 45758680116](https://github.com/liyiliuxingyu/riemann-lean-archive/actions/runs/45758680116) 已于 2026-11-26 成功完成，实际源码提交为 `c01eb3d7b21c4884b6c31b492f85635d4cd0669c`。13 个阶段全部通过；完整构建、五个公开出口的精确类型和公理检查均有直接日志证据。

- [`ci_run_45758680116/validation.json`](ci_run_45758680116/validation.json)：原始报告，`passed: true`。
- [`ci_run_45758680116/`](ci_run_45758680116/)：从成功运行的 artifact 原样展开的全部 16 个 JSON/日志文件。
- [`CI_REVIEW.md`](CI_REVIEW.md)、[`ci_log_review.json`](ci_log_review.json)：独立读取作业日志与下载的 artifact 交叉核对。
- [`ci_success_excerpt.txt`](ci_success_excerpt.txt)：构建完成、五个接口和五项公理的短摘录。

artifact ZIP 的 SHA-256 已实际核对为 `91c79096749483aee821f7b279289615a16360b74216ad28631a9ee486e6192c`。原始成功记录与较早的本机磁盘不足失败记录均保留。此成功结果不包含 Comparator、其他独立内核重放、逐条数学语义审查或同行评议。
