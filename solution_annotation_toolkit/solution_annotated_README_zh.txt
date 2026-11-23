solution.ndjson 完整逐行中文注释版

一、交付内容

输入文件：
https://math.mit.edu/~drew/grh/solution.ndjson.zst

本次对全部 1,080,769,508 条原始 NDJSON 记录逐行添加中文注释。
每一条原始物理行前，恰好有一条以“-- @line 原始行号”开头的说明。
原始 JSON 的字段顺序、空白、数字、字符串转义和换行保持不变。

原文解压字节数：61,570,595,788
带注释文本字节数：168,547,118,127
注释分卷压缩字节数：18,876,901,037
独立可解压分卷：57 卷
每卷均在完整“注释 + 原始记录”之后结束；原始行号跨卷连续。

完整数据是 solution_annotated.part001.txt.zst 等全部分卷。
solution_annotated_preview_2000.txt 仅为原始第 1–2,000 行的阅读预览。
solution_annotated_examples.txt 是从真实原文选取的各类记录示例。
solution_annotated_parts.tsv 和 parts.jsonl 列出每卷准确行号范围、大小及 SHA-256。

二、如何阅读

示例（来自真实原始第 20 行）：

-- @line 20 E8：函数应用，以E7为函数、E2为实参。
{"app":{"arg":2,"fn":7},"ie":8}

这里 @line 20 是原文件的第 20 行。E8 是表达式表中的编号 8。
它表示新建 E8 = E7(E2)，不能把 8 或 20 当作数学证明的第 8 或第 20 步。

注释约定：
  N123：名称表编号 123，对应 JSON 中的 in 或名称引用。
  L123：宇宙层级表编号 123，对应 il 或层级引用。
  E123：表达式表编号 123，对应 ie 或表达式引用。
  N0：预定义匿名名称；L0：预定义零层级。
  E0：原文件中实际定义的第一个表达式，并非预定义占位项。

名称行显示名称前缀、组件和组装后的名称。声明行显示完整名称、宇宙参数、
类型引用以及相应的值或证明项引用。表达式行显示构造方式和具体引用。
归纳声明行还逐项展开解释 types、ctors、recs 和 rules 中的字段。
超长自然数/字符串字面量的注释显示一个标明截断的预览；完整原值仍在紧随
其后的原始 JSON 中。控制字符在注释中转义，防止改变物理行边界。

三、文件性质和注释范围

该文件是 lean4export 的内核表达式与声明导出数据，并不是通常带 tactic
步骤的 .lean 源代码。大量记录只是共享语法节点；一行通常不等于一条
独立的数学推理。本次注释解释每条记录的字段、构造和编号引用关系。

阅读版加入了 -- 注释行，因此是 UTF-8 文本（.txt），不能直接作为纯 NDJSON
交给内核读取器。需要时，先用附带工具删除注释并恢复原始 NDJSON。

本次完成了数据格式/编号检查和字节保真检查；没有重新执行 Lean 内核、
nanoda 或 con-leche 对整个证明环境的逻辑验证。定理行中的“证明项”表示
该行给出了证明项引用，不表示注释程序重新证明了这一定理。

四、查看与解压

每一卷是独立 Zstandard 压缩帧，可单独解压和查看，无需先拼接其他卷。
有 zstd 命令行程序时，在下载目录运行：

  zstd -dc solution_annotated.part001.txt.zst > part001.txt

仅流式阅读某一卷、避免保存大型解压文本：

  zstd -dc solution_annotated.part001.txt.zst | less

按原始行号只提取所需的几行（工具包含 Python 脚本；需要 Python 3 与 zstd）：

  python3 tools/read_annotated_lines.py --manifest parts.jsonl --parts-dir /下载分卷目录 --start 19 --end 21 --output selected_lines.txt

脚本先按清单定位相应分卷，输出准确的“注释 + 原始记录”对。
如果清单和分卷放在同一目录，可省略 --parts-dir。

如确需合并成一个文本（Linux/macOS shell，文件名按编号排序）：

  zstd -dc solution_annotated.part*.txt.zst > solution_annotated.txt

若只想合成一个压缩文件，可拼接独立的 Zstandard 帧：

  cat solution_annotated.part*.txt.zst > solution_annotated_all.txt.zst

生成的压缩文件仍须使用支持串联 Zstandard 帧的解压器；zstd 命令行程序支持。

合并后的文本需要 168,547,118,127 字节磁盘空间。
原始纯 NDJSON 为 61,570,595,788 字节。
通常应按卷阅读；普通文本编辑器不适合一次加载整个文件。

本交付的注释分卷采用常规 zstd 窗口；源文件 solution.ndjson.zst 的压缩方式
不同，解压源文件需使用 zstd -dc --long=30。

五、核对完整性与恢复原始文件

工具包中的 tools/ 独立验证工具可逐卷检查压缩文件 SHA-256、连续原始行号、
一条注释对应一条记录、各卷原文哈希，以及整个原文哈希。
默认仅流式检查，不落地写出 61.57 GB 原文；需要恢复原文时使用 --restore。
精确编译和命令行用法见工具包中的验证工具说明文件。

源文件压缩 SHA-256：
61a8938ad5f5e57397c1c0e3b954916af546d9004ade01c3555744a681b05381

原始 NDJSON（删除注释后）SHA-256：
5ea74b912147c5c93cc2b6d70cc727cf908df2f62ac6a20480a3fa02f6be244e

所有分卷必须齐全且按 parts.jsonl 顺序处理。
annotation_summary.json 是注释程序输出统计。
independent_verification.json 是独立还原程序的全量验证结果。
generation_provenance.json 记录输入来源、冻结程序哈希和运行参数。
review/ 中的小样本测试报告只针对各报告列明的范围；不能替代全量报告。

六、格式与版本

真实首行声明：NDJSON 格式 3.1.0；导出器自报版本 3.1.0；Lean 4.33.1。
lean4export 固定提交：15f6055e299ad5b89345e533cc2192f4cc00f659。
Lean 固定提交：819816b2e0a3bf405af45ae5c7af2491d8f5bee6。
网站的导出器仓库标签 v4.33.0 与格式版本 3.1.0 是不同的版本概念。

schema/format_spec.json 记录全部 24 种顶层记录和 4 种嵌套结构的字段规范。
schema/format_notes_zh.txt 详细解释 bvar、letE.nondep、def.hints、all、
isReflexive、recursor.k 等容易误读的字段。该文件中 Name#、Level#、Expr#
分别等价于本注释正文的 N、L、E。
schema/source_hashes.json 列出所采用官方源码快照的 URL 与哈希。

七、本文件实际记录统计

总记录：1,080,769,508
未知记录类型：0
  app: 989,707,003 行
  axiom: 3 行
  bvar: 7,426 行
  const: 2,131,429 行
  def: 214,241 行
  forallE: 23,893,670 行
  imax: 352 行
  inductive: 7,969 行
  lam: 47,121,325 行
  letE: 2,259,622 行
  max: 18,634 行
  meta: 1 行
  natVal: 27,168 行
  num: 6,939,987 行
  opaque: 91 行
  param: 185 行
  proj: 65,718 行
  quot: 4 行
  sort: 812 行
  str: 7,125,163 行
  strVal: 162 行
  succ: 2,433 行
  thm: 1,246,110 行

声明记录可能包含多个嵌套声明。因此“记录数”“表达式数”“声明数”是不同
统计量，不能把它们混用。所有统计来自本次完整文件处理。

来源说明：
https://math.mit.edu/~drew/grh/
https://github.com/leanprover/lean4export/blob/15f6055e299ad5b89345e533cc2192f4cc00f659/format_ndjson.md
