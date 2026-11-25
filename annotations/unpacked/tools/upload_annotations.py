#!/usr/bin/env python3
"""Expand verified Release annotation volumes into ordinary Git files, one volume per commit."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import copy
import datetime
import fcntl
import threading
import uuid
from urllib.parse import quote, urlsplit
import getpass
import io
import ssl
import httpx
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import warnings

REPOSITORY = "liyiliuxingyu/riemann-lean-archive"
ORIGIN = "https://github.com/" + REPOSITORY + ".git"
API = "https://api.github.com/repos/" + REPOSITORY
PREFIX = "annotations/unpacked"
CHUNK_BYTES = 48 * 1024 * 1024
TOOL_VERSION = "2026-11-25.staging-v3-httpx-v3"
PACK_BUDGET = 700 * 1024 * 1024

UPLOAD_README = """# 完整注释的分块与并行上传

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
"""


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RuntimeError("Refusing an authenticated API redirect")


class ApiResponse(io.BytesIO):
    """Small already-read response with urllib's context/read/status interface."""
    def __init__(self, content, status, headers):
        super().__init__(content)
        self.status = status
        self.headers = headers


class PersistentApiOpener:
    """urllib-compatible API transport; its httpx.Client is shared across threads."""
    def __init__(self):
        target = urlsplit(API)
        self.origin = (target.scheme, target.hostname, target.port or 443)
        assert target.scheme == "https" and not target.username and not target.password
        context = ssl.create_default_context()
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        # Match urllib's HTTPS proxy and no_proxy route. Explicit selection avoids
        # loading an unrelated ALL_PROXY SOCKS route and its optional dependency.
        proxy_url = None if urllib.request.proxy_bypass(target.netloc) else urllib.request.getproxies().get("https")
        # The proxy may use plain HTTP CONNECT while the target remains HTTPS.
        # httpcore rejects a proxy SSL context for an HTTP (non-TLS) proxy.
        proxy_context = context if proxy_url and urlsplit(proxy_url).scheme == "https" else None
        proxy = httpx.Proxy(proxy_url, ssl_context=proxy_context) if proxy_url else None
        try:
            self.client = httpx.Client(
                verify=context, proxy=proxy, trust_env=False,
                follow_redirects=False, timeout=45.0,
                limits=httpx.Limits(max_connections=12, max_keepalive_connections=12, keepalive_expiry=120.0),
            )
        except Exception as error:
            raise RuntimeError("API transport initialization failed: " + type(error).__name__) from None

    def open(self, request, timeout=45):
        target = urlsplit(request.full_url)
        if (target.scheme, target.hostname, target.port or 443) != self.origin or target.username or target.password:
            raise RuntimeError("Refusing an API request outside the fixed HTTPS origin")
        try:
            response = self.client.request(
                request.get_method(), request.full_url,
                headers=dict(request.header_items()), content=request.data,
                timeout=timeout, follow_redirects=False,
            )
        except httpx.RequestError as error:
            # Keep existing retry and ambiguous-write handling, without logging
            # request headers, proxy URLs, or raw transport exception strings.
            raise urllib.error.URLError(type(error).__name__) from None
        try:
            content, status, headers = response.content, response.status_code, response.headers
        finally:
            response.close()
        if 300 <= status < 400:
            raise RuntimeError("Refusing an authenticated API redirect")
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "API request failed", headers, io.BytesIO(content))
        return ApiResponse(content, status, headers)

    def close(self):
        self.client.close()


def staging_push_retry_category(error):
    """Allow only recognizable transient transport or remote temporary-pack errors."""
    message = str(error).lower()
    permanent = ("authentication failed", "permission denied", "access denied", "repository not found",
                 "pre-receive hook declined", "protected branch", "large files detected",
                 "exceeds github's file size limit", "no space left on device", "disk quota exceeded",
                 "corrupt", "checksum mismatch", "non-fast-forward")
    if any(marker in message for marker in permanent):
        return None
    if ("index-pack failed" in message and "no such file or directory" in message
            and any(marker in message for marker in ("unable to write file", "unable to rename temporary pack"))):
        return "remote_temporary_pack_missing"
    transport = ("git command timed out", "connection reset by peer", "connection timed out",
                 "operation timed out", "connection was reset", "failed to connect", "connection refused",
                 "could not resolve host", "could not resolve proxy", "the remote end hung up unexpectedly",
                 "unexpected disconnect while reading sideband packet", "send failure: broken pipe",
                 "gnutls_recv error (-110)")
    if (any(marker in message for marker in transport)
            or re.search(r"\bcurl (?:16|18|28|52|55|56|92)\b", message)
            or re.search(r"(?:http(?:/\S+)?\s+|returned error:\s*)(?:408|429|500|502|503|504)\b", message)):
        return "transient_transport"
    return None


class ApiError(RuntimeError):
    def __init__(self, method, path, status, detail):
        self.status = status
        super().__init__(f"GitHub {method} {path}: {status} {detail}")


class Uploader:
    def __init__(self, args, token):
        if not __debug__:
            raise RuntimeError("Run this uploader without Python optimization; verification assertions must remain enabled")
        if not hasattr(os, "memfd_create"):
            raise RuntimeError("This bounded-disk uploader requires Linux memfd_create")
        self.args = args
        self.token = token
        self.root = args.work_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("batches", "reports", "logs", "staged"):
            (self.root / name).mkdir(exist_ok=True)
        self.catalog = json.loads(args.catalog.read_text())
        self.parts = self.catalog["parts"]
        assert len(self.parts) == 57
        assert sum(x["annotated_bytes"] for x in self.parts) == 168547118127
        assert sum(x["records"] for x in self.parts) == 1080769508
        previous = 0
        for i, part in enumerate(self.parts, 1):
            assert part["file"] == f"solution_annotated.part{i:03d}.txt.zst"
            assert part["download_url"] == (
                "https://github.com/" + REPOSITORY
                + "/releases/download/archive-20261122/" + part["file"]
            )
            assert part["first_line"] == previous + 1
            assert part["records"] == part["last_line"] - part["first_line"] + 1
            previous = part["last_line"]
        self.git_env = dict(os.environ)
        for key in list(self.git_env):
            if key.startswith("GIT_TRACE") or key == "GIT_CURL_VERBOSE":
                self.git_env.pop(key, None)
        self.git_env.update(GH_TOKEN=token, GH_HOST="github.com", GIT_TERMINAL_PROMPT="0")
        self.basic_env = dict(self.git_env)
        self.basic_env.pop("GH_TOKEN", None)
        self.basic_env.pop("GITHUB_TOKEN", None)
        self.api = PersistentApiOpener()
        self.started = time.monotonic()
        self.event_log = self.root / "events.jsonl"
        self.event_lock = threading.Lock()
        self.condition = threading.Condition()
        self.abort_event = threading.Event()
        self.abort_reason = None
        self.next_part = None
        self.last_published_head = None
        self.main_tree = None
        self.original_project_entry = None
        self.progress = None
        self.document_cache = {}
        self.tree_cache = {}
        run_file = self.root / "staging-run.json"
        if run_file.exists():
            state = json.loads(run_file.read_text())
            assert state["repository"] == REPOSITORY
            self.run_id = state["run_id"]
            assert re.fullmatch(r"[0-9a-f]{24}", self.run_id)
        else:
            self.run_id = uuid.uuid4().hex[:24]
            with run_file.open("x") as out:
                json.dump({"repository": REPOSITORY, "run_id": self.run_id}, out)
        self.tool_bytes = {name: (args.splitter.parent / name).read_bytes()
                           for name in ("split_annotations.cpp", "test_split_annotations.py", "test_results.json", "README.md")}
        self.tool_bytes["upload_annotations.py"] = Path(__file__).read_bytes()
        self.tool_version = {"version": TOOL_VERSION,
                             "uploader_sha256": hashlib.sha256(self.tool_bytes["upload_annotations.py"]).hexdigest(),
                             "splitter_source_sha256": hashlib.sha256(self.tool_bytes["split_annotations.cpp"]).hexdigest(),
                             "source_buffer": "Linux sealed memfd; at most 336997274 bytes per worker",
                             "pack_budget_per_worker_bytes": PACK_BUDGET,
                             "api_transport": "httpx persistent HTTP/1.1; system SSL context; urllib HTTPS proxy routing",
                             "dependencies": {"httpx": httpx.__version__}}
        self.tool_bytes["version.json"] = encoded(self.tool_version)
        self.tool_bytes["UPLOAD_README.md"] = UPLOAD_README.encode()
        self.tool_bytes["requirements.txt"] = b"httpx==0.28.1\n"

    def event(self, **item):
        item["elapsed_seconds"] = round(time.monotonic() - self.started, 2)
        line = json.dumps(item, ensure_ascii=False)
        with self.event_lock:
            with self.event_log.open("a") as out:
                out.write(line + "\n")
            print(line, flush=True)

    def api_json(self, method, path, data=None, missing_ok=False):
        payload = encoded(data) if data is not None else None
        attempts = 4 if method in ("GET", "POST") else 1
        for attempt in range(attempts):
            request = urllib.request.Request(API + path, data=payload, method=method, headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "RiemannAnnotationFileUpload",
            })
            delay = min(2 ** attempt, 15)
            try:
                with self.api.open(request, timeout=45) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {"status": response.status}
            except urllib.error.HTTPError as error:
                if error.code == 404 and missing_ok:
                    return None
                transient = error.code in (429, 500, 502, 503, 504)
                if not transient or attempt + 1 == attempts:
                    raise ApiError(method, path, error.code, "request failed") from None
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                if retry_after.isdigit():
                    delay = max(int(retry_after), 1)
                self.event(type="api_retry", method=method, path=path, status=error.code, attempt=attempt + 1)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt + 1 == attempts:
                    raise ApiError(method, path, None, type(error).__name__) from None
                self.event(type="api_retry", method=method, path=path, status=None, attempt=attempt + 1)
            time.sleep(delay)
        raise AssertionError("Unreachable API retry state")

    def get(self, path):
        return self.api_json("GET", path)

    def ensure_running(self):
        if self.abort_event.is_set():
            raise RuntimeError("Annotation pipeline aborted: " + str(self.abort_reason or "another worker failed"))

    def stop_all(self, error):
        with self.condition:
            if not self.abort_event.is_set():
                self.abort_reason = str(error)
                self.abort_event.set()
            self.condition.notify_all()

    def contents_at(self, path, commit, missing_ok=False):
        item = self.api_json("GET", "/contents/" + quote(path, safe="/") + "?ref=" + commit, missing_ok=missing_ok)
        if item is None:
            return None
        assert item["type"] == "file" and item["encoding"] == "base64"
        raw = base64.b64decode(item["content"])
        assert len(raw) == item["size"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == item["sha"]
        return raw

    def get_tree(self, sha):
        # Tree objects are immutable; concurrent workers may safely compute the same entry.
        if sha not in self.tree_cache:
            result = self.get("/git/trees/" + sha)
            assert result["sha"] == sha and not result.get("truncated")
            self.tree_cache[sha] = {entry["path"]: entry for entry in result["tree"]}
        return self.tree_cache[sha]

    def lookup_tree_entry(self, root_sha, path):
        pieces = path.split("/")
        tree_sha = root_sha
        for index, piece in enumerate(pieces):
            entry = self.get_tree(tree_sha).get(piece)
            if entry is None:
                return None
            if index + 1 == len(pieces):
                return entry
            if entry["type"] != "tree":
                return None
            tree_sha = entry["sha"]
        raise AssertionError("Empty tree path")

    def branch_for(self, number):
        return f"staging/annotations-{self.run_id}-part{number:03d}"

    def stage_receipt_path(self, number):
        return self.root / "staged" / f"part{number:03d}.json"

    def write_stage_receipt(self, stage):
        path = self.stage_receipt_path(stage["part"])
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encoded(stage))
        temp.replace(path)

    def verify_stage(self, stage):
        number = stage["part"]
        assert stage["repository"] == REPOSITORY and stage["run_id"] == self.run_id
        assert stage["branch"] == self.branch_for(number)
        assert stage["source"] == self.parts[number - 1]
        observed = self.api_json("GET", "/git/ref/heads/" + quote(stage["branch"], safe="/"), missing_ok=True)
        if observed is None:
            return False
        assert observed["object"]["sha"] == stage["commit"], "Own staging ref changed; preserve it and stop"
        commit = self.get("/git/commits/" + stage["commit"])
        assert commit["tree"]["sha"] == stage["tree"]
        assert commit.get("parents", []) == [], "Staging commit is not an orphan"
        expected = {Path(x["path"]).name: ("100644", "blob", x["git_blob_sha1"]) for x in stage["manifest"]["chunks"]}
        expected["manifest.json"] = ("100644", "blob", stage["manifest_blob_sha1"])
        actual = {p: (e["mode"], e["type"], e["sha"]) for p, e in self.get_tree(stage["tree"]).items()}
        assert actual == expected, "Staging tree differs from verified chunk manifest"
        raw = encoded(stage["manifest"])
        assert hashlib.sha256(raw).hexdigest() == stage["manifest_sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == stage["manifest_blob_sha1"]
        return True

    def download_memfd(self, number):
        self.ensure_running()
        part = self.parts[number - 1]
        for attempt in range(1, 4):
            fd = os.memfd_create(f"annotation-part{number:03d}", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            try:
                digest, size = hashlib.sha256(), 0
                cached = self.root / "downloads" / part["file"]
                request = urllib.request.Request(part["download_url"], headers={"User-Agent": "RiemannAnnotationFileUpload"})
                source = cached.open("rb") if cached.exists() else urllib.request.urlopen(request, timeout=60)
                with source, os.fdopen(os.dup(fd), "wb") as output:
                    for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                        self.ensure_running()
                        size += len(block)
                        if size > part["compressed_bytes"]:
                            raise RuntimeError("Compressed source exceeds pinned byte count")
                        output.write(block)
                        digest.update(block)
                assert size == part["compressed_bytes"] and digest.hexdigest() == part["compressed_sha256"], "Compressed source size or SHA-256 mismatch"
                os.lseek(fd, 0, os.SEEK_SET)
                # Linux UAPI constants from linux/fcntl.h; some Python builds omit their names.
                seals = 0x0001 | 0x0002 | 0x0004 | 0x0008
                fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), seals)
                assert fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034)) & seals == seals
                self.event(type="download_verified", part=number, bytes=size, source_buffer="sealed_memfd", cached=cached.exists())
                return fd, Path(f"/proc/self/fd/{fd}")
            except (OSError, urllib.error.URLError) as error:
                os.close(fd)
                if attempt == 3:
                    raise RuntimeError(f"Asset download failed for part {number}: {type(error).__name__}") from None
                time.sleep(attempt * 2)
            except BaseException:
                os.close(fd)
                raise
        raise AssertionError("Unreachable download state")

    def init_batch(self, number):
        self.ensure_running()
        directory = self.root / "batches" / f"part{number:03d}-{time.time_ns()}.git"
        self.git(None, "init", "--bare", "--initial-branch=" + self.branch_for(number), str(directory))
        self.git(directory, "remote", "add", "origin", ORIGIN)
        for key, value in (("gc.auto", "0"), ("fastimport.unpackLimit", "0"), ("core.compression", "1"), ("pack.window", "0")):
            self.git(directory, "config", key, value)
        return directory

    def disk_usage_bytes(self):
        total = 0
        for folder in (self.root,):
            for path in folder.rglob("*"):
                try:
                    if path.is_file():
                        total += path.stat().st_size
                except FileNotFoundError:
                    pass  # A different worker completed and removed its own batch.
        return total


    def git(self, directory, *arguments, input=None, allow_error=False):
        command = ["git"]
        if directory is not None:
            command += ["-C", str(directory)]
        command += ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
                    "-c", "http.lowSpeedLimit=1024", "-c", "http.lowSpeedTime=180"]
        command += list(arguments)
        try:
            result = subprocess.run(command, input=input, capture_output=True, env=self.git_env, timeout=1800)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Git command timed out; verify any attempted remote update before retrying") from None
        if result.returncode and not allow_error:
            error = result.stderr.decode("utf-8", "replace").replace(self.token, "[redacted]")
            raise RuntimeError("Git command failed: " + " ".join(arguments[:3]) + "\n" + error[-5000:])
        return result

    def read_blob(self, directory, path, required=True):
        value = self.document_cache.get(path)
        if required and value is None:
            raise RuntimeError("Missing cached metadata: " + path)
        return value

    def initial_progress(self):
        return {
            "schema": "ordinary-git-annotation-expansion-v1",
            "repository": REPOSITORY,
            "source_release_tag": "archive-20261122",
            "status": "in_progress",
            "chunk_max_bytes": CHUNK_BYTES,
            "boundary": "whole annotation plus original JSON record pairs; bytes preserved",
            "total_parts": 57,
            "total_annotated_bytes_expected": 168547118127,
            "total_original_records_expected": 1080769508,
            "completed_parts": [],
            "global_original_sha256_recomputed": False,
            "verification_scope": "Every complete source volume is SHA-256 checked before decompression; each original-volume hash, record count, byte count and line-label sequence is rechecked. Every output chunk is SHA-256 checked and its Git blob SHA-1 is compared with Git. No Lean proof checking.",
        }

    def make_readme(self, progress):
        completed = {x["part"]: x for x in progress["completed_parts"]}
        count = len(completed)
        total_bytes = sum(x["annotated_bytes"] for x in completed.values())
        total_chunks = sum(x["chunks"] for x in completed.values())
        state = "全部完成" if count == 57 else "正在逐卷上传，尚未全部完成"
        text = f"""# 完整注释的独立 TXT 文件\n\n状态：**{state}**。已完成 **{count}/57 卷**，**{total_chunks:,} 个 TXT 文件**，解压文本 **{total_bytes:,} 字节**。每个 TXT 不超过 48 MiB，保留完整的“注释＋原始 JSON 记录”两行配对；不增加标题、不改写换行、不重新编码正文。\n\n[机器可读进度](progress.json)记录实际完成的卷。每卷只有在压缩 SHA-256、解压结构、原文 SHA-256、字节数和记录数全部核验通过后，才随一个提交发布。全部原压缩附件仍保留在 [Release](https://github.com/{REPOSITORY}/releases/tag/archive-20261122)。\n\n## 按卷浏览\n\n| 卷 | 原始记录范围 | 状态 | 独立 TXT 数 |\n| --- | --- | --- | ---: |\n"""
        for number, part in enumerate(self.parts, 1):
            if number in completed:
                name = f"[第 {number} 卷](part{number:03d}/)"
                status = "已完整核验并上传"
                chunks = str(completed[number]["chunks"])
            else:
                name, status, chunks = f"第 {number} 卷", "待上传", "—"
            text += f"| {name} | {part['first_line']:,}–{part['last_line']:,} | {status} | {chunks} |\n"
        text += """\n## 下载、恢复与继续处理\n\n每卷目录中有 `manifest.json`，列出每个 TXT 的字节数、SHA-256、Git blob 标识、原始记录行号范围及注释文本字节区间。按 manifest 的块顺序直接连接即可恢复该卷的解压文本。网页不一定能预览较大 TXT，可以用单个文件的 Raw/Download 按钮或 Git 下载。\n\n这些是导出记录与中文字段注释，不是数学证明步骤编号，也不是可直接编译的 Lean 源文件。正式 Lean 源码位于 `project/lean/original/`，本次上传保持其 Git 子树不变。\n\n可复现工具位于 [tools/](tools/)。用 C++17、libzstd 与 OpenSSL 编译 `split_annotations.cpp`；`upload_annotations.py` 读取同仓库的 `annotations/release-parts.json`，按远端 `progress.json` 续传。认证仅从 `GH_TOKEN` 环境变量或隐藏终端输入读取，不写入仓库。\n\n全量原文的历史 SHA-256 为 `5ea74b912147c5c93cc2b6d70cc727cf908df2f62ac6a20480a3fa02f6be244e`。本次逐卷重算原文 SHA-256；没有把分卷哈希声称为新计算的全局哈希，也没有运行 Lean 内核验证。\n"""
        return text.encode()

    def updated_docs(self, directory, progress):
        count = len(progress["completed_parts"])
        status = "已全部展开为独立 TXT 文件" if count == 57 else f"正在按完整记录对分块上传，已完成 {count}/57 卷"
        root_readme = self.read_blob(directory, "README.md").decode()
        marker = "<!-- full-annotation-expansion-status -->"
        block = f"{marker}\n## 完整注释附件展开进度\n\n57 卷完整注释{status}。实际目录、逐卷核验结果和下载入口见 [annotations/unpacked/](annotations/unpacked/)。原始 Release 附件作为备份保留。\n<!-- /full-annotation-expansion-status -->\n\n"
        if marker in root_readme:
            root_readme = re.sub(r"<!-- full-annotation-expansion-status -->.*?<!-- /full-annotation-expansion-status -->\n*", lambda _: block, root_readme, count=1, flags=re.S)
        else:
            root_readme = root_readme.replace("## 交付内容与目录\n", block + "## 交付内容与目录\n", 1)
        root_readme = re.sub(r"\*\*57 卷注释的完整解压正文尚未加入普通 Git：.*?\*\*", "**完整注释的最新展开与上传状态见上方进度及 annotations/unpacked/。**", root_readme, count=1)
        root_readme = root_readme.replace("仍为 Release 压缩附件；[逐卷清单和解压说明](annotations/)", "[独立 TXT 与实时进度](annotations/unpacked/)；[原附件清单](annotations/)")
        root_readme = root_readme.replace("57 卷约 168.55 GB 的完整注释仍以 Release 附件保存。", "57 卷约 168.55 GB 的完整注释继续展开为独立 TXT，实际完成范围见上方进度；原 Release 附件保留。")
        annotation_readme = self.read_blob(directory, "annotations/README.md").decode()
        old_intro = "**完整数据仍仅作为 GitHub Release 的 `.txt.zst` 压缩附件保存；没有把解压后的 168,547,118,127 字节注释正文写入普通 Git 文件。**"
        new_intro = "**完整注释正在分卷展开为普通 TXT 文件，实际完成范围以 [unpacked/](unpacked/) 和其进度清单为准。原 Release 的压缩附件作为备份保留。**"
        annotation_readme = annotation_readme.replace(old_intro, new_intro)
        annotation_readme = annotation_readme.replace("本目录未实施这一全量展开方案，也不据上述计算断言任何仓库整体硬上限。", "当前全量展开工作使用 48 MiB 整记录对分块，实际数量及完成范围见 [unpacked/](unpacked/)；上述数字仅是旧的大小规划下限。")
        if count == 57:
            annotation_readme = annotation_readme.replace("完整注释正在分卷展开为普通 TXT 文件", "57 卷完整注释已全部展开为普通 TXT 文件")
        individual = self.read_blob(directory, "docs/INDIVIDUAL_FILES.md").decode()
        note = "> 后续更新：57 卷完整注释正在继续展开上传，实际完成范围见 [完整注释目录](../annotations/unpacked/)。本页记录此前 643 个小型归档展开文件的范围，其中保留大卷压缩附件的安排已由后续工作推进。\n\n"
        if "> 后续更新：57 卷完整注释" not in individual:
            individual = individual.replace("## 可直接阅读的内容\n", note + "## 可直接阅读的内容\n", 1)
        catalog = json.loads(self.read_blob(directory, "annotations/release-parts.json"))
        catalog["storage"].update({
            "decompressed_text_in_regular_git": True,
            "decompressed_text_complete": count == 57,
            "decompressed_parts_completed": count,
            "decompressed_text_directory": "annotations/unpacked/",
            "this_directory_contains": "Source inventory, documentation, and verified decompressed TXT volumes under unpacked/; consult unpacked/progress.json for actual completed scope.",
        })
        attrs = self.read_blob(directory, ".gitattributes").decode()
        if "annotations/unpacked/** -text -filter -ident" not in attrs:
            attrs += "\n# Preserve original bytes in full annotation text chunks.\nannotations/unpacked/** -text -filter -ident\n"
        return {
            "README.md": root_readme.encode(),
            "annotations/README.md": annotation_readme.encode(),
            "annotations/release-parts.json": encoded(catalog),
            "docs/INDIVIDUAL_FILES.md": individual.encode(),
            ".gitattributes": attrs.encode(),
        }


    def close_prepared(self, prepared):
        """Discard only task-created batch work; remote commits and logs are retained."""
        for name in ("splitter", "importer"):
            process = prepared.get(name)
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                for stream_name in ("stdin", "stdout"):
                    stream = getattr(process, stream_name, None)
                    if stream is not None and not stream.closed:
                        try:
                            stream.close()
                        except (BrokenPipeError, OSError):
                            pass
        fd = prepared.pop("memfd", None)
        if fd is not None:
            os.close(fd)
        for name in ("git_log", "split_log"):
            stream = prepared.get(name)
            if stream is not None and not stream.closed:
                stream.close()
        for name in ("directory", "chunks_dir"):
            path = prepared.get(name)
            if path is not None and path.exists():
                assert path.parent == self.root / "batches"
                shutil.rmtree(path)

    def prepare_part(self, number, directory=None):
        """Download, validate and import blobs, without creating any branch commit."""
        self.ensure_running()
        fd, source = self.download_memfd(number)
        part = self.parts[number - 1]
        prepared = {"number": number, "part": part, "source": source, "memfd": fd, "directory": directory}
        try:
            if directory is None:
                directory = self.init_batch(number)
                prepared["directory"] = directory
            chunks_dir = self.root / "batches" / f"chunks-{number:03d}-{time.time_ns()}"
            chunks_dir.mkdir()
            prepared["chunks_dir"] = chunks_dir
            git_log = (self.root / "logs" / f"part{number:03d}.git.log").open("wb")
            split_log = (self.root / "logs" / f"part{number:03d}.split.log").open("wb")
            prepared.update(git_log=git_log, split_log=split_log)
            importer = subprocess.Popen([
                "git", "-C", str(directory), "-c", "core.compression=1",
                "-c", "fastimport.unpackLimit=0", "fast-import", "--quiet", "--depth=0", "--max-pack-size=512", "--done",
            ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=git_log, env=self.git_env)
            prepared["importer"] = importer
            command = [str(self.args.splitter), "--source", str(source), "--out", str(chunks_dir),
                       "--first", str(part["first_line"]), "--last", str(part["last_line"]), "--max-bytes", str(CHUNK_BYTES)]
            if number == 57:
                command.append("--allow-final-no-lf")
            splitter = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=split_log, env=self.basic_env, pass_fds=(fd,))
            prepared["splitter"] = splitter
            files, marks = [], {}
            next_mark, offset, complete = 1, 0, None

            def add_blob(path, raw):
                nonlocal next_mark
                self.ensure_running()
                assert not path.startswith("/") and ".." not in path.split("/") and "\n" not in path
                mark = next_mark
                next_mark += 1
                expected = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                importer.stdin.write(f"blob\nmark :{mark}\ndata {len(raw)}\n".encode())
                importer.stdin.write(raw)
                importer.stdin.write(f"\nget-mark :{mark}\n".encode())
                importer.stdin.flush()
                observed = importer.stdout.readline().decode().strip()
                if observed != expected:
                    raise RuntimeError(f"Git imported blob differs from original bytes: {path}")
                marks[path] = mark
                return observed

            self.event(type="volume_started", part=number, original_records=part["records"], annotated_bytes=part["annotated_bytes"])
            for line in splitter.stdout:
                self.ensure_running()
                event = json.loads(line)
                if event["type"] == "complete":
                    if complete is not None:
                        raise RuntimeError("Duplicate complete event")
                    complete = event
                    continue
                assert event["type"] == "chunk" and complete is None
                assert re.fullmatch(r"chunk[0-9]{4,}\.txt", event["file"])
                path = chunks_dir / event["file"]
                raw = path.read_bytes()
                assert len(raw) == event["bytes"] <= CHUNK_BYTES
                assert hashlib.sha256(raw).hexdigest() == event["sha256"]
                expected_first = part["first_line"] if not files else files[-1]["last_line"] + 1
                assert event["first_line"] == expected_first
                assert event["records"] == event["last_line"] - event["first_line"] + 1
                destination = f"{PREFIX}/part{number:03d}/{event['file']}"
                assert destination not in marks, "Duplicate chunk path"
                blob = add_blob(destination, raw)
                files.append({"path": destination, "bytes": len(raw), "sha256": event["sha256"],
                              "git_blob_sha1": blob, "first_line": event["first_line"],
                              "last_line": event["last_line"], "records": event["records"],
                              "annotated_start_byte": offset, "annotated_end_byte_exclusive": offset + len(raw)})
                offset += len(raw)
                del raw
                path.unlink()
                pack_bytes = sum(x.stat().st_size for x in (directory / "objects" / "pack").iterdir() if x.is_file())
                if pack_bytes > PACK_BUDGET:
                    raise RuntimeError("Prepared volume exceeds the three-worker pack budget; nothing from this volume was published")
                self.ensure_running()
                splitter.stdin.write(b"ok\n")
                splitter.stdin.flush()
                if len(files) % 10 == 0:
                    self.event(type="chunks_imported", part=number, chunks=len(files), annotated_bytes=offset)
            splitter.stdin.close()
            if splitter.wait() != 0 or complete is None:
                raise RuntimeError(f"Splitter failed for part {number}; see the local split log")
            for key in ("first_line", "last_line", "records", "annotated_bytes", "original_bytes", "original_sha256"):
                assert complete[key] == part[key], f"Volume {number} mismatch: {key}"
            assert complete["compressed_bytes_read"] == part["compressed_bytes"]
            assert complete["chunks"] == len(files)
            assert offset == part["annotated_bytes"]
            assert files[-1]["last_line"] == part["last_line"]
            assert sum(x["records"] for x in files) == part["records"]
            prepared.update(files=files, marks=marks, add_blob=add_blob, complete=complete, offset=offset)
            # The verified compressed source is reproducible from its pinned Release URL.
            # Removing it now bounds two simultaneous prepared volumes before either push.
            os.close(prepared.pop("memfd"))
            self.event(type="volume_prepared", part=number, chunks=len(files), annotated_bytes=offset,
                       git_object_bytes=sum(x.stat().st_size for x in (directory / "objects" / "pack").iterdir() if x.is_file()),
                       observed_task_disk_bytes=self.disk_usage_bytes())
            return prepared
        except BaseException:
            self.close_prepared(prepared)
            raise


    def push_stage_commit(self, directory, head, branch, number):
        """Retry the same verified commit only after confirming its ref is absent."""
        assert branch == self.branch_for(number)
        ref_path = "/git/ref/heads/" + quote(branch, safe="/")
        for attempt in range(3):
            self.ensure_running()
            if attempt:
                # A previous push may become visible while backing off. Never
                # overwrite a ref, and do not retransmit a confirmed success.
                ref = self.api_json("GET", ref_path, missing_ok=True)
                if ref is not None:
                    assert ref["object"]["sha"] == head, "Staging ref changed before retry; preserve it and stop"
                    return
            try:
                self.git(directory, "push", "origin", head + ":refs/heads/" + branch)
                return
            except RuntimeError as error:
                # Check ambiguity even for an otherwise non-retryable failure.
                # A failed readback is not evidence of absence and propagates.
                ref = self.api_json("GET", ref_path, missing_ok=True)
                if ref is not None:
                    assert ref["object"]["sha"] == head, "Staging ref changed after push; preserve it and stop"
                    return
                category = staging_push_retry_category(error)
                if category is None or attempt == 2:
                    raise
                delay = (5, 15)[attempt]
                self.event(type="staging_push_retry", part=number, failed_attempt=attempt + 1,
                           next_attempt=attempt + 2, delay_seconds=delay, category=category)
                self.ensure_running()
                self.abort_event.wait(delay)
                self.ensure_running()
        raise AssertionError("Unreachable staging push retry state")


    def stage_part(self, number):
        """Upload one verified orphan volume tree, without changing main."""
        self.ensure_running()
        receipt_path = self.stage_receipt_path(number)
        if receipt_path.exists():
            previous = json.loads(receipt_path.read_text())
            if self.verify_stage(previous):
                previous["status"] = "staged"
                self.write_stage_receipt(previous)
                self.event(type="volume_staged_reused", part=number, commit=previous["commit"])
                return previous
        existing = self.api_json("GET", "/git/ref/heads/" + quote(self.branch_for(number), safe="/"), missing_ok=True)
        assert existing is None, "A staging ref exists without a matching verified receipt; preserve it and stop"
        prepared = None
        try:
            prepared = self.prepare_part(number)
            part, complete = prepared["part"], prepared["complete"]
            files, directory = prepared["files"], prepared["directory"]
            importer, marks, add_blob = prepared["importer"], prepared["marks"], prepared["add_blob"]
            manifest = {"schema": "annotation-volume-chunks-v1", "status": "complete", "part": number,
                        "source": part, "actual": complete, "chunk_max_bytes": CHUNK_BYTES,
                        "chunks": files, "tool_version": self.tool_version,
                        "byte_preservation": "Concatenate chunks in this listed order to recover exact decompressed bytes."}
            manifest_raw = encoded(manifest)
            manifest_blob = add_blob(f"{PREFIX}/part{number:03d}/manifest.json", manifest_raw)
            branch = self.branch_for(number)
            message = f"Stage verified annotation volume {number:03d}; main integration follows validation".encode()
            importer.stdin.write((f"commit refs/heads/{branch}\ncommitter ChatGPT <noreply@openai.com> {int(time.time())} +0000\ndata {len(message)}\n").encode())
            importer.stdin.write(message + b"\n")
            prefix = f"{PREFIX}/part{number:03d}/"
            for path, mark in marks.items():
                assert path.startswith(prefix)
                relative = path[len(prefix):]
                assert "/" not in relative and relative
                importer.stdin.write(f"M 100644 :{mark} {relative}\n".encode())
            importer.stdin.write(b"\ndone\n")
            importer.stdin.close()
            if importer.wait() != 0:
                raise RuntimeError("Staging fast-import failed; see local Git log")
            head = self.git(directory, "rev-parse", "HEAD").stdout.decode().strip()
            tree = self.git(directory, "rev-parse", "HEAD^{tree}").stdout.decode().strip()
            assert len(self.git(directory, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) == 1
            expected = {Path(x["path"]).name: ("100644", "blob", x["git_blob_sha1"]) for x in files}
            expected["manifest.json"] = ("100644", "blob", manifest_blob)
            actual = {}
            for entry in self.git(directory, "ls-tree", "-z", "HEAD").stdout.split(b"\0"):
                if entry:
                    props, path = entry.split(b"\t", 1)
                    actual[path.decode()] = tuple(props.decode().split())
            assert actual == expected, "Local orphan tree differs from verified files"
            stage = {"schema": "verified-annotation-stage-v1", "repository": REPOSITORY,
                     "run_id": self.run_id, "status": "prepared", "part": number, "source": part,
                     "branch": branch, "commit": head, "tree": tree, "manifest": manifest,
                     "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(), "manifest_blob_sha1": manifest_blob,
                     "tool_version": self.tool_version}
            # Persist the exact candidate before push, making an ambiguous push response recoverable.
            self.write_stage_receipt(stage)
            self.ensure_running()
            observed = self.api_json("GET", "/git/ref/heads/" + quote(branch, safe="/"), missing_ok=True)
            assert observed is None, "Staging ref appeared concurrently; do not overwrite it"
            self.event(type="volume_staging_push", part=number, commit=head,
                       observed_task_disk_bytes=self.disk_usage_bytes())
            self.push_stage_commit(directory, head, branch, number)
            assert self.verify_stage(stage), "Staging branch is missing after push"
            stage["status"] = "staged"
            self.write_stage_receipt(stage)
            self.event(type="volume_staged", part=number, chunks=len(files), commit=head, tree=tree,
                       annotated_bytes=part["annotated_bytes"], observed_task_disk_bytes=self.disk_usage_bytes())
            return stage
        finally:
            if prepared is not None:
                self.close_prepared(prepared)

    def remove_own_stage_ref(self, stage):
        """Lease-delete only our exact staging SHA after its tree is verified in main."""
        assert stage["branch"] == self.branch_for(stage["part"]) and stage["run_id"] == self.run_id
        get_path = "/git/ref/heads/" + quote(stage["branch"], safe="/")
        ref = self.api_json("GET", get_path, missing_ok=True)
        if ref is None:
            return True
        if ref["object"]["sha"] != stage["commit"]:
            self.event(type="staging_cleanup_preserved_changed_ref", part=stage["part"], branch=stage["branch"])
            return False
        control = self.root / "batches" / ("cleanup-" + uuid.uuid4().hex + ".git")
        try:
            self.git(None, "init", "--bare", str(control))
            self.git(control, "remote", "add", "origin", ORIGIN)
            target = "refs/heads/" + stage["branch"]
            try:
                # This is a guarded deletion of a task-created temporary ref, never a main update.
                self.git(control, "push", "--force-with-lease=" + target + ":" + stage["commit"],
                         "origin", ":" + target)
            except RuntimeError:
                # A lease failure preserves a changed ref; a disconnected successful deletion
                # is accepted only after the ref is observed to be absent.
                observed = self.api_json("GET", get_path, missing_ok=True)
                if observed is None:
                    return True
                self.event(type="staging_cleanup_pending", part=stage["part"], branch=stage["branch"],
                           reason="lease deletion failed or ref changed")
                return False
            return self.api_json("GET", get_path, missing_ok=True) is None
        finally:
            if control.exists():
                shutil.rmtree(control)

    def publish_staged(self, stage, progress):
        self.ensure_running()
        number, part = stage["part"], stage["source"]
        expected_parent = self.last_published_head
        assert self.get("/git/ref/heads/main")["object"]["sha"] == expected_parent, "Remote main changed outside this task; do not merge or overwrite it"
        assert self.verify_stage(stage), "Verified staging ref disappeared before integration"
        assert self.lookup_tree_entry(self.main_tree, f"{PREFIX}/part{number:03d}") is None, "Target volume directory already exists outside completed progress"
        next_progress = copy.deepcopy(progress)
        actual = stage["manifest"]["actual"]
        record = {"part": number, "source_file": part["file"], "source_compressed_sha256": part["compressed_sha256"],
                  "first_line": part["first_line"], "last_line": part["last_line"], "records": part["records"],
                  "annotated_bytes": part["annotated_bytes"], "annotated_sha256": actual["annotated_sha256"],
                  "original_bytes": part["original_bytes"], "original_sha256": part["original_sha256"],
                  "chunks": len(stage["manifest"]["chunks"]), "manifest": f"{PREFIX}/part{number:03d}/manifest.json",
                  "manifest_sha256": stage["manifest_sha256"], "subtree_sha": stage["tree"],
                  "tool_version": stage["tool_version"]["version"]}
        next_progress["completed_parts"].append(record)
        count = len(next_progress["completed_parts"])
        assert [x["part"] for x in next_progress["completed_parts"]] == list(range(1, count + 1))
        next_progress["status"] = "complete" if count == 57 else "in_progress"
        next_progress["completed_annotated_bytes"] = sum(x["annotated_bytes"] for x in next_progress["completed_parts"])
        next_progress["completed_original_records"] = sum(x["records"] for x in next_progress["completed_parts"])
        next_progress["completed_chunks"] = sum(x["chunks"] for x in next_progress["completed_parts"])
        next_progress["current_tool_version"] = self.tool_version
        if count == 57:
            assert next_progress["completed_annotated_bytes"] == 168547118127
            assert next_progress["completed_original_records"] == 1080769508
        documents = self.updated_docs(None, next_progress)
        documents[f"{PREFIX}/progress.json"] = encoded(next_progress)
        documents[f"{PREFIX}/README.md"] = self.make_readme(next_progress)
        for name, raw in self.tool_bytes.items():
            documents[f"{PREFIX}/tools/{name}"] = raw
        entries = [{"path": path, "mode": "100644", "type": "blob", "content": raw.decode("utf-8")}
                   for path, raw in documents.items()]
        entries.append({"path": f"{PREFIX}/part{number:03d}", "mode": "040000", "type": "tree", "sha": stage["tree"]})
        created = self.api_json("POST", "/git/trees", {"base_tree": self.main_tree, "tree": entries})
        new_tree = created["sha"]
        root_entries = self.get_tree(new_tree)
        project = root_entries["project"]
        assert (project["mode"], project["type"], project["sha"]) == self.original_project_entry, "Formal project tree changed unexpectedly"
        installed = self.lookup_tree_entry(new_tree, f"{PREFIX}/part{number:03d}")
        assert installed["mode"] == "040000" and installed["type"] == "tree" and installed["sha"] == stage["tree"]
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        person = {"name": "ChatGPT", "email": "noreply@openai.com", "date": stamp}
        commit = self.api_json("POST", "/git/commits", {
            "message": f"Expand verified full annotation volume {number:03d} into {record['chunks']} TXT files",
            "tree": new_tree, "parents": [expected_parent], "author": person, "committer": person})
        new_head = commit["sha"]
        assert commit["tree"]["sha"] == new_tree
        assert [p["sha"] for p in commit["parents"]] == [expected_parent]
        self.ensure_running()
        assert self.get("/git/ref/heads/main")["object"]["sha"] == expected_parent, "Remote main changed before non-force update"
        self.ensure_running()
        try:
            self.api_json("PATCH", "/git/refs/heads/main", {"sha": new_head, "force": False})
        except ApiError:
            # PATCH may have applied before a transient transport/server failure.
            # Accept only a readback equal to this exact candidate; otherwise stop.
            if self.get("/git/ref/heads/main")["object"]["sha"] != new_head:
                raise
        assert self.get("/git/ref/heads/main")["object"]["sha"] == new_head, "Published main differs from prepared commit"
        remote_commit = self.get("/git/commits/" + new_head)
        assert remote_commit["tree"]["sha"] == new_tree
        receipt = {"part": number, "commit": new_head, "tree": new_tree, "parent": expected_parent,
                   "remote_verified": True, "chunks": record["chunks"], "annotated_bytes": part["annotated_bytes"],
                   "records": part["records"], "volume_subtree": stage["tree"], "tool_version": self.tool_version,
                   "progress": next_progress}
        (self.root / "reports" / f"part{number:03d}.json").write_bytes(encoded(receipt))
        self.document_cache.update(documents)
        stage["status"] = "integrated"
        stage["main_commit"] = new_head
        self.write_stage_receipt(stage)
        cleanup_ok = False
        try:
            cleanup_ok = self.remove_own_stage_ref(stage)
        except ApiError as error:
            self.event(type="staging_cleanup_pending", part=number, error=str(error))
        stage["staging_ref_deleted"] = cleanup_ok
        self.write_stage_receipt(stage)
        self.event(type="volume_uploaded", part=number, chunks=record["chunks"], commit=new_head,
                   completed_parts=count, completed_bytes=next_progress["completed_annotated_bytes"], staging_ref_deleted=cleanup_ok)
        return next_progress, new_head, new_tree

    def publish_in_order(self, stage):
        number = stage["part"]
        with self.condition:
            while number != self.next_part and not self.abort_event.is_set():
                self.condition.wait(timeout=1)
            self.ensure_running()
            snapshot = copy.deepcopy(self.progress)
        next_progress, head, tree = self.publish_staged(stage, snapshot)
        with self.condition:
            self.progress, self.last_published_head, self.main_tree = next_progress, head, tree
            self.next_part += 1
            self.condition.notify_all()
        return head

    def run_pipeline(self, first, last, progress):
        assert 1 <= first <= last <= 57 and len(progress["completed_parts"]) == first - 1
        self.ensure_running()
        with self.condition:
            self.next_part = first
            self.progress = copy.deepcopy(progress)
        def worker(number):
            try:
                stage = self.stage_part(number)
                self.ensure_running()
                return self.publish_in_order(stage)
            except BaseException as error:
                self.stop_all(error)
                raise
        executor = ThreadPoolExecutor(max_workers=getattr(self.args, "workers", 3))
        futures = [executor.submit(worker, n) for n in range(first, last + 1)]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException as error:
            self.stop_all(error)
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        return self.progress

    def initialize_remote(self):
        repository = self.get("")
        assert repository["full_name"] == REPOSITORY and repository["id"] == 1467518482
        assert repository["owner"]["id"] == 21255612 and repository["permissions"]["push"]
        head = self.get("/git/ref/heads/main")["object"]["sha"]
        commit = self.get("/git/commits/" + head)
        self.main_tree = commit["tree"]["sha"]
        project = self.get_tree(self.main_tree)["project"]
        self.original_project_entry = (project["mode"], project["type"], project["sha"])
        paths = ["README.md", "annotations/README.md", "annotations/release-parts.json",
                 "docs/INDIVIDUAL_FILES.md", ".gitattributes", f"{PREFIX}/progress.json"]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = {path: pool.submit(self.contents_at, path, head, path.endswith("progress.json")) for path in paths}
            self.document_cache = {path: task.result() for path, task in results.items()}
        progress_raw = self.document_cache.get(f"{PREFIX}/progress.json")
        progress = json.loads(progress_raw) if progress_raw is not None else self.initial_progress()
        assert progress["schema"] == "ordinary-git-annotation-expansion-v1"
        completed = len(progress["completed_parts"])
        assert 0 <= completed <= 57
        assert [x["part"] for x in progress["completed_parts"]] == list(range(1, completed + 1))
        if completed:
            with ThreadPoolExecutor(max_workers=6) as pool:
                manifests = [pool.submit(self.contents_at, item["manifest"], head) for item in progress["completed_parts"]]
                for item, expected, task in zip(progress["completed_parts"], self.parts, manifests):
                    raw = task.result()
                    assert hashlib.sha256(raw).hexdigest() == item["manifest_sha256"]
                    manifest = json.loads(raw)
                    assert manifest["status"] == "complete" and manifest["part"] == item["part"]
                    assert manifest["source"] == expected
                    assert item["source_compressed_sha256"] == expected["compressed_sha256"]
                    assert item["annotated_bytes"] == expected["annotated_bytes"]
                    assert manifest["actual"]["original_sha256"] == expected["original_sha256"]
                    assert manifest["actual"]["records"] == expected["records"]
                    assert len(manifest["chunks"]) == item["chunks"]
                    assert sum(x["bytes"] for x in manifest["chunks"]) == expected["annotated_bytes"]
                    entry = self.lookup_tree_entry(self.main_tree, f"{PREFIX}/part{item['part']:03d}")
                    assert entry and entry["mode"] == "040000" and entry["type"] == "tree"
                    tree = self.get_tree(entry["sha"])
                    for chunk in manifest["chunks"]:
                        value = tree[Path(chunk["path"]).name]
                        assert (value["mode"], value["type"], value["sha"]) == ("100644", "blob", chunk["git_blob_sha1"])
        assert self.get("/git/ref/heads/main")["object"]["sha"] == head, "Remote main changed during initialization"
        self.last_published_head = head
        self.progress = progress
        self.event(type="resume_state", completed_parts=completed, total_parts=57, head=head, workers=getattr(self.args, "workers", 3))
        return progress

    def retry_integrated_cleanup(self):
        completed = {item["part"]: item for item in self.progress["completed_parts"]}
        for path in sorted((self.root / "staged").glob("part*.json")):
            stage = json.loads(path.read_text())
            item = completed.get(stage["part"])
            if item is None:
                continue  # A staged but not yet integrated volume is still a needed recovery point.
            assert stage["repository"] == REPOSITORY and stage["run_id"] == self.run_id
            assert stage["branch"] == self.branch_for(stage["part"])
            assert stage["source"] == self.parts[stage["part"] - 1]
            assert item["manifest_sha256"] == stage["manifest_sha256"]
            installed = self.lookup_tree_entry(self.main_tree, f"{PREFIX}/part{stage['part']:03d}")
            assert installed and installed["mode"] == "040000" and installed["type"] == "tree" and installed["sha"] == stage["tree"]
            # Recover the case where PATCH succeeded but all immediate verification reads failed.
            stage["status"] = "integrated"
            stage["main_verified_at"] = self.last_published_head
            self.write_stage_receipt(stage)
            if not stage.get("staging_ref_deleted"):
                try:
                    stage["staging_ref_deleted"] = self.remove_own_stage_ref(stage)
                    self.write_stage_receipt(stage)
                except ApiError as error:
                    self.event(type="staging_cleanup_pending", part=stage["part"], error=str(error))

    def run(self):
        progress = self.initialize_remote()
        self.retry_integrated_cleanup()
        completed = len(progress["completed_parts"])
        last = min(57, getattr(self.args, "stop_after_part", None) or 57)
        if completed < last:
            self.run_pipeline(completed + 1, last, progress)
        self.retry_integrated_cleanup()
        self.event(type="all_complete" if len(self.progress["completed_parts"]) == 57 else "requested_stop_reached",
                   completed_parts=len(self.progress["completed_parts"]),
                   chunks=self.progress.get("completed_chunks", 0),
                   annotated_bytes=self.progress.get("completed_annotated_bytes", 0),
                   original_records=self.progress.get("completed_original_records", 0),
                   observed_task_disk_bytes=self.disk_usage_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--splitter", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--stop-after-part", type=int, choices=range(1, 58))
    args = parser.parse_args()
    warnings.simplefilter("error", getpass.GetPassWarning)
    token = os.environ.get("GH_TOKEN") or getpass.getpass("GitHub token (input hidden): ").strip()
    if not token:
        raise RuntimeError("Authentication is required for the authorized repository upload")
    uploader = Uploader(args, token)
    try:
        uploader.run()
    finally:
        uploader.token = ""
        uploader.git_env.pop("GH_TOKEN", None)
        token = ""
        uploader.api.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"type": "stopped", "error": str(error)}, ensure_ascii=False), file=sys.stderr, flush=True)
        sys.exit(1)

