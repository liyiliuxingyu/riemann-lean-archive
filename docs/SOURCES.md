# 来源与版本

原始发布入口：<https://math.mit.edu/~drew/grh/>。

原 Lean 工程最初为 14 个分卷。源码汇编阶段原站返回 HTTP 403，实际使用发布页所指公开镜像的固定提交恢复源树，没有把镜像恢复计作重新下载原始 14 个分卷。

- 镜像提交：`40e56bab026552e089d7afcfeff08d2defb9c005`。
- 固定源码归档：<https://codeload.github.com/leanprover-community/riemann-hypothesis/tar.gz/40e56bab026552e089d7afcfeff08d2defb9c005>。
- Lean：`v4.33.1`。
- Mathlib：`0df444a360eaa60ab8c11dca51a86af692955474`。

最新完整工程 ZIP 内的 `riemann_human/provenance/` 保存原分卷预期哈希、固定镜像来源及源码汇编与恢复核验记录。`project-files.public.json` 保存该 ZIP 内全部成员的实际内容哈希。

仓库的三个小型工具从该工程 `riemann_human/tools/` 原样复制，源成员和哈希记录在 `tools/SOURCE.json`。这三个文件未在本次整理中改写正文。

NDJSON 来源：<https://math.mit.edu/~drew/grh/solution.ndjson.zst>。

`solution_annotation_toolkit.zip` 保存注释源码、独立核验器、schema、预览与报告；`schema/exporter_commit.json`、`schema/license_sources.json` 及 `tools/vendor/PROVENANCE.json` 记录引用代码和依赖的来源版本。`ndjson-files.public.json` 保存 57 卷的行号、字节数和哈希。

本次仓库准备只复核最新 ZIP 与最小注释元数据，没有重新下载全部注释卷、重跑完整 Lean 构建或独立内核检查。详细核验范围见根目录 README。中文稿中尚未完全展开的上游数学依赖见完整工程 `README_接续说明.txt` 与 `接续状态.json`。
