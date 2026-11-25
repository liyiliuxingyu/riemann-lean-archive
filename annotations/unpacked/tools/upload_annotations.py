#!/usr/bin/env python3
"""Expand verified Release annotation volumes into ordinary Git files, one volume per commit."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import getpass
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


class Uploader:
    def __init__(self, args, token):
        self.args = args
        self.token = token
        self.root = args.work_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("downloads", "batches", "reports", "logs"):
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
        self.api = urllib.request.build_opener(NoRedirect())
        self.started = time.monotonic()
        self.event_log = self.root / "events.jsonl"
        self.document_cache = {}
        self.document_cache_head = None

    def event(self, **item):
        item["elapsed_seconds"] = round(time.monotonic() - self.started, 2)
        line = json.dumps(item, ensure_ascii=False)
        with self.event_log.open("a") as out:
            out.write(line + "\n")
        print(line, flush=True)

    def get(self, path):
        request = urllib.request.Request(API + path, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RiemannAnnotationFileUpload",
        })
        for attempt in range(1, 6):
            try:
                with self.api.open(request, timeout=45) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 5:
                    raise RuntimeError(f"Authenticated GitHub API returned HTTP {error.code}") from None
                delay = max(2 ** attempt, int(error.headers.get("Retry-After", "0")))
                self.event(type="api_read_retry", status=error.code, attempt=attempt, retry_seconds=delay)
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 5:
                    raise RuntimeError("Authenticated GitHub API read failed after retries") from None
                self.event(type="api_read_retry", status="network", attempt=attempt)
                time.sleep(2 ** attempt)
        raise AssertionError("Unreachable API retry state")

    def git(self, directory, *arguments, input=None, allow_error=False):
        command = ["git"]
        if directory is not None:
            command += ["-C", str(directory)]
        command += ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
        command += list(arguments)
        result = subprocess.run(command, input=input, capture_output=True, env=self.git_env)
        if result.returncode and not allow_error:
            error = result.stderr.decode("utf-8", "replace").replace(self.token, "[redacted]")
            raise RuntimeError("Git command failed: " + " ".join(arguments[:3]) + "\n" + error[-5000:])
        return result

    def download(self, number):
        part = self.parts[number - 1]
        destination = self.root / "downloads" / part["file"]
        if destination.exists():
            if destination.stat().st_size == part["compressed_bytes"] and sha256_file(destination) == part["compressed_sha256"]:
                self.event(type="download_verified", part=number, bytes=part["compressed_bytes"], cached=True)
                return destination
            raise RuntimeError(f"Existing download has a checksum mismatch: part {number}")
        temporary = destination.with_name(destination.name + ".partial")
        for attempt in range(1, 4):
            digest = hashlib.sha256()
            size = 0
            try:
                request = urllib.request.Request(part["download_url"], headers={"User-Agent": "RiemannAnnotationFileUpload"})
                # No authentication header is sent to the public asset or its redirect target.
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
                    for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
                        out.write(block)
                        digest.update(block)
                        size += len(block)
                if size != part["compressed_bytes"] or digest.hexdigest() != part["compressed_sha256"]:
                    raise RuntimeError(f"Compressed source size or SHA-256 mismatch: part {number}")
                temporary.replace(destination)
                self.event(type="download_verified", part=number, bytes=size, cached=False)
                return destination
            except (OSError, urllib.error.URLError) as error:
                if attempt == 3:
                    raise RuntimeError(f"Asset download failed for part {number}: {type(error).__name__}") from None
                time.sleep(3 * attempt)
        raise AssertionError("Unreachable download state")

    def clone_batch(self, number):
        directory = self.root / "batches" / f"part{number:03d}-{time.time_ns()}.git"
        self.git(None, "clone", "--bare", "--filter=blob:none", "--depth=1", "--single-branch", "--branch=main", ORIGIN, str(directory))
        for key, value in (("gc.auto", "0"), ("fastimport.unpackLimit", "0"), ("core.compression", "1"), ("pack.window", "0")):
            self.git(directory, "config", key, value)
        return directory

    def read_blob(self, directory, path, required=True):
        cacheable = path in {"README.md", "annotations/README.md", "annotations/release-parts.json",
                             "docs/INDIVIDUAL_FILES.md", ".gitattributes", PREFIX + "/progress.json"}
        head = self.git(directory, "rev-parse", "HEAD").stdout.decode().strip() if cacheable else None
        if cacheable and head == self.document_cache_head and path in self.document_cache:
            return self.document_cache[path]
        result = self.git(directory, "show", "HEAD:" + path, allow_error=not required)
        raw = result.stdout if result.returncode == 0 else None
        if cacheable and raw is not None:
            if head != self.document_cache_head:
                self.document_cache = {}
                self.document_cache_head = head
            self.document_cache[path] = raw
        return raw

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

    def publish_part(self, number, source, directory, progress):
        part = self.parts[number - 1]
        parent = self.git(directory, "rev-parse", "HEAD").stdout.decode().strip()
        original_tree = self.git(directory, "rev-parse", "HEAD:project/lean/original").stdout.strip()
        chunks_dir = self.root / "batches" / f"chunks-{number:03d}-{time.time_ns()}"
        chunks_dir.mkdir()
        git_log = (self.root / "logs" / f"part{number:03d}.git.log").open("wb")
        split_log = (self.root / "logs" / f"part{number:03d}.split.log").open("wb")
        importer = subprocess.Popen([
            "git", "-C", str(directory), "-c", "core.compression=1",
            "-c", "fastimport.unpackLimit=0", "fast-import", "--quiet", "--depth=0", "--max-pack-size=512", "--done",
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=git_log, env=self.git_env)
        command = [str(self.args.splitter), "--source", str(source), "--out", str(chunks_dir),
                   "--first", str(part["first_line"]), "--last", str(part["last_line"]), "--max-bytes", str(CHUNK_BYTES)]
        if number == 57:
            command.append("--allow-final-no-lf")
        splitter = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=split_log, env=self.basic_env)
        files = []
        marks = {}
        next_mark = 1
        offset = 0
        complete = None

        def add_blob(path, raw):
            nonlocal next_mark
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

        try:
            self.event(type="volume_started", part=number, original_records=part["records"], annotated_bytes=part["annotated_bytes"])
            for line in splitter.stdout:
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
                blob = add_blob(destination, raw)
                files.append({"path": destination, "bytes": len(raw), "sha256": event["sha256"],
                              "git_blob_sha1": blob, "first_line": event["first_line"],
                              "last_line": event["last_line"], "records": event["records"],
                              "annotated_start_byte": offset, "annotated_end_byte_exclusive": offset + len(raw)})
                offset += len(raw)
                del raw
                path.unlink()
                splitter.stdin.write(b"ok\n")
                splitter.stdin.flush()
                if len(files) % 10 == 0:
                    self.event(type="chunks_imported", part=number, chunks=len(files), annotated_bytes=offset)
                pack_bytes = sum(x.stat().st_size for x in (directory / "objects" / "pack").iterdir() if x.is_file())
                if pack_bytes > 1450 * 1024 * 1024:
                    raise RuntimeError("Batch pack exceeded the conservative push-size budget; no incomplete volume will be published")
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
            manifest = {"schema": "annotation-volume-chunks-v1", "status": "complete", "part": number,
                        "source": part, "actual": complete, "chunk_max_bytes": CHUNK_BYTES,
                        "chunks": files, "byte_preservation": "Concatenate chunks in this listed order to recover exact decompressed bytes."}
            manifest_raw = encoded(manifest)
            manifest_path = f"{PREFIX}/part{number:03d}/manifest.json"
            add_blob(manifest_path, manifest_raw)
            record = {"part": number, "source_file": part["file"], "source_compressed_sha256": part["compressed_sha256"],
                      "first_line": part["first_line"], "last_line": part["last_line"], "records": part["records"],
                      "annotated_bytes": offset, "annotated_sha256": complete["annotated_sha256"],
                      "original_bytes": part["original_bytes"], "original_sha256": part["original_sha256"],
                      "chunks": len(files), "manifest": manifest_path, "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest()}
            progress["completed_parts"].append(record)
            done_count = len(progress["completed_parts"])
            assert [x["part"] for x in progress["completed_parts"]] == list(range(1, done_count + 1))
            progress["status"] = "complete" if done_count == 57 else "in_progress"
            progress["completed_annotated_bytes"] = sum(x["annotated_bytes"] for x in progress["completed_parts"])
            progress["completed_original_records"] = sum(x["records"] for x in progress["completed_parts"])
            progress["completed_chunks"] = sum(x["chunks"] for x in progress["completed_parts"])
            if done_count == 57:
                assert progress["completed_annotated_bytes"] == 168547118127
                assert progress["completed_original_records"] == 1080769508
            add_blob(f"{PREFIX}/progress.json", encoded(progress))
            add_blob(f"{PREFIX}/README.md", self.make_readme(progress))
            document_updates = self.updated_docs(directory, progress)
            for path, raw in document_updates.items():
                add_blob(path, raw)
            if number == 1:
                for name in ("split_annotations.cpp", "test_split_annotations.py", "test_results.json", "README.md"):
                    add_blob(f"{PREFIX}/tools/{name}", (self.args.splitter.parent / name).read_bytes())
            add_blob(f"{PREFIX}/tools/upload_annotations.py", Path(__file__).read_bytes())
            message = f"Expand verified full annotation volume {number:03d} into {len(files)} TXT files".encode()
            importer.stdin.write((f"commit refs/heads/main\ncommitter ChatGPT <noreply@openai.com> {int(time.time())} +0000\ndata {len(message)}\n").encode())
            importer.stdin.write(message + b"\n")
            importer.stdin.write(f"from {parent}\n".encode())
            for path, mark in marks.items():
                importer.stdin.write(f"M 100644 :{mark} {path}\n".encode())
            importer.stdin.write(b"\ndone\n")
            importer.stdin.close()
            if importer.wait() != 0:
                raise RuntimeError("Git fast-import failed; see local Git log")
            head = self.git(directory, "rev-parse", "HEAD").stdout.decode().strip()
            tree = self.git(directory, "rev-parse", "HEAD^{tree}").stdout.decode().strip()
            assert self.git(directory, "rev-parse", "HEAD:project/lean/original").stdout.strip() == original_tree
            batch_input = b"".join(x["git_blob_sha1"].encode() + b"\n" for x in files)
            observed = self.git(directory, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", input=batch_input).stdout.decode().splitlines()
            assert len(observed) == len(files)
            for info, expected in zip(observed, files):
                blob, kind, size = info.split()
                assert kind == "blob" and blob == expected["git_blob_sha1"] and int(size) == expected["bytes"]
            before = self.get("/git/ref/heads/main")["object"]["sha"]
            assert before == parent, "Remote main changed; stop before overwriting concurrent work"
            self.event(type="volume_verified_pushing", part=number, chunks=len(files), commit=head,
                       git_object_bytes=sum(x.stat().st_size for x in (directory / "objects" / "pack").iterdir() if x.is_file()))
            result = self.git(directory, "push", "origin", head + ":refs/heads/main")
            after = self.get("/git/ref/heads/main")["object"]["sha"]
            assert after == head, "Published branch differs from prepared commit"
            remote_tree = self.get("/git/commits/" + head)["tree"]["sha"]
            assert remote_tree == tree, "Published tree differs from prepared tree"
            self.document_cache_head = head
            self.document_cache = {**document_updates, PREFIX + "/progress.json": encoded(progress)}
            receipt = {"part": number, "commit": head, "tree": tree, "parent": parent,
                       "remote_verified": True, "chunks": len(files), "annotated_bytes": offset,
                       "records": part["records"], "progress": progress}
            (self.root / "reports" / f"part{number:03d}.json").write_bytes(encoded(receipt))
            self.event(type="volume_uploaded", part=number, chunks=len(files), commit=head,
                       completed_parts=done_count, completed_bytes=progress["completed_annotated_bytes"])
            source.unlink()
            shutil.rmtree(directory)
            chunks_dir.rmdir()
            return progress
        except BaseException:
            for process in (splitter, importer):
                if process.poll() is None:
                    process.terminate()
                    process.wait()
            raise
        finally:
            git_log.close()
            split_log.close()

    def run(self):
        repository = self.get("")
        assert repository["full_name"] == REPOSITORY and repository["id"] == 1467518482
        assert repository["owner"]["id"] == 21255612 and repository["permissions"]["push"]
        first_batch = self.clone_batch(0)
        raw_progress = self.read_blob(first_batch, f"{PREFIX}/progress.json", required=False)
        progress = json.loads(raw_progress) if raw_progress is not None else self.initial_progress()
        assert progress["schema"] == "ordinary-git-annotation-expansion-v1"
        completed = len(progress["completed_parts"])
        assert 0 <= completed <= 57
        assert [x["part"] for x in progress["completed_parts"]] == list(range(1, completed + 1))
        tracked = {}
        for entry in self.git(first_batch, "ls-tree", "-r", "-z", "HEAD", "--", PREFIX).stdout.split(b"\0"):
            if entry:
                properties, path = entry.split(b"\t", 1)
                mode, kind, object_id = properties.decode().split()
                tracked[path.decode()] = (mode, kind, object_id)
        for item, part in zip(progress["completed_parts"], self.parts):
            assert item["source_compressed_sha256"] == part["compressed_sha256"]
            assert item["annotated_bytes"] == part["annotated_bytes"]
            original_manifest = self.read_blob(first_batch, item["manifest"])
            assert hashlib.sha256(original_manifest).hexdigest() == item["manifest_sha256"]
            manifest = json.loads(original_manifest)
            assert manifest["status"] == "complete" and manifest["part"] == item["part"]
            assert manifest["source"] == part
            assert manifest["actual"]["original_sha256"] == part["original_sha256"]
            assert manifest["actual"]["records"] == part["records"]
            assert len(manifest["chunks"]) == item["chunks"]
            assert sum(x["bytes"] for x in manifest["chunks"]) == part["annotated_bytes"]
            for chunk in manifest["chunks"]:
                assert tracked.get(chunk["path"]) == ("100644", "blob", chunk["git_blob_sha1"]), "Previously published chunk changed or disappeared"
        self.event(type="resume_state", completed_parts=completed, total_parts=57)
        if completed == 57:
            shutil.rmtree(first_batch)
            self.event(type="all_complete", already_complete=True)
            return
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.download, completed + 1)
            for number in range(completed + 1, 58):
                source = future.result()
                if number < 57:
                    future = pool.submit(self.download, number + 1)
                directory = first_batch if number == completed + 1 else self.clone_batch(number)
                if number != completed + 1:
                    remote_progress = json.loads(self.read_blob(directory, f"{PREFIX}/progress.json"))
                    assert remote_progress == progress, "Remote progress changed unexpectedly"
                progress = self.publish_part(number, source, directory, progress)
        self.event(type="all_complete", completed_parts=57, chunks=progress["completed_chunks"],
                   annotated_bytes=progress["completed_annotated_bytes"], original_records=progress["completed_original_records"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--splitter", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
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


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"type": "stopped", "error": str(error)}, ensure_ascii=False), file=sys.stderr, flush=True)
        sys.exit(1)
