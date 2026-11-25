#!/usr/bin/env python3
"""Losslessly gather a Lean project's source files into ONE readable .lean bundle.

This is a reversible SOURCE ARCHIVE, not an elaborated Lean module or a kernel
proof export. Original import commands, scopes, and source bytes are preserved.
The archive must be restored to its module tree before normal Lean compilation.

Python 3.11+. No third-party dependencies; source bytes are streamed, and the
module/import catalogue is kept in SQLite. Standard header imports are parsed
without executing Lean or any project code. The parser supports nested comments,
UTF-8 names, quoted identifier components, module/prelude, public/meta/import all.
It does not elaborate custom syntax or establish theorem-level dependencies.
"""
from __future__ import annotations

import argparse
import array
import base64
import hashlib
import heapq
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys

CHUNK = 1024 * 1024
FORMAT = "lean-source-bundle-v1"
START = b"-- @LEAN_SOURCE_BUNDLE_FILE "
END = b"\n-- @LEAN_SOURCE_BUNDLE_END_FILE\n"
AUX = b"-- @LEAN_SOURCE_BUNDLE_AUX "
FOOTER = b"-- @LEAN_SOURCE_BUNDLE_COMPLETE "
PREAMBLE = (
    "-- Lean 源码无损汇编 / Reversible Lean source archive.\n"
    "-- 本文件未经 Lean 编译；模块正文原样保留，不能视为新的单体证明。\n"
    "-- NOT a standalone Lean module, NOT an elaborated kernel proof export.\n"
    "-- Restore original modules using export_lean_bundle.py restore before building.\n"
    "-- Module boundaries use exact byte lengths; marker-like text inside source is harmless.\n"
)
DEFAULT_EXTERNAL = {
    "Init", "Lean", "Std", "Mathlib", "Aesop", "Batteries", "Qq", "Cli",
    "ProofWidgets", "ImportGraph", "Plausible", "LeanSearchClient", "Archive",
    "MathlibTest", "MathlibTestFunctions", "Lake",
}
CONFIG_NAMES = ("lean-toolchain", "lakefile.toml", "lakefile.lean", "lake-manifest.json",
                "LICENSE", "LICENSE.md", "LICENSE.txt", "README", "README.md", "README.txt")


def js(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sha_file(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe relative path: {value!r}")
    return path


def source_files(root: Path):
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(n for n in names if n not in {".git", ".lake", "__pycache__"})
        for name in sorted(files):
            if name.endswith(".lean"):
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError(f"Source symlink is not accepted: {path}")
                yield path


def header_tokens(path: Path):
    """Tokens needed only for the standard module header; stop consuming at body."""
    depth = 0
    quoted = False
    token = []
    token_line = 1
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for line_no, line in enumerate(stream, 1):
            i = 0
            while i < len(line):
                pair = line[i:i + 2]
                char = line[i]
                if depth:
                    if pair == "/-":
                        depth += 1
                        i += 2
                    elif pair == "-/":
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                    continue
                if quoted:
                    token.append(char)
                    if char == "»":
                        quoted = False
                    i += 1
                    continue
                if pair in {"/-", "--"}:
                    if token:
                        yield "".join(token), token_line
                        token.clear()
                    if pair == "--":
                        break
                    depth = 1
                    i += 2
                    continue
                if char.isspace():
                    if token:
                        yield "".join(token), token_line
                        token.clear()
                    i += 1
                    continue
                if not token:
                    token_line = line_no
                token.append(char)
                if char == "«":
                    quoted = True
                i += 1
    if token:
        yield "".join(token), token_line
    if depth or quoted:
        raise ValueError(f"Unterminated header comment or quoted name in {path}")


def normalize_module(name):
    parts = []
    current = []
    quoted = False
    for char in name:
        if char == "«" and not quoted:
            quoted = True
        elif char == "»" and quoted:
            quoted = False
        elif char == "." and not quoted:
            parts.append("".join(current))
            current.clear()
        else:
            current.append(char)
    parts.append("".join(current))
    if quoted or any(not part for part in parts):
        raise ValueError(f"Invalid module name in header: {name!r}")
    return ".".join(parts)


def parse_imports(path):
    tokens = iter(header_tokens(path))
    imports = []
    current = next(tokens, None)
    if current and current[0] == "module":
        current = next(tokens, None)
    if current and current[0] == "prelude":
        current = next(tokens, None)
    while current:
        modifiers = []
        while current and current[0] in {"public", "meta"}:
            modifiers.append(current[0])
            current = next(tokens, None)
        if not current or current[0] != "import":
            break
        import_line = current[1]
        target = next(tokens, None)
        if target and target[0] == "all":
            modifiers.append("all")
            target = next(tokens, None)
        if not target:
            raise ValueError(f"Missing import target in {path}:{import_line}")
        imports.append((normalize_module(target[0]), import_line, " ".join(modifiers)))
        current = next(tokens, None)
    return imports


def hash_and_count(path):
    digest = hashlib.sha256()
    size = 0
    linefeeds = 0
    last = b""
    with path.open("rb") as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
            size += len(block)
            linefeeds += block.count(b"\n")
            last = block[-1:]
    return digest.hexdigest(), size, linefeeds + int(size > 0 and last != b"\n"), linefeeds


def catalogue(args, project, source, database):
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    connection.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE files(id INTEGER PRIMARY KEY, path TEXT UNIQUE, module TEXT UNIQUE,
          bytes INTEGER, sha256 TEXT, lines INTEGER, linefeeds INTEGER);
        CREATE TABLE imports(source_id INTEGER, target TEXT, line INTEGER, modifiers TEXT);
        CREATE TABLE edges(source_id INTEGER, dependency_id INTEGER,
          PRIMARY KEY(source_id,dependency_id)) WITHOUT ROWID;
        CREATE TABLE ordering(sequence INTEGER PRIMARY KEY, file_id INTEGER UNIQUE);
        CREATE INDEX imports_target ON imports(target);
        CREATE INDEX imports_source ON imports(source_id);
        CREATE INDEX files_hash ON files(sha256);
    """)
    count = 0
    for count, path in enumerate(source_files(source), 1):
        relative = path.relative_to(project).as_posix()
        module = ".".join(path.relative_to(source).with_suffix("").parts)
        digest, size, lines, linefeeds = hash_and_count(path)
        connection.execute("INSERT INTO files VALUES(?,?,?,?,?,?,?)",
                           (count, relative, module, size, digest, lines, linefeeds))
        connection.executemany("INSERT INTO imports VALUES(?,?,?,?)",
                               ((count, target, line, mods) for target, line, mods in parse_imports(path)))
        if count % 5000 == 0:
            connection.commit()
            print(f"Catalogued {count} modules", file=sys.stderr, flush=True)
    if not count:
        raise ValueError(f"No Lean sources found in {source}")
    connection.execute("INSERT OR IGNORE INTO edges SELECT i.source_id,f.id FROM imports i JOIN files f ON i.target=f.module")
    connection.execute("CREATE INDEX edges_dependency ON edges(dependency_id)")
    connection.commit()
    indegree = array.array("I", [0]) * (count + 1)
    for ident, degree in connection.execute("SELECT source_id,COUNT(*) FROM edges GROUP BY source_id"):
        indegree[ident] = degree
    ready = [ident for ident in range(1, count + 1) if indegree[ident] == 0]
    heapq.heapify(ready)
    sequence = 0
    while ready:
        ident = heapq.heappop(ready)
        sequence += 1
        connection.execute("INSERT INTO ordering VALUES(?,?)", (sequence, ident))
        for (dependent,) in connection.execute("SELECT source_id FROM edges WHERE dependency_id=?", (ident,)):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if sequence != count:
        remaining = [row[0] for row in connection.execute("SELECT module FROM files WHERE id NOT IN (SELECT file_id FROM ordering) LIMIT 20")]
        raise ValueError(f"Internal import cycle (or dependents of cycle): {remaining}")
    connection.commit()
    return connection


def export(args):
    project = args.project_root.resolve()
    source = (args.source_root or project / "src").resolve()
    if not source.is_relative_to(project):
        raise ValueError("Source root must be inside project root")
    output = args.output.resolve()
    if output.is_relative_to(source):
        raise ValueError("Output must be outside the source tree")
    output.parent.mkdir(parents=True, exist_ok=True)
    database = output.with_suffix(".catalog.sqlite")
    connection = catalogue(args, project, source, database)
    expected_external = DEFAULT_EXTERNAL | set(args.external_prefix or [])
    unresolved = []
    external = []
    for module, users in connection.execute("SELECT i.target,COUNT(DISTINCT i.source_id) FROM imports i LEFT JOIN files f ON i.target=f.module WHERE f.id IS NULL GROUP BY i.target ORDER BY i.target"):
        record = {"module": module, "imported_by_count": users}
        (external if module.split(".")[0] in expected_external else unresolved).append(record)
    dependency_path = output.with_suffix(".dependencies.jsonl")
    with dependency_path.open("w", encoding="utf-8") as stream:
        query = "SELECT s.module,i.target,i.line,i.modifiers,t.id FROM imports i JOIN files s ON s.id=i.source_id LEFT JOIN files t ON t.module=i.target ORDER BY i.source_id,i.line,i.target"
        for source_name, target, line, modifiers, target_id in connection.execute(query):
            stream.write(js({"source": source_name, "target": target, "source_line": line,
                             "modifiers": modifiers, "in_bundle": target_id is not None}) + "\n")
    missing_path = output.with_suffix(".unresolved.json")
    missing_path.write_text(json.dumps({"expected_external_imports": external,
                                       "unresolved_project_or_unknown_imports": unresolved},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.require_closed_project_imports and unresolved:
        raise ValueError(f"{len(unresolved)} project/unknown imports are absent; see {missing_path}")
    count, total_bytes, total_lines = connection.execute("SELECT COUNT(*),SUM(bytes),SUM(lines) FROM files").fetchone()
    index_path = output.with_suffix(".index.jsonl")
    duplicate_path = output.with_suffix(".duplicates.jsonl")
    with duplicate_path.open("w", encoding="utf-8") as duplicates:
        for digest, copies in connection.execute("SELECT sha256,COUNT(*) FROM files GROUP BY sha256 HAVING COUNT(*)>1"):
            paths = [row[0] for row in connection.execute("SELECT path FROM files WHERE sha256=? ORDER BY path", (digest,))]
            duplicates.write(js({"sha256": digest, "copies": copies, "paths": paths,
                                 "action": "all distinct module paths preserved"}) + "\n")
    bundle_hash = hashlib.sha256()
    newline_count = 0
    aux_count = 0
    partial = output.with_suffix(output.suffix + ".partial")
    with partial.open("wb") as bundle, index_path.open("w", encoding="utf-8") as index:
        def write(block):
            nonlocal newline_count
            bundle.write(block)
            bundle_hash.update(block)
            newline_count += block.count(b"\n")
        write(PREAMBLE.encode("utf-8"))
        write(("-- @LEAN_SOURCE_BUNDLE_META " + js({"format": FORMAT,
              "source_root": source.relative_to(project).as_posix(), "module_count": count,
              "original_source_bytes": total_bytes, "original_source_lines": total_lines,
              "order": "topological on included modules; deterministic path-derived tie order",
              "not_a_compilable_single_module": True,
              "source_bytes_rewritten": False}) + "\n").encode("utf-8"))
        for name in CONFIG_NAMES:
            path = project / name
            if path.is_file() and not path.is_symlink() and not path.is_relative_to(source):
                if path.stat().st_size > 8 * CHUNK:
                    raise ValueError(f"Unexpectedly large auxiliary config: {path}")
                data = path.read_bytes()
                metadata = {"kind": "auxiliary", "path": name, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "base64": base64.b64encode(data).decode("ascii")}
                write(AUX + js(metadata).encode("utf-8") + b"\n")
                index.write(js({key: value for key, value in metadata.items() if key != "base64"}) + "\n")
                aux_count += 1
        query = "SELECT o.sequence,f.id,f.path,f.module,f.bytes,f.sha256,f.lines,f.linefeeds FROM ordering o JOIN files f ON f.id=o.file_id ORDER BY o.sequence"
        for sequence, ident, relative, module, size, digest, lines, linefeeds in connection.execute(query):
            record = {"kind": "source", "sequence": sequence, "path": relative,
                      "module": module, "bytes": size, "sha256": digest, "lines": lines}
            write(START + js(record).encode("utf-8") + b"\n")
            record["byte_offset"] = bundle.tell()
            record["line_start"] = newline_count + 1
            actual_hash = hashlib.sha256()
            actual_size = 0
            with (project / relative).open("rb") as source_stream:
                while block := source_stream.read(CHUNK):
                    actual_hash.update(block)
                    actual_size += len(block)
                    write(block)
            if actual_size != size or actual_hash.hexdigest() != digest:
                raise ValueError(f"Source changed after cataloguing: {relative}")
            write(END)
            index.write(js(record) + "\n")
            if sequence % 10000 == 0:
                print(f"Exported {sequence}/{count} modules", file=sys.stderr, flush=True)
        write(FOOTER + js({"module_count": count, "auxiliary_count": aux_count,
                          "original_source_bytes": total_bytes}).encode("utf-8") + b"\n")
    partial.replace(output)
    report = {"format": FORMAT, "file": output.name, "source_root": source.relative_to(project).as_posix(),
              "module_count": count, "original_source_bytes": total_bytes,
              "original_source_lines": total_lines, "auxiliary_count": aux_count,
              "bundle_bytes": output.stat().st_size, "bundle_sha256": bundle_hash.hexdigest(),
              "dependency_edges": connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
              "internal_dependency_order_acyclic": True,
              "unresolved_project_or_unknown_imports": len(unresolved),
              "project_imports_closed_under_configured_external_prefixes": not unresolved,
              "external_imports_included": False, "lean_compilation_performed": False,
              "kernel_export": False, "source_archive_only": True,
              "hash_index": index_path.name, "dependency_index": dependency_path.name,
              "duplicate_content_index": duplicate_path.name,
              "parser_scope": "standard module header imports only; not declaration dependency analysis"}
    output.with_suffix(".summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    connection.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


def consume_bundle(args, restoring=False):
    bundle_path = args.bundle.resolve()
    destination = args.destination.resolve() if restoring else None
    comparison = args.against_root.resolve() if args.against_root else None
    if destination:
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Restore destination must be new or empty; no existing project is overwritten")
        destination.mkdir(parents=True, exist_ok=True)
    files = 0
    auxiliary = 0
    total_bytes = 0
    seen = set()
    seen_sources = set()
    finished = False
    metadata_seen = False
    with bundle_path.open("rb") as stream:
        while line := stream.readline():
            if line.startswith(b"-- @LEAN_SOURCE_BUNDLE_META "):
                metadata = json.loads(line.split(b" ", 2)[2])
                if metadata.get("format") != FORMAT:
                    raise ValueError("Unsupported bundle format")
                metadata_seen = True
            elif line.startswith(START) or line.startswith(AUX):
                is_source = line.startswith(START)
                prefix = START if is_source else AUX
                record = json.loads(line[len(prefix):])
                relative = str(checked_relative(record["path"]))
                if relative in seen:
                    raise ValueError(f"Duplicate archived path: {relative}")
                seen.add(relative)
                expected_bytes = record["bytes"]
                if not isinstance(expected_bytes, int) or expected_bytes < 0:
                    raise ValueError("Invalid file length")
                target = destination / relative if destination else None
                if target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                writer = target.open("xb") if target else None
                digest = hashlib.sha256()
                try:
                    if is_source:
                        remaining = expected_bytes
                        while remaining:
                            block = stream.read(min(CHUNK, remaining))
                            if not block:
                                raise ValueError(f"Truncated source: {relative}")
                            remaining -= len(block)
                            digest.update(block)
                            if writer:
                                writer.write(block)
                        if stream.read(len(END)) != END:
                            raise ValueError(f"Invalid source boundary: {relative}")
                        files += 1
                        total_bytes += expected_bytes
                        seen_sources.add(relative)
                    else:
                        data = base64.b64decode(record["base64"], validate=True)
                        if len(data) != expected_bytes:
                            raise ValueError(f"Auxiliary byte count mismatch: {relative}")
                        digest.update(data)
                        if writer:
                            writer.write(data)
                        auxiliary += 1
                finally:
                    if writer:
                        writer.close()
                if digest.hexdigest() != record["sha256"]:
                    raise ValueError(f"SHA256 mismatch: {relative}")
                if comparison:
                    original = comparison / relative
                    if not original.is_file() or original.stat().st_size != expected_bytes or sha_file(original) != record["sha256"]:
                        raise ValueError(f"Original-file comparison failed: {relative}")
            elif line.startswith(FOOTER):
                footer = json.loads(line[len(FOOTER):])
                if footer != {"module_count": files, "auxiliary_count": auxiliary, "original_source_bytes": total_bytes}:
                    raise ValueError("Bundle footer totals do not match")
                if stream.read():
                    raise ValueError("Unexpected bytes after bundle footer")
                finished = True
                break
            elif not line.startswith(b"--") and line.strip():
                raise ValueError("Unexpected data outside module records")
    if not metadata_seen or not finished:
        raise ValueError("Incomplete bundle: metadata or completion footer missing")
    if metadata.get("module_count") != files or metadata.get("original_source_bytes") != total_bytes:
        raise ValueError("Bundle header totals do not match its contents")
    if comparison:
        comparison_source = comparison / str(checked_relative(metadata["source_root"]))
        expected_sources = {p.relative_to(comparison).as_posix() for p in source_files(comparison_source)}
        if seen_sources != expected_sources:
            raise ValueError(f"Source inventory mismatch: {len(expected_sources - seen_sources)} missing, {len(seen_sources - expected_sources)} extra")
    result = {"operation": "restore" if restoring else "verify", "module_count": files,
              "auxiliary_count": auxiliary, "source_bytes": total_bytes,
              "all_embedded_sha256_passed": True, "compared_with_originals": bool(comparison),
              "lean_compilation_performed": False, "bundle_sha256": sha_file(bundle_path)}
    if destination:
        result["destination"] = str(destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("export", help="Create lossless source archive, dependency index, and hashes")
    build.add_argument("--project-root", type=Path, required=True)
    build.add_argument("--source-root", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--external-prefix", action="append")
    build.add_argument("--require-closed-project-imports", action="store_true")
    for command in ("verify", "restore"):
        child = sub.add_parser(command)
        child.add_argument("--bundle", type=Path, required=True)
        child.add_argument("--against-root", type=Path)
        if command == "restore":
            child.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "export":
            export(args)
        else:
            consume_bundle(args, args.command == "restore")
    except (ValueError, OSError, sqlite3.Error, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
