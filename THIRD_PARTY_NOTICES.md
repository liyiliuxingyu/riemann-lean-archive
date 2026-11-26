# 第三方材料与许可说明

上游材料继续适用各自许可和版权声明。本仓库没有为全部源码、字体、排版资源与衍生说明重新指定统一许可证。

## 完整工程 ZIP

`黎曼猜想_人类可读证明与续作工程.zip` 保持已核验文件原样。

- Fandol 的许可文件保存在 `riemann_human/texmf/doc/fonts/fandol/COPYING`，并在 `riemann_human/texmf/fonts/opentype/public/fandol/COPYING` 保留一份。
- 原工程 ZIP 的 CTeX 对应源码归档位于 `riemann_human/third_party/ctex-kit-source.tar.gz`。普通 Git 已将它展开为 [project/third_party/ctex-kit-source/](project/third_party/ctex-kit-source/)，保留全部 405 个源码与随附文件；组件许可及版权声明以其中原文件为准。原包映射及校验见 [独立文件说明](docs/INDIVIDUAL_FILES.md)。
- CTeX、xeCJK、zhnumber、Fandol 的资源和既有声明随完整工程保留。
- Lean 项目、Mathlib 及其他依赖继续按各自源码与工程配置中的许可和版本处理。本说明不改变上游授权范围。

## NDJSON 注释工具包

`solution_annotation_toolkit.zip` 保留以下许可和来源文件：

| 材料 | 许可文件 | 来源记录 |
| --- | --- | --- |
| Lean 4 代码片段 | `schema/LICENSE.lean4` | `schema/license_sources.json` |
| lean4export | `schema/LICENSE.lean4export` | `schema/exporter_commit.json`、`schema/license_sources.json` |
| simdjson | `tools/vendor/LICENSE.simdjson` | `tools/vendor/PROVENANCE.json` |

这三个随附许可文件包含 Apache License 2.0 文本；使用时仍须同时阅读相应版权与来源声明。

## 小型入口工具

`tools/export_lean_bundle.py`、`tools/extract_one_module.py`、`tools/RHEntry.lean` 从完整工程原样复制，来源和内容哈希见 `tools/SOURCE.json`。本次整理未添加新的全局许可声明，未改写这些文件的原注释。

## lsernau/grh-lean 紧凑版

`project/lean/compact/` 的生产源码与构建配置取自 `lsernau/grh-lean` 提交 `72fead102f663d5c7a407964a13dc0cf9d977207`，上游版权声明为 Copyright 2026 Anthropic, PBC，许可为 Apache 2.0。原 `LICENSE`、`NOTICE`、`ATTRIBUTION.md` 已完整保留；原 README 保存为 `UPSTREAM_README.md`。逐文件映射和本仓库集成改动见 `UPSTREAM.json`。本说明不把该组件许可扩展到仓库内其他历史材料。
