#!/usr/bin/env python3
"""Verify the SHA256 manifest of this continuation package."""
from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parent
manifest = root / 'SHA256SUMS.txt'
failures = []
count = 0
for line in manifest.read_text(encoding='utf-8').splitlines():
    expected, relative = line.split('  ', 1)
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        failures.append((relative, 'path outside package'))
        continue
    if not path.is_file():
        failures.append((relative, 'missing'))
        continue
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        failures.append((relative, 'SHA256 mismatch'))
    count += 1
if failures:
    for failure in failures:
        print(*failure, sep=': ')
    sys.exit(1)
print(f'All {count} recorded files passed SHA256 verification.')
