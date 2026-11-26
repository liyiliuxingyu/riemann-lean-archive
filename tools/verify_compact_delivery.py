#!/usr/bin/env python3
"""Verify delivered files and their recorded CI inputs without rebuilding Lean.

Python 3.11+, standard library only. Archive anchors check Git tree/blob IDs;
they do not read the large archived bodies. The manifest is not a signature.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile

TARGETS = {
    "riemannHypothesis", "riemannZeta_eq_zero_re",
    "LFunction_ne_zero_of_half_lt_re", "LFunction_eq_zero_re",
    "LFunction_eq_zero_re_of_isPrimitive",
}
AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
STAGES = (
    "lean-version", "lake-version", "source-integrity", "dependencies",
    "mathlib-cache", "clean-compressed-cache", "expected-statements",
    "interface-auditor", "full-build", "public-interface", "axioms",
    "final-source-integrity", "final-dependency-lock",
)
EXCLUDED_DIRS = {".lake", "verification-output", "__pycache__"}
FIELDS = ("path", "bytes", "sha256", "git_blob_sha1")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative_name(value):
    require(isinstance(value, str), "A manifest path must be a string")
    path = PurePosixPath(value)
    require(bool(path.parts) and not path.is_absolute() and ".." not in path.parts
            and value == path.as_posix() and "\\" not in value and ":" not in value
            and not any(ord(c) < 32 for c in value), "Unsafe relative path: " + repr(value))
    return value


def ordinary_path(root, name, directory=False):
    name = relative_name(name)
    target = root
    for part in PurePosixPath(name).parts:
        target = target / part
        require(not stat.S_ISLNK(target.lstat().st_mode), "Symlink is not allowed: " + name)
    mode = target.stat().st_mode
    require(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode),
            "Not an ordinary " + ("directory: " if directory else "file: ") + name)
    return target


def records(rows, label):
    require(isinstance(rows, list) and rows, label + " must be a nonempty list")
    result = {}
    for row in rows:
        require(isinstance(row, dict), "Invalid record in " + label)
        name = relative_name(row["path"])
        require(name not in result, "Duplicate path in " + label + ": " + name)
        require(type(row["bytes"]) is int and row["bytes"] >= 0, "Invalid size: " + name)
        for field, length in (("sha256", 64), ("git_blob_sha1", 40)):
            require(isinstance(row[field], str) and
                    re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", row[field]),
                    "Invalid " + field + ": " + name)
        result[name] = {field: row[field] for field in FIELDS}
    return result


def check_file(root, row):
    raw = ordinary_path(root, row["path"]).read_bytes()
    require(len(raw) == row["bytes"], "Size mismatch: " + row["path"])
    require(hashlib.sha256(raw).hexdigest() == row["sha256"],
            "SHA-256 mismatch: " + row["path"])
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(blob == row["git_blob_sha1"], "Git blob mismatch: " + row["path"])


def directory_error(error):
    raise error


def exact_files(root, name):
    directory = ordinary_path(root, name, directory=True)
    found = set()
    for current, dirs, files in os.walk(directory, followlinks=False, onerror=directory_error):
        dirs[:] = [entry for entry in dirs if entry not in EXCLUDED_DIRS]
        files = [entry for entry in files if Path(entry).suffix not in {".pyc", ".pyo"}]
        for entry in dirs + files:
            child = Path(current) / entry
            require(not child.is_symlink(), "Symlink under exact root: " + str(child.relative_to(root)))
        for entry in files:
            path = Path(current) / entry
            relative = path.relative_to(root).as_posix()
            ordinary_path(root, relative)
            found.add(relative)
    return found


def git(root, *arguments):
    result = subprocess.run(["git", "--literal-pathspecs", "-C", str(root), *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"})
    return result.stdout


def check_anchors(root, anchors):
    require(isinstance(anchors, list) and anchors, "git_anchors must be a nonempty list")
    require(Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root,
            "--root must be the Git repository root")
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    names = set()
    for row in anchors:
        name = relative_name(row["path"])
        require(name not in names, "Duplicate Git anchor: " + name)
        names.add(name)
        require(row["object_type"] in {"tree", "blob"}, "Invalid Git anchor object type: " + name)
        require(isinstance(row["git_sha1"], str) and re.fullmatch(r"[0-9a-f]{40}", row["git_sha1"]),
                "Invalid Git anchor SHA: " + name)
        oid = git(root, "rev-parse", "--verify", head + ":" + name).decode().strip()
        entries = git(root, "ls-tree", "-z", "--full-tree", head, "--", name).split(b"\0")
        entries = [entry for entry in entries if entry]
        require(len(entries) == 1, "Missing or ambiguous Git anchor: " + name)
        info, listed_name = entries[0].split(b"\t", 1)
        mode, kind, listed_oid = info.decode().split()
        require(listed_name.decode() == name and kind == row["object_type"]
                and mode != "120000" and oid == listed_oid == row["git_sha1"],
                "Git anchor mismatch: " + name)
    return len(anchors), head


def verify(root, manifest_path):
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    require(manifest["schema"] == "compact-delivery-v1", "Unsupported delivery schema")
    files = records(manifest["files"], "files")
    for row in files.values():
        check_file(root, row)
    roots = manifest["exact_roots"]
    require(isinstance(roots, list) and roots and len(roots) == len(set(roots)), "Invalid exact_roots")
    for name in roots:
        name = relative_name(name)
        expected = {path for path in files if path.startswith(name + "/")}
        actual = exact_files(root, name)
        require(expected == actual, "Exact root mismatch: " + name + "; missing=" +
                repr(sorted(expected - actual)[:10]) + "; extra=" + repr(sorted(actual - expected)[:10]))
    anchor_count, head = check_anchors(root, manifest["git_anchors"])
    ci = manifest["verified_ci"]
    require(isinstance(ci["source_commit"], str) and re.fullmatch(r"[0-9a-f]{40}", ci["source_commit"]),
            "Invalid verified CI commit")
    require(type(ci["run_id"]) is int and ci["run_id"] > 0, "Invalid verified CI run ID")
    inputs = records(ci["inputs"], "verified_ci.inputs")
    prefix = "project/lean/compact/"
    required = {name for name in files if name.startswith((prefix + "src/", prefix + "scripts/"))}
    required |= {prefix + name for name in
                 ("lean-toolchain", "lakefile.toml", "lake-manifest.json", "UPSTREAM.json", "Challenge.lean")}
    required.add(".github/workflows/compact-lean.yml")
    require(required <= inputs.keys(), "CI input coverage is incomplete: " + repr(sorted(required - inputs.keys())))
    for name, row in inputs.items():
        require(files.get(name) == row, "CI input differs from delivered file record: " + name)
    report_name = relative_name(ci["report_path"])
    require(report_name in files, "CI report is absent from the delivery manifest")
    report = json.loads(ordinary_path(root, report_name).read_text())
    require(report["schema"] == "grh-compact-build-validation-v1", "Unexpected CI report schema")
    for flag in ("passed", "full_main_build_passed", "public_interface_check_passed", "axiom_check_passed"):
        require(report.get(flag) is True, "CI acceptance flag is not true: " + flag)
    require(report["source_commit"] == ci["source_commit"] and
            str(report["github_run_id"]) == str(ci["run_id"]), "CI source commit or run ID mismatch")
    stages = report["stages"]
    require(isinstance(stages, list) and tuple(stage["name"] for stage in stages) == STAGES,
            "CI report must contain exactly the thirteen expected stages in order")
    for stage in stages:
        require(stage["status"] == "passed" and type(stage["returncode"]) is int
                and stage["returncode"] == 0, "CI stage did not pass: " + stage["name"])
        log_name = (PurePosixPath(report_name).parent / relative_name(stage["log"])).as_posix()
        require(log_name in files, "CI stage log is absent from the delivery manifest: " + log_name)
    theorems = report["theorem_axioms"]
    require(isinstance(theorems, dict) and set(theorems) == TARGETS, "CI theorem list differs from five exports")
    for name, axioms in theorems.items():
        require(isinstance(axioms, list) and all(isinstance(a, str) for a in axioms)
                and len(axioms) == len(set(axioms)) and set(axioms) <= AXIOMS,
                "Unexpected or repeated axiom in " + name)
    return {"passed": True, "verified_files": len(files), "verified_bytes": sum(r["bytes"] for r in files.values()),
            "exact_roots": roots, "verified_git_anchors": anchor_count,
            "checked_git_commit": head,
            "verified_ci_inputs": len(inputs), "ci_source_commit": ci["source_commit"],
            "ci_run_id": ci["run_id"], "ci_stage_count": len(stages), "theorem_axioms": theorems,
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path("docs/compact-delivery-manifest.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    target = args.manifest if args.manifest.is_absolute() else root / args.manifest
    output, output_allowed = None, False
    try:
        relative = target.relative_to(root).as_posix()
        target = ordinary_path(root, relative)
        if args.output:
            output = args.output.resolve()
            listed = json.loads(target.read_text()).get("files", [])
            protected = {target, Path(__file__).resolve()} | {root / row["path"] for row in listed}
            require(output not in protected, "Report output would overwrite an input file")
            output_allowed = True
        result = verify(root, target)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        result = {"passed": False, "error": str(error)}
    result.update(schema="compact-delivery-check-v1",
                  checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scope="File hashes, exact delivered file sets, Git object anchors and recorded CI acceptance only. No new Lean build, archived-body read, independent kernel replay or mathematical peer review.")
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output_allowed:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as stream:
                stream.write(serialized)
            try:
                os.replace(stream.name, output)
            finally:
                Path(stream.name).unlink(missing_ok=True)
        except OSError as error:
            result.update(passed=False, output_error=str(error))
            serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(serialized, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
