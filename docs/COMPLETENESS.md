# 仓库完整性：范围、证据与复查方法

日期：2026-11-26。这里的“完整”指现有工程及归档清单中的文件有明确去向、当前紧凑工程具备构建与续作所需的源码和配置、已验证结论有可保存的证据。中文数学稿的待展开部分、独立内核复核等研究任务另见[接续说明](CONTINUATION.md)。

## 第一步：按清单核对 GitHub 上的文件

本轮对固定主分支基线 `328dc7d7…` 和交付分支 `85df6b6…` 的远端 Git 元数据及 Release 清单重新核对，未发现应有文件缺失。完整结果见[目录审计](../audits/repository_completeness_20261126/inventory_report.json)及[中文说明](../audits/repository_completeness_20261126/INVENTORY_REVIEW.md)。

| 对象 | 本轮已核对的数量与范围 |
| --- | --- |
| 原始 Lean 工程 | 175,187 个 Lean 源文件与 3 个配置文件；路径重新枚举，原 Git 子树保持。 |
| 完整中文注释 | 57 份卷清单、3,380 个普通 TXT；逐项匹配路径、大小、普通文件模式及 Git blob。 |
| 注释连续性 | 1–1,080,769,508 条原记录连续，卷内和卷间的记录及字节范围无缺口、无重叠；TXT 合计 168,547,118,127 字节。 |
| 原工程 ZIP 成员 | 270 个全部有归属：267 个原路径，另 3 个采用下列可恢复布局。 |
| 较早展开文件 | 643 个普通文件的路径、大小与模式重新匹配。 |
| Release 备份 | 60 个附件的名称、ID、大小、上传状态及服务器 SHA-256 digest 全部匹配，总计 20,270,996,524 字节。 |

三项布局转换是：`RH_AllSources.lean` 恢复成完整原模块树（原单文件仍在 Release）；214,948,999 字节的依赖索引分为 5 个可无损拼接的 JSONL；CTeX 源码包展开为 405 个普通文件。目录映射有记录，不能把原 ZIP 的 270 个成员数当成当前 Git 文件总数。

本轮未重新下载或重新散列全部 168.55 GB 注释正文。较早的逐字节验证与本轮检查通过未变化的 Git 子树及卷清单衔接；文件元数据核验与正文 SHA-256 重算分别记录。

原始元数据快照和[离线复算脚本](../audits/repository_completeness_20261126/reproduce_inventory.py)一并保留，运行说明见[审计目录](../audits/repository_completeness_20261126/README.md)。复算固定快照与重新访问 GitHub 的实时检查分别标明。

## 第二步：逐文件固定紧凑工程和交付材料

[compact-delivery-manifest.json](compact-delivery-manifest.json) 记录紧凑目录的全部交付文件、所需说明、验证脚本和原始验收资料的大小、SHA-256 与 Git blob。清单同时固定原始档案的 Git 对象，避免新增紧凑版时遗漏或改动已有内容。

清单自身不包含自身散列，以避免循环；运行结果会给出整份清单的 SHA-256。`.lake`、`verification-output`、Python 缓存等可再生产物不属于交付内容。Git 属性固定交付文件的原始字节，避免 Windows 检出时的换行转换破坏校验。

从仓库根目录运行：

```bash
python3 tools/verify_compact_delivery.py --output /tmp/compact-delivery-check.json
```

工具要求 Python 3.11+ 与 Git，使用标准库。它检查缺失、多余的紧凑源文件、字节变化、错误的目录对象、CI 报告和被测输入之间的不一致；失败返回非零。验证器的 17 个小型正负例记录见[测试记录](../audits/repository_completeness_20261126/integrity_guard_cases.json)，[测试源码](../audits/repository_completeness_20261126/check_integrity_guard_cases.py)可复跑。这项快速检查不会重新运行 Lean。

## 第三步：保存完整构建和五个出口的实际验收

[完整 CI 运行 45758680116](https://github.com/liyiliuxingyu/riemann-lean-archive/actions/runs/45758680116) 已成功完成，验证源码提交为 `c01eb3d7b21c4884b6c31b492f85635d4cd0669c`，固定 Lean 4.35.0 与 Mathlib `56a005855ea17e0b0958f73ec801ae140b0a1679`。

- 原始报告的 13 个阶段全部通过，所有退出码为 0。
- `lake build` 完成 9843 个构建任务，实测耗时 8852.495 秒。
- 五个实际公开定理均通过独立预期类型、参数及声明种类检查。
- 五个定理的公理均为 `propext`、`Classical.choice`、`Quot.sound`。
- 构建前后的来源完整性报告一致，最后的九个依赖版本检查也通过。

[原始 JSON 与日志](../audits/lean_compact_20261126/ci_run_45758680116/)已经作为 16 个普通文件纳入仓库，避免依赖临时 artifact 的保留期限。原 ZIP 摘要已核对，逐文件摘要与独立日志复核见[CI 复核记录](../audits/lean_compact_20261126/ci_log_review.json)。交付清单的 `verified_ci.inputs` 继续检查当前证明源码、配置及验收脚本与该次成功运行一致。

## 第四步：主分支持续复查与继续工作

`Repository delivery integrity` 工作流对主分支、交付分支和 PR 做轻量检查。它从 GitHub 重新检出必要文件，核对交付清单、保留档案的 Git 对象，以及已成功构建的证明输入。工作流的绿色结果表示这些检查通过；它不会被写成“再次完整编译通过”。

需要重新编译时，可以手动运行 `Compact Lean build and public interface` 工作流，或依照[紧凑工程 README](../project/lean/compact/README.md)在本地运行 `ci_validate.py`。编译器和 Mathlib 等依赖按固定版本安装或获取；仓库不保存可再生的编译缓存，因此不是离线编译环境。

改动证明源码、依赖、工具链或旧验收脚本后，旧 CI 记录不能自动代表新版本。应完成新的全量验收，再保存新原始报告并更新对应输入清单。仅更新说明文档时，也要更新交付文件的哈希，并让轻量检查实际通过。

当前已修正 `ndjson-files.public.json` 的过期 `pending` 状态。原 ZIP 清单和 2026-11-23 的历史展开报告保留原始含义，并提供当前状态导航。原始 4.33.1 大工程的完整重编、Comparator、独立内核重放、逐条数学审稿及中文稿的剩余展开均仍单独列为待处理。
