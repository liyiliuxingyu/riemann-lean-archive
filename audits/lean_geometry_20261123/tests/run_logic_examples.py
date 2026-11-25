#!/usr/bin/env python3
"""Run two small core-only checks, not the original RH proof."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--lean', required=True, type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parent
results = []
for filename in ['TrueInterfaceLogic.lean', 'InvalidTrueBridge.lean']:
    src = root / filename
    r = subprocess.run([str(a.lean.resolve()), str(src)], capture_output=True, text=True, timeout=30)
    output = r.stdout + r.stderr
    (root / (src.stem + '.log')).write_text(output, encoding='utf-8')
    expected_failure = filename == 'InvalidTrueBridge.lean'
    matches = (r.returncode == 1 and 'Type mismatch' in output) if expected_failure else r.returncode == 0
    results.append({'file': filename, 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
                    'exit_code': r.returncode, 'expected': 'type mismatch' if expected_failure else 'success',
                    'expectation_met': matches, 'output': output})
(root / 'logic_examples_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(r['expectation_met'] for r in results) else 1)
