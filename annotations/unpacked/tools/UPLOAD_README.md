# 完整注释的分块与并行上传

该工具使用 Linux 的 memfd、Git fast-import 与 GitHub GitData API，把经过核验的 Release 卷拆成普通 TXT 文件。需要正常模式的 Python 3（禁止 -O）、Git、gh、C++17 编译器、libzstd、OpenSSL 和 httpx==0.28.1（可用 python3 -m pip install httpx==0.28.1 安装）。

编译分块器：

```bash
g++ -O3 -DNDEBUG -std=c++17 split_annotations.cpp -lzstd -lcrypto -o split_annotations
```

从仓库根目录启动上传器（工作目录用于断点和本地临时对象）：

```bash
python3 annotations/unpacked/tools/upload_annotations.py --catalog annotations/release-parts.json --splitter /path/to/split_annotations --work-dir /path/to/upload-work --workers 3
```

认证由 GH_TOKEN 环境变量或隐藏终端输入提供，不要把令牌写入命令行或文件。分块器子进程不接收认证环境变量。

每卷压缩源先核验大小和 SHA-256，再封存到 Linux memfd；memfd 只读封印被实际读回检查。每 worker 的压缩源最多约337 MB内存，另外有分块与散列缓冲。磁盘不保存全部解压文本。每个 worker 的本卷 Git pack 预算为700 MiB，检查粒度是一个48 MiB块；超过预算时该卷停止并保留既有远端进度。三 worker 的工作文件规模目标约2.5 GB，事件日志报告实际工作目录文件字节数，既有缓存和失败遗留数据也必须计入；不能以 statvfs 的零占用值保证真实峰值。

每个 Git 数据批次只含一卷的独立 TXT 和清单，先推送到本运行创建的唯一临时分支。主分支按卷序通过 GitData 子树挂接更新；整个 project 子树保持不变。主分支始终使用非强制更新，并在更新前后核对提交。普通并发新提交会导致停止；REST 非强制更新不是针对所有强制回退竞态的严格CAS承诺。

只有 main 的实际卷子树核验通过后，才用带精确预期 SHA 的 Git lease 删除本运行的临时分支；lease 失败时保留分支。staged/ 内的接续记录在推送前保存，断线后可读回核对，避免盲目重传。main 更新成功但随后的读取失败，也可在重启时通过主分支进度和子树核验恢复完成状态。

GET 与可重复的Git对象创建请求对429/5xx作有限重试，并尊重Retry-After秒数。主分支更新或分支删除结果不明时先读回状态。Git传输设置低速超时和单命令30分钟超时。临时分支推送失败后先读回精确提交；已成功则直接继续，出现其他提交则停止。只有确认分支不存在且错误属于可识别的暂时传输故障或远端临时 pack 文件缺失，才保留同一已核验本地 pack，在5秒、15秒退避后最多重试两次；每次重试前再次核对分支，期间可被其他 worker 的失败唤醒停止。

GitHub API 使用可跨线程共享的 httpx.Client 和最多12条持久连接；系统 ssl.create_default_context() 保持证书与主机名核验，代理和 no_proxy 选择与 urllib 的 HTTPS 路由相同，不启用无关的 ALL_PROXY SOCKS 路由。认证请求固定在 API 主机，不跟随重定向。Release 下载和 Git 上传传输保持原逻辑。

--workers 可以为1、2或3；--stop-after-part N 会在完整处理到第N卷后停止。再次用同一工作目录运行即可按远端已核验清单与本地暂存收据续作。完整源记录对不会拆开，正文不改写换行、不增加标题、不重新编码。

本工具核验文件与上传过程，不执行Lean内核检查，也不把分卷哈希误称为新算出的全局原文哈希。
