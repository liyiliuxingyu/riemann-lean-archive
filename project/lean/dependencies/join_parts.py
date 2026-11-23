#!/usr/bin/env python3
"""Reassemble the original JSONL bytes using only the Python standard library.

Every part and the complete output are verified against manifest.json. Existing
matching output is accepted; an existing different file is never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

CHUNK_BYTES = 1024 * 1024


def nonnegative_integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f'{label} must be a nonnegative integer')
    return value


def digest_string(value, label):
    if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError(f'{label} must be a lowercase SHA-256 digest')
    return value


def filename(value, label):
    if (not isinstance(value, str) or not value or value in {'.', '..'}
            or '/' in value or '\\' in value or '\x00' in value or ':' in value):
        raise ValueError(f'{label} must be a single relative filename')
    return value


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('format') != 'jsonl-byte-parts-v1':
        raise ValueError('Unsupported manifest format')
    limit = nonnegative_integer(manifest['maximum_part_bytes'], 'maximum_part_bytes')
    if limit == 0:
        raise ValueError('maximum_part_bytes must be positive')
    original = manifest['original']
    filename(original['file'], 'original.file')
    nonnegative_integer(original['bytes'], 'original.bytes')
    nonnegative_integer(original['line_count'], 'original.line_count')
    digest_string(original['sha256'], 'original.sha256')
    if type(original['ends_with_newline']) is not bool:
        raise ValueError('original.ends_with_newline must be boolean')
    parts = manifest['parts']
    if not isinstance(parts, list) or not parts:
        raise ValueError('The manifest must contain at least one part')
    if manifest.get('part_count') != len(parts):
        raise ValueError('part_count does not match the parts list')
    next_offset, next_line = 0, 1
    seen = set()
    for number, part in enumerate(parts, 1):
        name = filename(part['file'], 'part.file')
        if name in seen:
            raise ValueError(f'Duplicate part filename: {name}')
        seen.add(name)
        size = nonnegative_integer(part['bytes'], 'part.bytes')
        lines = nonnegative_integer(part['line_count'], 'part.line_count')
        digest_string(part['sha256'], 'part.sha256')
        if part['number'] != number:
            raise ValueError(f'Invalid part number: {name}')
        if not 0 < size <= limit or lines == 0:
            raise ValueError(f'Invalid part size or line count: {name}')
        if (part['start_byte'] != next_offset
                or part['end_byte_exclusive'] != next_offset + size
                or part['first_line'] != next_line
                or part['last_line'] != next_line + lines - 1):
            raise ValueError(f'Noncontiguous offsets or line numbers: {name}')
        if type(part['ends_with_newline']) is not bool:
            raise ValueError(f'Invalid newline metadata: {name}')
        if number < len(parts) and not part['ends_with_newline']:
            raise ValueError(f'A nonfinal part does not end at a line boundary: {name}')
        next_offset += size
        next_line += lines
    if next_offset != original['bytes'] or next_line - 1 != original['line_count']:
        raise ValueError('Part totals do not match the original metadata')
    if parts[-1]['ends_with_newline'] != original['ends_with_newline']:
        raise ValueError('Final newline metadata does not match the original')
    return manifest


def file_digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Expected a regular file: {path}')
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(CHUNK_BYTES), b''):
            h.update(block)
            size += len(block)
    return size, h.hexdigest()


def existing_output_matches(output, original):
    if not output.exists() and not output.is_symlink():
        return False
    size, digest = file_digest(output)
    if size != original['bytes'] or digest != original['sha256']:
        raise FileExistsError(f'Refusing to overwrite an existing different file: {output}')
    return True


def reassemble(manifest_path, output):
    manifest = load_manifest(manifest_path)
    original = manifest['original']
    if output is None:
        output = manifest_path.parent.parent / original['file']
    output = Path(output).absolute()
    if existing_output_matches(output, original):
        return {'status': 'existing_file_verified', 'output': str(output),
                'bytes': original['bytes'], 'sha256': original['sha256']}

    source_dir = manifest_path.parent
    for part in manifest['parts']:
        source = source_dir / part['file']
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'Missing or nonregular part: {part["file"]}')
        if source.stat().st_size != part['bytes']:
            raise ValueError(f'Part size mismatch: {part["file"]}')

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    global_hash = hashlib.sha256()
    total_bytes = 0
    total_lines = 0
    final_byte = b''
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=output.parent,
                                         prefix=f'.{output.name}.', suffix='.tmp',
                                         delete=False) as destination:
            temporary_path = Path(destination.name)
            for part in manifest['parts']:
                part_hash = hashlib.sha256()
                part_bytes = 0
                newlines = 0
                last_byte = b''
                with (source_dir / part['file']).open('rb') as source:
                    for block in iter(lambda: source.read(CHUNK_BYTES), b''):
                        destination.write(block)
                        part_hash.update(block)
                        global_hash.update(block)
                        part_bytes += len(block)
                        newlines += block.count(b'\n')
                        last_byte = block[-1:]
                ends_with_newline = last_byte == b'\n'
                lines = newlines + int(part_bytes > 0 and not ends_with_newline)
                if (part_bytes != part['bytes'] or part_hash.hexdigest() != part['sha256']
                        or lines != part['line_count']
                        or ends_with_newline != part['ends_with_newline']):
                    raise ValueError(f'Part content verification failed: {part["file"]}')
                total_bytes += part_bytes
                total_lines += lines
                final_byte = last_byte
            if (total_bytes != original['bytes'] or global_hash.hexdigest() != original['sha256']
                    or total_lines != original['line_count']
                    or (final_byte == b'\n') != original['ends_with_newline']):
                raise ValueError('Complete output verification failed')
            destination.flush()
            os.fsync(destination.fileno())

        # A hard link installs the verified file atomically and cannot overwrite
        # a destination that appeared while reconstruction was in progress.
        try:
            os.link(temporary_path, output)
        except FileExistsError:
            if existing_output_matches(output, original):
                return {'status': 'existing_file_verified', 'output': str(output),
                        'bytes': original['bytes'], 'sha256': original['sha256']}
            raise
        return {'status': 'reassembled_and_verified', 'output': str(output),
                'bytes': total_bytes, 'line_count': total_lines,
                'sha256': global_hash.hexdigest(), 'part_count': len(manifest['parts'])}
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path,
                        default=Path(__file__).resolve().with_name('manifest.json'))
    parser.add_argument('-o', '--output', type=Path,
                        help='Output path; defaults to the original filename in the parent directory')
    args = parser.parse_args()
    try:
        result = reassemble(args.manifest.absolute(), args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
