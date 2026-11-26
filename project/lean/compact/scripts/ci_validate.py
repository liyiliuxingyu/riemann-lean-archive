#!/usr/bin/env python3
"""Build the pinned compact project and validate its five public exports.

The final passed flag is written only after every stage succeeds. Logs and an
incomplete report remain available on failure. This does not run Comparator or
an independent Lean kernel implementation.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification-output"
TARGETS = (
    "riemannHypothesis", "riemannZeta_eq_zero_re",
    "LFunction_ne_zero_of_half_lt_re", "LFunction_eq_zero_re",
    "LFunction_eq_zero_re_of_isPrimitive",
)
ALLOWED = {"propext", "Classical.choice", "Quot.sound"}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main():
    OUT.mkdir(exist_ok=True)
    report = {
        "schema": "grh-compact-build-validation-v1", "passed": False,
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "upstream_commit": "72fead102f663d5c7a407964a13dc0cf9d977207",
        "mathlib_commit": "56a005855ea17e0b0958f73ec801ae140b0a1679",
        "lean_num_threads": os.environ.get("LEAN_NUM_THREADS"),
        "initial_free_disk_bytes": shutil.disk_usage(ROOT).free,
        "stages": [], "full_main_build_passed": False,
        "public_interface_check_passed": False, "axiom_check_passed": False,
        "independent_kernel_replay_performed": False, "comparator_performed": False,
        "mathematical_peer_review_performed": False,
    }
    def checkpoint():
        report["current_free_disk_bytes"] = shutil.disk_usage(ROOT).free
        write_json(OUT / "validation.json", report)
    def run(name, command):
        item = {"name": name, "command": command, "status": "running"}
        report["stages"].append(item)
        checkpoint()
        print(f"\nSTAGE {name}", flush=True)
        started = time.monotonic()
        log_path = OUT / (name + ".log")
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=ROOT, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)
            code = process.wait()
        item.update(returncode=code, seconds=round(time.monotonic() - started, 3),
                    status="passed" if code == 0 else "failed", log=log_path.name)
        checkpoint()
        if code:
            raise RuntimeError(f"Stage {name} failed with exit code {code}")
        return log_path.read_text()
    try:
        version = run("lean-version", ["lean", "--version"])
        if not re.search(r"\bversion 4\.35\.0\b", version):
            raise RuntimeError("The Lean version is not the pinned 4.35.0")
        report["lean_version"] = version.strip()
        run("lake-version", ["lake", "--version"])
        run("source-integrity", [sys.executable, "scripts/verify_sources.py", "--output", str(OUT / "source-integrity.json")])
        report["upstream_manifest_sha256"] = hashlib.sha256((ROOT / "UPSTREAM.json").read_bytes()).hexdigest()
        run("dependencies", [sys.executable, "scripts/bootstrap_dependencies.py"])
        run("mathlib-cache", ["lake", "exe", "cache", "get"])
        run("clean-compressed-cache", ["lake", "exe", "cache", "clean!"])
        object_dir = ROOT / ".lake/build/lib/lean"
        object_dir.mkdir(parents=True, exist_ok=True)
        run("expected-statements", ["lake", "env", "lean", "--root=scripts", "-o", str(object_dir / "ArchiveExpectedStatements.olean"), "scripts/ArchiveExpectedStatements.lean"])
        run("interface-auditor", ["lake", "env", "lean", "--root=scripts", "-o", str(object_dir / "ArchiveInterfaceAudit.olean"), "scripts/ArchiveInterfaceAudit.lean"])
        run("full-build", ["lake", "build"])
        report["full_main_build_passed"] = True
        interface_log = run("public-interface", ["lake", "env", "lean", "--root=scripts", "scripts/ArchiveInterfaceCheck.lean"])
        for name in TARGETS:
            if len(re.findall(r"INTERFACE_OK " + re.escape(name) + r";", interface_log)) != 1:
                raise RuntimeError("Missing or repeated interface acceptance for " + name)
        report["public_interface_check_passed"] = True
        axiom_log = run("axioms", ["lake", "env", "lean", "scripts/PrintAxioms.lean"])
        entries = re.findall(r"'([^']+)' depends on axioms:\s*\[([^\]]*)\]", axiom_log)
        if len(entries) != len(TARGETS) or {name for name, _ in entries} != set(TARGETS):
            raise RuntimeError("The printed axiom report does not contain exactly the five exports")
        report["theorem_axioms"] = {}
        for name, raw in entries:
            axioms = {value.strip() for value in raw.split(",") if value.strip()}
            if not axioms <= ALLOWED:
                raise RuntimeError("Unexpected axioms in " + name + ": " + repr(sorted(axioms - ALLOWED)))
            report["theorem_axioms"][name] = sorted(axioms)
        report["axiom_check_passed"] = True
        run("final-source-integrity", [sys.executable, "scripts/verify_sources.py", "--output", str(OUT / "final-source-integrity.json")])
        run("final-dependency-lock", [sys.executable, "scripts/bootstrap_dependencies.py", "--check-only"])
        report["passed"] = True
        report["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        checkpoint()
        print(json.dumps({"passed": True, "theorems": report["theorem_axioms"]}), flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = str(error)
        report["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        checkpoint()
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
