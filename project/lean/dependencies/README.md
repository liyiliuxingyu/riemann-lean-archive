# 依赖索引分卷

这里保存 `../RH_AllSources.dependencies.jsonl` 的全部原始字节，共 214,948,999 字节、909,822 行。文件按完整行拆为 5 卷，每卷不超过 48 MiB（50,331,648 字节）。分卷没有重新编码、解析后重写、增删换行或压缩；按清单顺序直接连接即可精确恢复原件。

## 恢复与核验

使用 Python 3.9 或更新版本，仅依赖标准库。从 `project/lean/` 运行：

```sh
python3 dependencies/join_parts.py
```

脚本默认在本目录的父目录生成 `RH_AllSources.dependencies.jsonl`。它逐一核验每卷的大小、SHA-256、行数及末尾换行，再核验完整输出。只有全部通过后才安装最终文件。若目标文件已经存在，脚本先核验现有文件：相同则成功返回，内容不同则拒绝覆盖。

也可以指定输出路径：

```sh
python3 dependencies/join_parts.py --output /path/to/RH_AllSources.dependencies.jsonl
```

恢复时需为完整输出预留约 205 MiB 的可用空间。脚本临时文件位于输出目录，并在完成或失败后清理自身创建的临时文件。

## 清单字段

`manifest.json` 只记录相对文件名和来源归档成员路径。每卷记录 SHA-256、字节数、行数、原始首末行号，以及原始起止字节偏移。行号从 1 开始且两端均包含；字节偏移从 0 开始，结束偏移不包含末尾字节。

原件 SHA-256：

```text
1321696d0bd1141923163735d6479916ba1bf4061e2e78c7427fa0e3fe36c431
```

邻近的 `../RH_AllSources.index.jsonl` 是从同一工程 ZIP 按原始字节直接提取的独立索引文件，不需要连接操作。
