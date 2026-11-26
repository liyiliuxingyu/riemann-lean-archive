# 接续说明

更新时间：2026-11-26。仓库：`liyiliuxingyu/riemann-lean-archive`。优先从[完整性说明](COMPLETENESS.md)、[紧凑工程](../project/lean/compact/README.md)及[中文代码导航](LEAN_COMPACT_GUIDE.md)开始。

## 已完成与实际通过

- 上游 `lsernau/grh-lean@72fead102f663d5c7a407964a13dc0cf9d977207` 的紧凑工程已按原字节引入：794 个生产模块、7,420,187 字节、112,827 个物理行。
- 本仓库完整 CI `45758680116` 已成功，实际被测源码提交为 `c01eb3d7b21c4884b6c31b492f85635d4cd0669c`。13 个阶段、完整 Main 构建、五个实际类型与公理检查均通过；原始报告及日志已经保存在普通 Git 文件中。
- 原始 175,190 个源码/配置、57 卷注释的 3,380 个 TXT、60 个 Release 备份、270 个 ZIP 成员的布局去向及较早展开文件已重新做目录/元数据核对，未发现缺失。
- 增加交付文件哈希、保留档案的 Git 对象及已验证证明输入的联合检查；根目录 NDJSON 清单的陈旧 `pending` 已修正。
- 原始归档、历史失败记录与当时的验证边界继续保留，不能用本次紧凑版成功覆盖它们。

## 尚未完成或尚未验证

1. 原始 Lean 4.33.1 的 175,187 模块大工程尚未重新完整构建。此次成功来自独立 Lean 4.35.0 紧凑工程。
2. Comparator、其他独立 Lean 内核重放、逐条数学语义审查和同行评议尚未执行。
3. 31 页中文 `ctexbook` 稿仍有标明依赖的上游论证未完全展开，包括自守/Galois 表示、模性长度窗口、几何构造及部分尺度估计。紧凑版构建成功不等于中文纸面稿已经全部完成。
4. 本次没有重新下载和散列全部 168.55 GB 注释正文；本轮远端元数据核对与既有字节检查通过固定 Git 对象关联。
5. 当前 Git 路径清单未找到 MP4/WebM/MOV/AVI 科普视频成品；早先的视频目标不能标为已交付。

## 只取继续本轮所需的小文件

以下是 Bash / Git Bash 命令，使用部分克隆与稀疏检出。大型归档的 Git 树可核验，正文按需要另取。

```bash
git clone --filter=blob:none --no-checkout --depth 1 --branch main https://github.com/liyiliuxingyu/riemann-lean-archive.git
cd riemann-lean-archive
git sparse-checkout set --no-cone --stdin <<'EOF'
/README.md
/THIRD_PARTY_NOTICES.md
/.gitattributes
/.gitignore
/*public.json
/.github/workflows/
/project/lean/compact/
/docs/
/audits/lean_compact_20261126/
/audits/repository_completeness_20261126/
/tools/verify_compact_delivery.py
EOF
git read-tree -mu HEAD
python3 tools/verify_compact_delivery.py
```

不要对尚未取回的大归档使用会逐个读取 blob 的体积统计命令；需要路径清单时可使用不带 `-l` 的 `git ls-tree`。查看中文 PDF/TeX 或某一注释卷时，再显式增加对应稀疏路径。

## 下一步起点

- **继续精简 Lean：**从 `src/Main.lean` 的五个出口及 `src/New/Main.lean` 开始，按中文导航追溯共享输入。全部 794 个模块在导入闭包内，不能仅凭文件名或文本搜索没有引用就删除。一次修改一处，保留命题和假设，随后重建受影响模块并完成最终接口/公理验收。
- **独立验证：**以固定版本和五个根声明为对象运行 Comparator 或独立内核，保存实际命令、版本、日志及未通过事项。原始 `Challenge.lean` 的五个 `sorry` 属于比较器题面，排除在生产 Main 导入闭包中。
- **中文数学稿：**从 `project/proof_process/` 的阶段说明与 `project/chapters/` 已标明的待展开处继续；本轮没有新增页码进度，不应伪造“下一页已完成”。使用原 `ctexbook` 工程，并同步区分原始与紧凑论证的来源。
- **变更后的交付：**更新相应文件清单；证明输入有变化时必须先完成新全量验收并保存证据，不能只刷新哈希把旧成功记录用于新证明。

`project/README_接续说明.txt`、`project/接续状态.json` 及 `project/SHA256SUMS.txt` 属于原工程 ZIP 的历史交付布局。当前仓库应联合使用本文件、交付清单和本轮审计记录，不要把旧 ZIP 成员总数或初始分类误读为当前仓库状态。
