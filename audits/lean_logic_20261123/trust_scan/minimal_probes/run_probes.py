#!/usr/bin/env python3
"""Run small trust-boundary probes, checking kernel rejection, not just exit 1."""
import argparse
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument("--lean", type=Path, required=True)
p.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
a = p.parse_args()
results = []
for f in sorted(a.directory.glob("*.lean")):
    start = time.monotonic()
    result = subprocess.run([str(a.lean.resolve()), str(f.resolve())], capture_output=True, text=True, timeout=45)
    output = result.stdout + result.stderr
    (a.directory / (f.stem + ".log")).write_text(output, encoding="utf-8")
    negative = "Negative" in f.stem
    matched = (result.returncode == 1 and "(kernel) declaration type mismatch" in output
               and "unexpected identifier" not in output and "has not been implemented" not in output) if negative else result.returncode == 0
    results.append({"file": f.name,
                    "expected_result": "kernel_type_mismatch" if negative else "success",
                    "actual_exit_code": result.returncode,
                    "expectation_met": matched,
                    "duration_seconds": round(time.monotonic() - start, 3),
                    "output": output})
(a.directory / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(x["expectation_met"] for x in results) else 1)
