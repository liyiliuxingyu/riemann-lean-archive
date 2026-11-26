# 2026-11-26 仓库完整性验收

- [inventory_report.json](inventory_report.json)：原始工程、注释分卷、Release 附件及成员布局的固定基线核对。
- [INVENTORY_REVIEW.md](INVENTORY_REVIEW.md)：范围、转换关系与发现的陈旧字段。
- [reproduce_inventory.py](reproduce_inventory.py)及同目录四份固定输入：离线复算原始元数据审计，明确保留历史快照含义。
- [integrity_guard_cases.json](integrity_guard_cases.json)：交付验证器的 17 个小型正负例；属于文件/报告检查，不是 Lean 编译。
- [check_integrity_guard_cases.py](check_integrity_guard_cases.py)：上述测试的可复跑源码，报告默认写入临时目录。
- [交付文件清单](../../docs/compact-delivery-manifest.json)：当前小文件的逐项哈希、保留档案对象及成功 CI 的输入记录。
- [完整 CI 原始报告](../lean_compact_20261126/ci_run_45758680116/validation.json)：已通过的 13 阶段验收。

固定基线审计发现的 `ndjson-files.public.json: upload_status=pending` 已在本轮改为 `complete`；原审计保留发现时的事实。原 ZIP 的 270 成员清单及历史展开快照已增加当前状态导航，没有重写当时的验证范围。

交付检查的最新运行结果写到工作目录之外，避免报告与其所记录的清单形成循环散列。主分支的 `Repository delivery integrity` 工作流会重新取得必要文件并运行同一检查。

## 复算记录

离线复算原目录审计（输出路径必须尚不存在）：

```bash
python3 audits/repository_completeness_20261126/reproduce_inventory.py --output /tmp/grh-inventory-reproduced.json
```

脚本禁用自动网络取对象。如果深度为 1 的克隆缺少历史候选对象，可先显式取回该固定提交的树元数据，再重新执行：

```bash
git fetch --filter=blob:none --depth=1 origin 85df6b6d6975c1e64fcfcd4f65eacd60070495c1
```

复跑轻量验证器的 17 个小型正负例：

```bash
python3 audits/repository_completeness_20261126/check_integrity_guard_cases.py
```

以上复算与测试均不执行新的 Lean 构建，也不重新下载注释正文。
