先读“专项核查报告.txt”。

本包是针对 anyGeometry 截图的专项补充审查，不是完整 RH 证明证书，也不含完整原工程。
evidence 保存原始文件路径、原行号、完整文件 SHA-256、源码链接与文本统计。
本次逐一校验了所列原文件哈希及定义审查所引的精确行段；未重新构建全项目。

tests 保存两份独立的、只用 Lean 核心的逻辑对照例及真实运行输出。
InvalidTrueBridge.lean 故意不能通过；这是预期的类型检查拒绝，不能当作原 RH 工程报错。
重跑命令：python3 tests/run_logic_examples.py --lean /绝对路径/lean
原实验工具链为 Lean 4.33.1。对照例不验证原 RH 工程。

SHA256SUMS.txt 用于核对本包文件，未将其自身纳入自身的哈希列表。
来源网址和范围限制均在主报告中。
