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

完整构建和最终五个出口的类型/公理验收以仓库 `Compact Lean build and public interface` 的实际运行日志和 `validation.json` 为准。尚未有通过报告时，不应把上游的成功自述写成此仓库已复现。
