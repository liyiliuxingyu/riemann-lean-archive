#!/usr/bin/env python3
"""Independently verify the manifest's import-only byte deletions and Lean headers.

Run from the repository root, or pass --repo.  Only Python's standard library,
Git, and the official Lean 4.33.1 release are needed.  Project dependencies are
not needed: the Lean helper parses headers without resolving imports.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time


BASELINE = "b32465bf0a42b702d7834fbb5f983fe413fa5aa6"
LEAN_VERSION = "4.33.1"
LEAN_COMMIT = "819816b2e0a3bf405af45ae5c7af2491d8f5bee6"
FIELDS = {"path", "before_sha256", "after_sha256", "removed_lines", "removed_bytes"}
IMPORT_LINE = re.compile(rb"[ \t]*import[ \t]+([^\s]+)[ \t]*(?:\r?\n)?")
INITIAL_IMPORTS = [("Init", True, False, False), ("Init", True, True, False)]


class VerificationError(Exception):
    def __init__(self, code, path=None):
        super().__init__(code)
        self.code, self.path = code, path


def require(condition, code, path=None):
    if not condition:
        raise VerificationError(code, path)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def plain_import_target(line, rel):
    """Accept only simple bare module names; never consume comment delimiters."""
    match = IMPORT_LINE.fullmatch(line)
    require(match is not None, "removed_line_is_not_plain_import", rel)
    target = match.group(1).decode("utf-8")
    parts = target.split(".")
    require(all(part and (part[0].isalpha() or part[0] == "_")
                and all(char.isalnum() or char in "_'" for char in part)
                for part in parts), "removed_line_is_not_plain_import", rel)
    return target


def read_changes(path):
    raw = path.read_bytes()
    rows, seen = [], set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        require(isinstance(row, dict) and set(row) == FIELDS, "invalid_manifest_fields")
        rel = row["path"]
        require(isinstance(rel, str) and rel and not any(c in rel for c in "\x00\r\n\\"), "invalid_manifest_path")
        pure = PurePosixPath(rel)
        require(not pure.is_absolute() and ".." not in pure.parts and str(pure) == rel, "unsafe_manifest_path")
        require(rel.startswith("project/lean/original/src/") and rel.endswith(".lean"), "unexpected_manifest_scope", rel)
        require(rel not in seen, "duplicate_manifest_path", rel)
        seen.add(rel)
        for key in ("before_sha256", "after_sha256"):
            require(isinstance(row[key], str) and re.fullmatch(r"[0-9a-f]{64}", row[key]), "invalid_manifest_hash", rel)
        lines = row["removed_lines"]
        require(isinstance(lines, list) and bool(lines) and all(type(n) is int and n > 0 for n in lines), "invalid_removed_lines", rel)
        require(lines == sorted(set(lines)), "removed_lines_not_sorted_and_unique", rel)
        require(type(row["removed_bytes"]) is int and row["removed_bytes"] > 0, "invalid_removed_bytes", rel)
        rows.append(row)
    require(bool(rows), "empty_manifest")
    require([row["path"] for row in rows] == sorted(seen), "manifest_paths_not_sorted")
    return rows, sha256(raw)


class GitBatch:
    """One request is flushed and fully read before the next; no pipe deadlock."""
    def __init__(self, repo, baseline, stderr_path, blob_ids=None):
        self.baseline = baseline
        self.blob_ids = blob_ids
        self.err = stderr_path.open("wb")
        try:
            self.proc = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err)
        except BaseException:
            self.err.close()
            raise

    def __enter__(self):
        return self

    def read(self, rel):
        object_name = self.blob_ids[rel] if self.blob_ids is not None else self.baseline + ":" + rel
        request = (object_name + "\n").encode("utf-8")
        self.proc.stdin.write(request)
        self.proc.stdin.flush()
        response = self.proc.stdout.readline().rstrip(b"\n").split()
        require(len(response) == 3 and response[1] == b"blob", "baseline_blob_not_found", rel)
        if self.blob_ids is not None:
            require(response[0].decode("ascii") == object_name, "git_batch_object_id_mismatch", rel)
        try:
            size = int(response[2])
        except ValueError:
            raise VerificationError("invalid_git_batch_response", rel) from None
        data = self.proc.stdout.read(size)
        require(len(data) == size and self.proc.stdout.read(1) == b"\n", "truncated_git_batch_blob", rel)
        return data

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self.proc.stdin.close()
                require(self.proc.wait(timeout=30) == 0, "git_batch_failed")
            elif self.proc.poll() is None:
                self.proc.terminate()
                self.proc.wait(timeout=30)
        finally:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()
            self.proc.stdout.close()
            if not self.proc.stdin.closed:
                self.proc.stdin.close()
            self.err.close()


def resolve_baseline(repo, baseline):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", baseline)), "baseline_must_be_full_commit_hash")
    result = subprocess.run(["git", "rev-parse", "--verify", baseline + "^{commit}"],
                            cwd=repo, capture_output=True, timeout=30)
    require(result.returncode == 0, "baseline_commit_unavailable")
    resolved = result.stdout.decode("ascii").strip()
    require(resolved == baseline, "baseline_commit_mismatch")
    return resolved


def baseline_blob_ids(repo, baseline, rows):
    """Read the baseline tree once, avoiding repeated large commit:path lookups."""
    selected = {row["path"].encode("utf-8"): row["path"] for row in rows}
    result = subprocess.run(["git", "ls-tree", "-rz", "--full-tree", baseline,
                             "--", "project/lean/original/src"],
                            cwd=repo, capture_output=True, timeout=120)
    require(result.returncode == 0, "baseline_tree_read_failed")
    found = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        if raw_path not in selected:
            continue
        rel = selected[raw_path]
        mode, kind, oid = metadata.split()
        require(mode in {b"100644", b"100755"} and kind == b"blob", "baseline_path_not_regular_file", rel)
        require(re.fullmatch(rb"[0-9a-f]{40}", oid) is not None, "invalid_baseline_blob_id", rel)
        found[rel] = oid.decode("ascii")
    for row in rows:
        require(row["path"] in found, "path_missing_from_baseline_tree", row["path"])
    return found


def find_lean(command):
    found = shutil.which(command)
    require(found is not None, "lean_executable_not_found")
    result = subprocess.run([found, "--version"], text=True, capture_output=True, timeout=30)
    require(result.returncode == 0, "lean_version_check_failed")
    version = result.stdout.strip()
    require(re.search(r"\bversion " + re.escape(LEAN_VERSION) + r"(?=[, )])", version) is not None,
            "lean_version_must_be_4_33_1")
    require("commit " + LEAN_COMMIT in version, "lean_release_commit_mismatch")
    # The published report records version metadata, never the local executable path.
    return str(Path(found).resolve()), version


def prepare_byte_checks(rows, repo, baseline, temp, use_parser):
    counts = Counter()
    before_hashes, after_hashes = hashlib.sha256(), hashlib.sha256()
    input_path = temp / "parser-input.jsonl"
    objects = baseline_blob_ids(repo, baseline, rows)
    with input_path.open("w", encoding="utf-8", newline="\n") as parser_input:
        with GitBatch(repo, baseline, temp / "git.stderr", objects) as batch:
            for index, row in enumerate(rows, 1):
                rel = row["path"]
                before = batch.read(rel)
                require(sha256(before) == row["before_sha256"], "baseline_sha256_mismatch", rel)
                lines = before.splitlines(keepends=True)
                removed = set(row["removed_lines"])
                require(max(removed) <= len(lines), "removed_line_out_of_range", rel)
                deleted_bytes = 0
                removed_modules = []
                for number in sorted(removed):
                    line = lines[number - 1]
                    removed_modules.append(plain_import_target(line, rel))
                    deleted_bytes += len(line)
                row["_removed_import_modules"] = removed_modules
                require(deleted_bytes == row["removed_bytes"], "removed_bytes_mismatch", rel)
                expected = b"".join(line for number, line in enumerate(lines, 1) if number not in removed)
                target = repo / rel
                require(not target.is_symlink() and target.resolve().is_relative_to(repo), "unsafe_worktree_path", rel)
                after = target.read_bytes()
                require(after == expected, "worktree_is_not_exact_manifest_line_deletion", rel)
                require(sha256(after) == row["after_sha256"], "worktree_sha256_mismatch", rel)
                before_hashes.update((rel + "\0" + row["before_sha256"] + "\n").encode())
                after_hashes.update((rel + "\0" + row["after_sha256"] + "\n").encode())
                if use_parser:
                    for stage, source in (("before", before), ("after", after)):
                        record = {"id": stage + ":" + rel, "source": source.decode("utf-8")}
                        parser_input.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                counts["files"] += 1
                counts["removed_lines"] += len(removed)
                counts["removed_bytes"] += deleted_bytes
                counts["baseline_bytes_read"] += len(before)
                counts["worktree_bytes_read"] += len(after)
                if index % 5000 == 0:
                    print(f"Verified exact byte deletions: {index} / {len(rows)}", file=sys.stderr, flush=True)
    return {**dict(counts), "all_baseline_hashes_match": True, "all_worktree_hashes_match": True,
            "all_edits_are_exact_listed_line_deletions": True, "all_removed_lines_are_plain_imports": True,
            "baseline_tree_resolution": "One git ls-tree traversal; git cat-file --batch requests use the selected baseline blob object IDs.",
            "baseline_path_hash_pairs_sha256": before_hashes.hexdigest(),
            "worktree_path_hash_pairs_sha256": after_hashes.hexdigest()}


def import_quads(header, rel):
    require(isinstance(header, dict) and set(header) == {"imports", "isModule"}, "unexpected_module_header_schema", rel)
    require(type(header["isModule"]) is bool and isinstance(header["imports"], list), "invalid_module_header_schema", rel)
    result = []
    for entry in header["imports"]:
        require(isinstance(entry, dict) and set(entry) == {"module", "isExported", "isMeta", "importAll"}, "unexpected_import_schema", rel)
        require(isinstance(entry["module"], str) and all(type(entry[key]) is bool for key in ("isExported", "isMeta", "importAll")), "invalid_import_schema", rel)
        result.append((entry["module"], entry["isExported"], entry["isMeta"], entry["importAll"]))
    return result


def check_lean_headers(rows, lean, version, helper, temp, timeout):
    helper_copy = temp / "ParseImportJsonl.lean"
    shutil.copyfile(helper, helper_copy)
    output_path = temp / "parser-output.jsonl"
    stderr_path = temp / "lean.stderr"
    env = dict(os.environ)
    env.pop("LEAN_PATH", None)
    # Regular input/output files cannot deadlock on pipe capacity or output buffering.
    with (temp / "parser-input.jsonl").open("rb") as source, output_path.open("wb") as output, stderr_path.open("wb") as errors:
        process = subprocess.run([lean, "--run", str(helper_copy)], cwd=temp, env=env,
                                 stdin=source, stdout=output, stderr=errors, timeout=timeout)
    require(process.returncode == 0, "official_lean_parser_process_failed")
    counts = Counter()
    before_digest, after_digest = hashlib.sha256(), hashlib.sha256()
    with output_path.open("r", encoding="utf-8") as output:
        for row in rows:
            rel = row["path"]
            headers = []
            for stage in ("before", "after"):
                line = output.readline()
                require(bool(line), "missing_official_parser_record", rel)
                record = json.loads(line)
                require(isinstance(record, dict), "invalid_official_parser_record", rel)
                require(record.get("id") == stage + ":" + rel, "official_parser_record_order_mismatch", rel)
                require("error" not in record and set(record) == {"id", "header"}, "official_header_parse_error", rel)
                headers.append(record["header"])
                counts["headers_parsed"] += 1
            before, after = headers
            before_quads, after_quads = import_quads(before, rel), import_quads(after, rel)
            before_unique = list(dict.fromkeys(before_quads))
            after_unique = list(dict.fromkeys(after_quads))
            require(before["isModule"] == after["isModule"] == False, "module_flag_changed_or_nonlegacy_header", rel)
            require(before_quads[:2] == after_quads[:2] == INITIAL_IMPORTS, "implicit_init_imports_changed", rel)
            require(all(exported and not meta and not all_ for _, exported, meta, all_ in before_quads[2:]), "nonordinary_explicit_import_flags", rel)
            require(set(before_quads) == set(after_quads), "unique_import_quadruple_set_changed", rel)
            require(before_unique == after_unique, "first_occurrence_quadruple_order_changed", rel)
            require(after_quads == before_unique, "after_header_is_not_exact_first_occurrence_deduplication", rel)
            require(len(before_quads) - len(after_quads) == len(row["removed_lines"]), "official_parser_removed_import_count_mismatch", rel)
            expected_removed = Counter((name, True, False, False) for name in row["_removed_import_modules"])
            require(Counter(before_quads) - Counter(after_quads) == expected_removed,
                    "deleted_line_module_tokens_differ_from_official_imports", rel)
            for sequence, digest in ((before_unique, before_digest), (after_unique, after_digest)):
                digest.update((json.dumps([rel, sequence], ensure_ascii=False, separators=(",", ":")) + "\n").encode())
            counts["files_compared"] += 1
            counts["imports_before_including_implicit_init"] += len(before_quads)
            counts["imports_after_including_implicit_init"] += len(after_quads)
            counts["duplicate_import_occurrences_removed"] += len(before_quads) - len(after_quads)
        require(not output.read().strip(), "unexpected_extra_official_parser_records")
    return {"status": "passed", "compiler_version": version, "required_version": LEAN_VERSION,
            "required_compiler_commit": LEAN_COMMIT, "entry_point": "Lean.parseImports'",
            "helper_sha256": sha256(helper.read_bytes()), **dict(counts),
            "quadruple_fields": ["module", "isExported", "isMeta", "importAll"],
            "all_unique_import_quadruple_sets_preserved": True,
            "all_first_occurrence_quadruple_sequences_preserved": True,
            "all_module_and_import_flags_preserved": True,
            "all_implicit_init_imports_preserved": True,
            "all_after_headers_equal_exact_first_occurrence_deduplication": True,
            "all_deleted_line_module_tokens_match_official_quadruple_differences": True,
            "before_unique_quadruple_sequences_sha256": before_digest.hexdigest(),
            "after_unique_quadruple_sequences_sha256": after_digest.hexdigest(),
            "project_imports_resolved_or_loaded": False,
            "project_declarations_elaborated": False}


def verify(args):
    started = time.monotonic()
    report = {"format": "lean-import-cleanup-verification-v1", "baseline_commit": args.baseline,
              "scope": "Only manifest-listed paths, checked against the Git baseline and current working-tree bytes.",
              "source_project_full_build_performed": False, "source_project_full_build_passed": False,
              "whole_project_kernel_verification_performed": False, "source_files_modified": False,
              "temporary_source_and_parser_files_cleaned": False}
    try:
        repo = args.repo.resolve()
        rows, manifest_hash = read_changes(args.changes)
        report["change_manifest_sha256"] = manifest_hash
        report["verifier_sha256"] = sha256(Path(__file__).read_bytes())
        report["baseline_commit"] = resolve_baseline(repo, args.baseline)
        lean, version = (None, None) if args.skip_lean_parser else find_lean(args.lean)
        with tempfile.TemporaryDirectory(prefix="verify-import-cleanup-") as directory:
            temp = Path(directory)
            report["byte_verification"] = prepare_byte_checks(rows, repo, args.baseline, temp, not args.skip_lean_parser)
            if args.skip_lean_parser:
                report["official_lean_parser"] = {"status": "skipped_by_request", "headers_parsed": 0}
                report["verification_status"] = "byte_checks_passed_parser_skipped"
                report["listed_import_cleanup_passed"] = False
            else:
                report["official_lean_parser"] = check_lean_headers(rows, lean, version, args.parser, temp, args.parser_timeout)
                report["verification_status"] = "passed"
                report["listed_import_cleanup_passed"] = True
        report["temporary_source_and_parser_files_cleaned"] = True
        report["all_requested_checks_passed"] = True
        exit_code = 0
    except VerificationError as exc:
        report["verification_status"] = "failed"
        report["error"] = {"code": exc.code}
        if exc.path is not None:
            report["error"]["repository_relative_path"] = exc.path
        report["all_requested_checks_passed"] = False
        report["listed_import_cleanup_passed"] = False
        report["temporary_source_and_parser_files_cleaned"] = True
        exit_code = 1
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        # Avoid leaking local paths from exception strings into a publishable report.
        report["verification_status"] = "failed"
        report["error"] = {"code": "runtime_error", "exception_type": type(exc).__name__}
        report["all_requested_checks_passed"] = False
        report["listed_import_cleanup_passed"] = False
        report["temporary_source_and_parser_files_cleaned"] = True
        exit_code = 1
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root; defaults to current directory.")
    parser.add_argument("--lean", default="lean", help="Official Lean 4.33.1 executable; defaults to lean on PATH.")
    parser.add_argument("--baseline", default=BASELINE, help="Full baseline commit hash.")
    parser.add_argument("--changes", type=Path, default=here / "duplicate_import_changes.jsonl", help="Defaults to the adjacent compact manifest.")
    parser.add_argument("--parser", type=Path, default=here / "ParseImportJsonl.lean", help="Defaults to the adjacent Lean helper.")
    parser.add_argument("--output", type=Path, default=here / "import_cleanup_verification.json", help="Defaults to the adjacent verification report.")
    parser.add_argument("--parser-timeout", type=int, default=900, help="Lean parser subprocess timeout in seconds.")
    parser.add_argument("--skip-lean-parser", action="store_true", help="Verify bytes only; report explicitly records incomplete parser verification.")
    return verify(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
