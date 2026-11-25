#!/usr/bin/env python3
"""Compare a pinned public source tarball, bundle index, and restored tree.

Only streams/reads the archive and source tree; never extracts or rewrites them.
This checks source identity, not Lean elaboration or kernel validity.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import time


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_relative(value: str) -> str:
    p = PurePosixPath(value)
    if p.is_absolute() or not p.parts or ".." in p.parts or "\\" in value:
        raise ValueError(f"invalid relative path: {value!r}")
    if str(p) != value:
        raise ValueError(f"noncanonical relative path: {value!r}")
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--restored", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--expected-archive-sha256", required=True)
    args = ap.parse_args()
    started = time.monotonic()
    records: dict[str, dict] = {}
    for number, line in enumerate(args.index.open(encoding="utf-8"), 1):
        row = json.loads(line)
        name = clean_relative(row["path"])
        if name in records:
            raise ValueError(f"duplicate index path at line {number}: {name}")
        if row["kind"] not in ("source", "auxiliary"):
            raise ValueError(f"unknown index kind: {row['kind']}")
        records[name] = row

    archive_sha256 = file_sha256(args.archive)
    failures: list[dict] = []
    if archive_sha256 != args.expected_archive_sha256:
        failures.append({"kind": "archive_sha256_mismatch"})
    source_count = sum(r["kind"] == "source" for r in records.values())
    auxiliary_paths = sorted(n for n, r in records.items() if r["kind"] == "auxiliary")
    if auxiliary_paths != ["lake-manifest.json", "lakefile.toml", "lean-toolchain"]:
        failures.append({"kind": "unexpected_configuration_set", "paths": auxiliary_paths})

    seen: set[str] = set()
    top_roots: set[str] = set()
    extra_archive_paths: list[str] = []
    unsafe_members: list[dict] = []
    matched_index = matched_restored = checked = source_bytes = aux_bytes = 0
    total_regular_members = directory_members = 0
    with tarfile.open(args.archive, mode="r|gz") as tf:
        for member in tf:
            raw = PurePosixPath(member.name)
            if raw.is_absolute() or ".." in raw.parts or not raw.parts or "\\" in member.name:
                unsafe_members.append({"name": member.name, "type": repr(member.type)})
                continue
            top_roots.add(raw.parts[0])
            if member.isdir():
                directory_members += 1
                continue
            if not member.isfile():
                unsafe_members.append({"name": member.name, "type": repr(member.type)})
                continue
            total_regular_members += 1
            if len(raw.parts) < 2:
                unsafe_members.append({"name": member.name, "reason": "no top-level directory"})
                continue
            name = clean_relative(str(PurePosixPath(*raw.parts[1:])))
            if name in seen:
                failures.append({"kind": "duplicate_archive_path", "path": name})
                continue
            seen.add(name)
            row = records.get(name)
            if row is None:
                extra_archive_paths.append(name)
                continue
            stream = tf.extractfile(member)
            if stream is None:
                failures.append({"kind": "unreadable_archive_member", "path": name})
                continue
            payload = stream.read()
            digest = hashlib.sha256(payload).hexdigest()
            index_ok = len(payload) == row["bytes"] and digest == row["sha256"]
            if index_ok:
                matched_index += 1
            else:
                failures.append({"kind": "tar_index_mismatch", "path": name,
                                 "archive_bytes": len(payload), "index_bytes": row["bytes"],
                                 "archive_sha256": digest, "index_sha256": row["sha256"]})
            restored_path = args.restored / name
            if restored_path.is_symlink() or not restored_path.is_file():
                failures.append({"kind": "missing_or_nonregular_restored_file", "path": name})
            else:
                restored_payload = restored_path.read_bytes()
                if restored_payload == payload:
                    matched_restored += 1
                else:
                    failures.append({"kind": "tar_restored_bytes_mismatch", "path": name,
                                     "restored_bytes": len(restored_payload),
                                     "restored_sha256": hashlib.sha256(restored_payload).hexdigest(),
                                     "archive_sha256": digest})
            checked += 1
            if row["kind"] == "source":
                source_bytes += len(payload)
            else:
                aux_bytes += len(payload)
            if checked % 25000 == 0:
                print(json.dumps({"checked": checked, "index_matches": matched_index,
                                  "restored_byte_matches": matched_restored,
                                  "failures": len(failures)}), flush=True)

    restored_paths: set[str] = set()
    restored_nonregular: list[str] = []
    for parent, dirs, files in os.walk(args.restored, followlinks=False):
        for name in dirs:
            p = Path(parent) / name
            if p.is_symlink():
                restored_nonregular.append(p.relative_to(args.restored).as_posix())
        for name in files:
            p = Path(parent) / name
            rel = p.relative_to(args.restored).as_posix()
            if p.is_symlink() or not p.is_file():
                restored_nonregular.append(rel)
            restored_paths.add(rel)

    missing_archive = sorted(set(records) - seen)
    missing_restored = sorted(set(records) - restored_paths)
    extra_restored = sorted(restored_paths - set(records))
    if len(top_roots) != 1 or next(iter(top_roots), "") != f"riemann-hypothesis-{args.commit}":
        failures.append({"kind": "unexpected_archive_top_level", "values": sorted(top_roots)})
    passed = not any((failures, unsafe_members, restored_nonregular, extra_archive_paths,
                      missing_archive, missing_restored, extra_restored)) and checked == len(records)
    canonical_manifest = hashlib.sha256()
    for name, row in sorted(records.items()):
        canonical_manifest.update(json.dumps([name, row["bytes"], row["sha256"]],
                                           ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        canonical_manifest.update(b"\n")
    result = {
        "format": "public-source-comparison-v1",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "Exact source identity only; no Lean compilation, proof elaboration, or kernel verification.",
        "public_source_url": f"https://codeload.github.com/leanprover-community/riemann-hypothesis/tar.gz/{args.commit}",
        "public_source_commit": args.commit,
        "archive": {"path": str(args.archive.resolve()), "bytes": args.archive.stat().st_size,
                    "sha256": archive_sha256, "expected_sha256": args.expected_archive_sha256,
                    "sha256_matches_expected": archive_sha256 == args.expected_archive_sha256,
                    "top_level_directories": sorted(top_roots), "regular_members": total_regular_members,
                    "directory_members": directory_members},
        "index": {"path": str(args.index.resolve()), "sha256": file_sha256(args.index),
                  "source_records": source_count, "auxiliary_records": len(auxiliary_paths),
                  "configuration_paths": auxiliary_paths,
                  "canonical_source_manifest_sha256": canonical_manifest.hexdigest()},
        "restored_tree": str(args.restored.resolve()),
        "results": {"passed": passed, "checked_files": checked,
                    "source_bytes": source_bytes, "configuration_bytes": aux_bytes,
                    "archive_index_size_and_sha256_matches": matched_index,
                    "archive_restored_exact_byte_matches": matched_restored,
                    "missing_archive_files": missing_archive,
                    "extra_archive_files": sorted(extra_archive_paths),
                    "missing_restored_files": missing_restored,
                    "extra_restored_files": extra_restored,
                    "unsafe_or_nonregular_archive_members": unsafe_members,
                    "nonregular_restored_entries": restored_nonregular,
                    "failures": failures},
        "lean_compilation_performed": False,
        "kernel_recheck_performed": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(args.output.resolve()), "passed": passed,
                      "checked": checked, "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
