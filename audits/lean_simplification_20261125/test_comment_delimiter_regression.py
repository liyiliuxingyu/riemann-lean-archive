#!/usr/bin/env python3
"""Reject a duplicate-import deletion that would damage a block-comment boundary."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import verify_import_cleanup as verifier


def main():
    here = Path(__file__).resolve().parent
    before = b"import Lean\nimport Lean/-\n-/\ntheorem body : True := by trivial\n"
    after = b"import Lean\n-/\ntheorem body : True := by trivial\n"
    relative = "project/lean/original/src/Regression.lean"
    with tempfile.TemporaryDirectory(prefix="import-comment-regression-") as directory:
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()

        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout

        git("init", "-q")
        source = repo / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(before)
        git("add", relative)
        git("-c", "user.name=Import Verification Test", "-c", "user.email=import-verification@example.invalid",
            "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Fixture")
        baseline = git("rev-parse", "HEAD").decode().strip()
        source.write_bytes(after)
        row = {"path": relative, "before_sha256": hashlib.sha256(before).hexdigest(),
               "after_sha256": hashlib.sha256(after).hexdigest(), "removed_lines": [2],
               "removed_bytes": len(b"import Lean/-\n")}
        manifest = root / "changes.jsonl"
        manifest.write_text(json.dumps(row) + "\n")
        args = argparse.Namespace(repo=repo, changes=manifest, baseline=baseline, skip_lean_parser=True,
                                  lean="lean", parser=here / "ParseImportJsonl.lean", parser_timeout=30,
                                  output=root / "result.json")
        with contextlib.redirect_stdout(io.StringIO()):
            code = verifier.verify(args)
        report = json.loads(args.output.read_text())
        assert code == 1
        assert report["error"]["code"] == "removed_line_is_not_plain_import"
        assert report["listed_import_cleanup_passed"] is False
    result = {"format": "import-comment-regression-v1",
              "case": "Deleting import Lean/- would leave a closing block-comment token in the body.",
              "rejected": True, "exit_code": code, "error_code": report["error"]["code"],
              "listed_import_cleanup_passed": False, "source_project_full_build_performed": False,
              "temporary_fixture_cleaned": True,
              "verifier_sha256": hashlib.sha256((here / "verify_import_cleanup.py").read_bytes()).hexdigest()}
    (here / "comment_delimiter_regression.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
