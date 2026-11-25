#!/usr/bin/env python3
"""Verify the 643 files unpacked into ordinary Git on 2026-11-25."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=root / "docs" / "unpacked-files-20261125.json",
    )
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if data.get("schema") != "github-individual-file-expansion-v1":
        raise ValueError("Unsupported manifest schema")

    failures = []
    seen = set()
    total = 0
    for item in data["files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid manifest path: {relative}")
        if str(relative) in seen:
            raise ValueError(f"Duplicate manifest path: {relative}")
        seen.add(str(relative))
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Path escapes repository: {relative}")
        if not path.is_file() or path.is_symlink():
            failures.append({"path": str(relative), "error": "missing or not a regular file"})
            continue
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
        total += size
        if size != item["bytes"] or digest.hexdigest() != item["sha256"]:
            failures.append({"path": str(relative), "error": "size or SHA-256 mismatch"})

    if len(seen) != data["expanded_file_count"]:
        failures.append({"error": "manifest file count mismatch"})
    if total != data["expanded_bytes"]:
        failures.append({"error": "expanded byte total mismatch"})
    print(json.dumps({
        "scope": "expanded archive files only; no Lean proof checking",
        "files_checked": len(seen),
        "bytes_read": total,
        "failures": failures,
        "ok": not failures,
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
