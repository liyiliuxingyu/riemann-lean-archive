#!/usr/bin/env python3
"""Small synthetic metadata fixtures; these do not run or validate any Lean proof."""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / "tools/verify_compact_delivery.py"
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("delivery_guard", SCRIPT)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
MAIN = "project/lean/compact/src/Main.lean"
REPORT = "audits/example/validation.json"
MANIFEST = "docs/compact-delivery-manifest.json"


def row(root, name):
    raw = (root / name).read_bytes()
    return dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                git_blob_sha1=hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())


def write(root, name, raw):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def fixture(root):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    write(root, "archive/kept.txt", b"tiny archive fixture\n")
    subprocess.run(["git", "-C", str(root), "add", "archive"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture archive"], check=True)
    prefix = "project/lean/compact/"
    inputs = [MAIN, prefix + "scripts/check.py", ".github/workflows/compact-lean.yml"]
    inputs += [prefix + name for name in
               ("lean-toolchain", "lakefile.toml", "lake-manifest.json", "UPSTREAM.json", "Challenge.lean")]
    for name in inputs:
        write(root, name, b"synthetic fixture only\n")
    logs = []
    for name in GUARD.STAGES:
        target = "audits/example/" + name + ".log"
        write(root, target, ("synthetic stage " + name + "\n").encode())
        logs.append(target)
    report = dict(schema="grh-compact-build-validation-v1", passed=True,
                  source_commit="c01eb3d7b21c4884b6c31b492f85635d4cd0669c", github_run_id="45758680116",
                  full_main_build_passed=True, public_interface_check_passed=True, axiom_check_passed=True,
                  stages=[dict(name=n, status="passed", returncode=0, log=n + ".log") for n in GUARD.STAGES],
                  theorem_axioms={name: sorted(GUARD.AXIOMS) for name in GUARD.TARGETS})
    write(root, REPORT, (json.dumps(report) + "\n").encode())
    anchor = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD:archive"], text=True).strip()
    manifest = dict(schema="compact-delivery-v1", files=[row(root, n) for n in inputs + logs + [REPORT]],
                    exact_roots=["project/lean/compact"],
                    git_anchors=[dict(path="archive", object_type="tree", git_sha1=anchor)],
                    verified_ci=dict(source_commit=report["source_commit"], run_id=45758680116,
                                     report_path=REPORT, inputs=[row(root, n) for n in inputs]))
    return manifest, report


def refresh_report(root, manifest, report):
    write(root, REPORT, (json.dumps(report) + "\n").encode())
    manifest["files"] = [row(root, REPORT) if r["path"] == REPORT else r for r in manifest["files"]]


def run_case(name, mutation, expected, phrase=None, extra_args=()):
    with tempfile.TemporaryDirectory(prefix="compact-integrity-fixture-") as temporary:
        root = Path(temporary)
        manifest, report = fixture(root)
        mutation(root, manifest, report)
        write(root, MANIFEST, (json.dumps(manifest) + "\n").encode())
        before = (root / MANIFEST).read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *extra_args],
                                text=True, capture_output=True, cwd=root)
        payload = json.loads(result.stdout)
        accepted = result.returncode == 0 and payload.get("passed") is True
        assert accepted == expected, (name, result.returncode, payload, result.stderr)
        if not expected:
            assert result.returncode != 0 and payload.get("passed") is False
        if phrase:
            assert phrase in payload.get("error", ""), (name, payload)
        assert (root / MANIFEST).read_bytes() == before, "Verifier overwrote manifest"
        return dict(case=name, expected_accept=expected, returncode=result.returncode,
                    observed_accept=accepted, error=payload.get("error"), passed=True)


def change_flag(root, manifest, report):
    report["passed"] = False
    refresh_report(root, manifest, report)


def bad_stage(root, manifest, report):
    report["stages"][8]["returncode"] = 1
    refresh_report(root, manifest, report)


def bad_axiom(root, manifest, report):
    report["theorem_axioms"]["riemannHypothesis"].append("Fixture.extraAxiom")
    refresh_report(root, manifest, report)


def symlink(root, manifest, report):
    (root / MAIN).unlink()
    (root / MAIN).symlink_to(root / "archive/kept.txt")


CASES = [
    ("baseline", lambda r, m, p: None, True, None),
    ("sparse_archive_body_not_read", lambda r, m, p: shutil.rmtree(r / "archive"), True, None),
    ("ignored_cache", lambda r, m, p: write(r, "project/lean/compact/.lake/cache.bin", b"cache"), True, None),
    ("missing_file", lambda r, m, p: (r / MAIN).unlink(), False, "Main.lean"),
    ("same_size_changed_file", lambda r, m, p: write(r, MAIN, b"S" + (r / MAIN).read_bytes()[1:]), False, "SHA-256 mismatch"),
    ("extra_source", lambda r, m, p: write(r, "project/lean/compact/src/Extra.lean", b"extra"), False, "Exact root mismatch"),
    ("ci_passed_false", change_flag, False, "CI acceptance flag is not true"),
    ("ci_input_hash_differs", lambda r, m, p: m["verified_ci"]["inputs"][0].update(sha256="0" * 64), False, "CI input differs"),
    ("ci_input_omitted", lambda r, m, p: m["verified_ci"]["inputs"].pop(0), False, "CI input coverage is incomplete"),
    ("wrong_anchor", lambda r, m, p: m["git_anchors"][0].update(git_sha1="0" * 40), False, "Git anchor mismatch"),
    ("duplicate_record", lambda r, m, p: m["files"].append(copy.deepcopy(m["files"][0])), False, "Duplicate path"),
    ("path_traversal", lambda r, m, p: m["files"][0].update(path="../outside.txt"), False, "Unsafe relative path"),
    ("windows_drive_path", lambda r, m, p: m["files"][0].update(path="C:/outside.txt"), False, "Unsafe relative path"),
    ("source_symlink", symlink, False, "Symlink is not allowed"),
    ("failed_stage_under_passed_flag", bad_stage, False, "CI stage did not pass"),
    ("extra_axiom", bad_axiom, False, "Unexpected or repeated axiom"),
    ("output_must_not_replace_manifest", lambda r, m, p: None, False, "Report output would overwrite", ("--output", MANIFEST)),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New report path; existing files are never overwritten")
    args = parser.parse_args()
    output = (args.output.resolve() if args.output else
              Path(tempfile.mkdtemp(prefix="compact-integrity-report-")) / "integrity_guard_cases.json")
    if output == (HERE / "integrity_guard_cases.json").resolve():
        parser.error("The published integrity_guard_cases.json is immutable; choose another output path")
    if output.exists():
        parser.error("Output already exists; choose a new output path")
    results = [run_case(*case) for case in CASES]
    report = dict(schema="compact-delivery-verifier-fixtures-v1", passed=True,
                  checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope="Synthetic small Git repositories and fabricated CI metadata only; no Lean build, original archive read or mathematical validation. Windows-style paths are checked synthetically; this run is not a Windows execution test.",
                  verifier_sha256=hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                  fixture_suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), cases=results)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(passed=True, cases=len(results), verifier_sha256=report["verifier_sha256"],
                         fixture_suite_sha256=report["fixture_suite_sha256"], output=str(output))))


if __name__ == "__main__":
    main()
