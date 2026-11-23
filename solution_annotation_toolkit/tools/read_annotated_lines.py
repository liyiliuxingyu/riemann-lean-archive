#!/usr/bin/env python3
"""Extract a source-line interval and its Chinese annotations from the right shards.

Requires Python 3 and the zstd command line program. Output remains byte-for-byte
identical to the selected annotation/record pairs; no JSON reserialization occurs.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="按原始行号读取中文注释，无需解压全部分卷")
    parser.add_argument("--manifest", required=True, type=Path, help="parts.jsonl 路径")
    parser.add_argument("--parts-dir", type=Path, help="分卷目录，默认清单所在目录")
    parser.add_argument("--start", required=True, type=int, help="首个原始行号，从 1 起")
    parser.add_argument("--end", required=True, type=int, help="末尾原始行号，包含该行")
    parser.add_argument("--output", type=Path, help="保存到新的文本文件；默认标准输出")
    args = parser.parse_args()
    if args.start < 1 or args.end < args.start:
        parser.error("须满足 1 <= start <= end")
    parts = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line]
    if not parts or args.end > parts[-1]["last_line"]:
        parser.error("请求行号超出完整清单范围")
    previous = 0
    for part in parts:
        if part["first_line"] != previous + 1 or part["last_line"] < part["first_line"]:
            parser.error("清单行号不连续")
        if part["records"] != part["last_line"] - part["first_line"] + 1:
            parser.error("清单计数不符")
        previous = part["last_line"]
    directory = args.parts_dir or args.manifest.parent
    temporary = None
    output = sys.stdout.buffer
    if args.output:
        if args.output.exists():
            parser.error("输出文件已存在；请选择新文件名")
        temporary = args.output.with_name(args.output.name + ".partial")
        output = temporary.open("xb")
    count = 0
    try:
        for part in parts:
            if part["last_line"] < args.start or part["first_line"] > args.end:
                continue
            name = part["file"]
            if Path(name).name != name:
                raise ValueError("清单文件名必须是不含目录的文件名")
            path = directory / name
            if path.stat().st_size != part["compressed_bytes"]:
                raise ValueError(f"分卷大小不符：{name}")
            proc = subprocess.Popen(["zstd", "-dc", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            finished_part = False
            try:
                for row in range(part["first_line"], min(part["last_line"], args.end) + 1):
                    comment = proc.stdout.readline()
                    original = proc.stdout.readline()
                    if not comment.startswith(f"-- @line {row} ".encode()) or not original:
                        raise ValueError(f"注释/原文对损坏：原行号 {row}")
                    if row >= args.start:
                        output.write(comment)
                        output.write(original)
                        count += 1
                if args.end >= part["last_line"]:
                    if proc.stdout.read(1):
                        raise ValueError(f"清单记录末尾存在多余数据：{name}")
                    finished_part = True
                    if proc.wait() != 0:
                        raise ValueError(f"分卷解压失败：{name}")
            finally:
                proc.stdout.close()
                if not finished_part and proc.poll() is None:
                    proc.terminate()
                proc.wait()
        if count != args.end - args.start + 1:
            raise ValueError("未读取到所请求的全部原始行")
        output.flush()
        if temporary:
            output.close()
            # Link fails if another process created the target in the meantime.
            os.link(temporary, args.output)
            temporary.unlink()
        return 0
    except BrokenPipeError:
        return 0
    finally:
        if temporary and not output.closed:
            output.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)
