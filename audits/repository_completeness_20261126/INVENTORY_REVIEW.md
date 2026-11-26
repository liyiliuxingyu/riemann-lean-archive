# 原始工程与附件的完整性复核

本轮对 `liyiliuxingyu/riemann-lean-archive` 的固定主分支基线 `328dc7d7b7c747d8a9e56130787ce7a3c8c3ed27` 与紧凑版候选 `85df6b6d6975c1e64fcfcd4f65eacd60070495c1` 作只读核验。机器报告见 `inventory_report.json`。

## 实际重新检查

| 对象 | 本轮结果 |
| --- | --- |
| 注释目录 | GitHub 递归树返回 3,508 个条目，`truncated=false`。 |
| 57 卷清单 | 全部取回；Git blob 与目录及既有验收记录一致。 |
| 3,380 个 TXT | 逐项匹配远端路径、普通文件类型、字节数及 Git blob SHA-1；无缺失或额外 TXT。 |
| 注释连续性 | 清单中的记录范围从 1 连续到 1,080,769,508；分片字节区间、卷内和卷间记录区间没有缺口或重叠。 |
| 注释总量 | 168,547,118,127 字节；原始数据 61,570,595,788 字节；压缩卷 18,876,901,037 字节。 |
| Release | 60 个附件的名称、ID、大小、`uploaded` 状态和服务器报告的 SHA-256 digest 全部匹配清单，总计 20,270,996,524 字节。 |
| 原始 Lean 工程 | 从稀疏克隆的 Git 树重新枚举 175,190 个文件，其中 175,187 个生产 Lean 源文件和 3 个构建配置；没有读取大正文。 |
| 原工程与候选 | `project/lean/original`、`annotations`、注释工具包子树保持相同；原 `project` 的其他已有文件和子树也保留。 |
| 270 个工程 ZIP 成员 | 267 个原路径存在且大小一致；另 3 个通过下列明确转换保存。 |
| 较早的压缩附件展开 | 对 643 个展开文件重新检查远端路径、大小和文件模式，全部匹配既有展开清单。 |
| 依赖索引 | 5 个 JSONL 分片路径和大小匹配，清单区间连续，总计 214,948,999 字节、909,822 条记录。 |

270 个工程 ZIP 成员中的三项转换如下：

1. `project/lean/RH_AllSources.lean`：展开为 `project/lean/original/` 的 175,190 个文件；1,101,883,390 字节的原单文件仍在 Release。
2. `project/lean/RH_AllSources.dependencies.jsonl`：无损分为 `project/lean/dependencies/` 的 5 个 JSONL 文件，附清单与拼接脚本。
3. `project/third_party/ctex-kit-source.tar.gz`：展开为 `project/third_party/ctex-kit-source/` 的 405 个文件。

原始源码子树为 `b41b516b1f7baee4d83ced235ecc71fd43c97695`；原工程子树为 `e517b335d21898fd2506ad538a1e1775c0aaa4e4`；注释子树为 `f3b35589ee1f34906661921bdeb158f89968b823`。这些不可变 Git 对象把当前路径检查与较早的字节校验记录关联起来。

## 一个需要修正的当前状态字段

`ndjson-files.public.json` 的 `upload_status` 仍为 `pending`，与当前全部完成的实际文件和验收记录不符，应更新为 `complete` 并附当前布局、核验报告的链接。该字段的发现记录对应上述固定基线，后续修正不应被解释为本轮重新下载和散列了全部 168 GB 正文。

另外两份清单应保持用途清晰：

- `release-assets.public.json` 的 `upload_status=complete` 正确；全部 60 个附件元数据已重新核对。
- `project-files.public.json` 是原始 ZIP 的成员清单，其 SHA-256 应保留。19 个曾标记为仅归档的 PDF 构建证据现在也在普通 Git 路径中；可以添加 `inventory_role` 和当前布局报告链接，避免把初始分类误读为当前缺失。
- `docs/release-expansion.json` 是 2026-11-23 的历史快照；其中当时尚未展开注释的状态已被 `annotations/unpacked/progress.json` 和 2026-11-25 验收报告更新。应提供当前状态导航，不宜改写当日历史事实。

工具包保留一个约 2.9 MB 的 `.zst` 测试夹具，因为现有压缩读取测试直接引用它；对应 TXT 已另外展开。它不是未上传完的注释卷。

## 检查范围

本轮重新取得并对照了 GitHub 的文件树、57 份小清单及 Release 元数据，也重新枚举了原始源码路径。没有再次下载、解压或对所有巨大正文计算 SHA-256。大文件逐字节验证及整卷解压验证依赖仓库已有的记录，并通过未变的 Git 对象及清单衔接。本报告不包含新的 Lean 编译、独立内核重放或数学正确性结论。

工作脚本已整理为本目录的 [`reproduce_inventory.py`](reproduce_inventory.py)，输入快照、两个附加清单和候选审计目录树快照一并保留。它固定输入摘要后离线复算历史比较，不访问网络、不读取大 blob、不覆盖原验收报告。输入快照约 3.2 MB；使用方式见[目录 README](README.md)。复算历史快照不会被描述为重新向 GitHub 取证。
