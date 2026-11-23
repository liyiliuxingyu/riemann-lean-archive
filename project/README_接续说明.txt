黎曼猜想：完整源码单文件汇编与人类可读证明（第二版）
整理日期：2026-11-22（北京时间）

一、先打开什么

1. 黎曼猜想_人类可读证明主线.pdf：31页中文数学稿。使用ctexbook默认正文字号、默认中文Fandol字体、章标题与正常字号目录，页边距约21毫米。数学图为TikZ矢量图。
2. proof_process/证明过程_数学说明与关键源码.txt：13个阶段的数学说明，附33个关键模块的逐行原文。
3. lean/RH_AllSources.lean：175187个原Lean模块的完整无损汇编，文件为1101883390字节。索引、直接导入图及统计与它放在同一目录。

二、合并结果及其编译性质

原文件是一个gzip归档的14个分卷。原站本轮返回HTTP403，实际从MIT核验页指向的公开镜像首提交40e56bab026552e089d7afcfeff08d2defb9c005恢复完整源树。原作者gzip预期哈希与本次镜像gzip哈希分别记录，没有冒称重新取得原14分卷。

本轮实测：175187个Lean源文件、17374215行、1030531854字节；另有3个工程配置。旧选源与配置88/88逐字节相同。源码按内部import拓扑顺序汇编，共753261条内部直接导入边；没有缺失的项目内部或未知导入，Mathlib等外部依赖仍按原工程配置取得。

RH_AllSources.lean是源码汇编，尚不是已编译通过的单一Lean模块。原模块正文、import、private、局部作用域、证明体全部保留，不用sorry或axiom替换证明。源码汇编的成功不等于在同一个Lean全局环境里重新编译全部原模块。

已完成全部175187模块的字节与SHA256核验，实际恢复全部模块与3配置，再逐文件读回恢复结果核验，全部通过。源码清单无遗漏或额外模块。本轮没有运行完整原工程Lean构建或独立内核检查；小型RHEntry.lean也未在本机实际编译。

三、恢复原项目与抽取单个模块

需要Python 3.11或更新版本，工具只使用标准库。先进入解压后的riemann_human目录。

校验汇编内部的全部原模块：
  python3 tools/export_lean_bundle.py verify --bundle lean/RH_AllSources.lean

恢复到不存在或为空的目录：
  python3 tools/export_lean_bundle.py restore --bundle lean/RH_AllSources.lean --destination restored/lean

恢复后与汇编逐文件比较：
  python3 tools/export_lean_bundle.py verify --bundle lean/RH_AllSources.lean --against-root restored/lean

只抽取Main模块，避免一次展开全部文件：
  python3 tools/extract_one_module.py --bundle lean/RH_AllSources.lean --index lean/RH_AllSources.index.jsonl --module Main --output selected/Main.lean

抽取工具不覆盖已有输出，并验证所读字节的SHA256。完整恢复不依赖外部index文件，因为汇编内部已带边界、长度、哈希和3个工程配置。

原项目固定Lean v4.33.1、Mathlib commit 0df444a360eaa60ab8c11dca51a86af692955474。恢复后仍需按原lake配置准备工具链和外部依赖。tools/RHEntry.lean仅是调用原公开定理的小型入口，不是完整证明源码的替代。

四、继续编辑数学稿

可编辑同名TeX，或修改chapters中的分章后执行：
  python3 assemble.py
  python3 build_pdf.py 黎曼猜想_人类可读证明主线.tex

需要XeLaTeX、latexmk、pdfinfo及标准数学/TikZ包。texmf随包附CTeX、xeCJK、zhnumber及Fandol字体和许可证；third_party保留对应CTeX源码归档。DejaVu Sans Mono用于拉丁代码记号。build_pdf.py在原工作区使用已有私有格式，在其他环境使用系统XeLaTeX格式与本地texmf补充；它不自动下载软件。

五、数学证明已经展开到哪一层

正文完整保留算术窗口推出RH的解析证明。本版进一步展开VVle非负部分和、HostExW量词、平方窗口缩到3/2、截断401到400、Closed/DesignExists先后、有限特征正交、4o辅助误差、E+7及同一宿主的统一阈值。新增算术章经过独立来源与数学复核，最终PDF编译和31页目视审查通过。

尚未全部转写的上游包括自守与Galois表示构造、模性长度窗口、宿主内部构造、几何链与逐单位比较，以及ch_core中的完整尺度和厚薄区域估计。不能因源码已完整保存就把这些纸面转写任务标成完成。

下一步优先从第三章“从投影到数值界仍需尺度控制”继续，展开DedekindLFunctions/LandauTheorems/ChCore.lean及所调用的移动、厚薄区域和平均估计；之后再追踪DesWin的九类几何条件。不要重复把已经证明的解析窗口判据当作新突破。

六、证明过程文件与内核导出

proof_process中的TXT和JSON是源码级数学说明与原文导出，不是Lean逐tactic状态日志或最小内核依赖闭包。公开内核导出solution.ndjson.zst约7.7GB，解压约61.6GB；本轮未下载或重新复核。准确URL、哈希和运行说明见tools/源码汇编与内核导出说明.txt。

七、校验与文件保留

  python3 verify_package.py

SHA256SUMS.txt覆盖本包实际交付文件。provenance保存原分卷预期哈希、固定镜像来源和本轮逐文件验证结果；evidence保存数学与排版审查。省略原gzip镜像副本、完整恢复副本、SQLite扫描缓存和页面PNG，均可由现行文件再生；保留旧中文重构稿作为本稿引用来源。
