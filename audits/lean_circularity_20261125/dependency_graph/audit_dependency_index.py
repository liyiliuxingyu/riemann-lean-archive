#!/usr/bin/env python3
"""Verify the archived module-import graph; this is not a declaration graph."""
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path


def audit(repo):
    depdir = repo / 'project/lean/dependencies'
    manifest = json.loads((depdir / 'manifest.json').read_text())
    modules = {}
    with (repo / 'project/lean/RH_AllSources.index.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['kind'] == 'source':
                assert row['module'] not in modules
                modules[row['module']] = row['lines']
    names = list(modules)
    ids = {name: index for index, name in enumerate(names)}
    outgoing = [set() for _ in names]
    external = set()
    counts = Counter()
    modifiers = Counter()
    complete_sha = hashlib.sha256()
    part_results = []
    self_edges = []
    for part in manifest['parts']:
        sha = hashlib.sha256()
        size = rows = 0
        with (depdir / part['file']).open('rb') as stream:
            for raw in stream:
                sha.update(raw)
                complete_sha.update(raw)
                size += len(raw)
                rows += 1
                row = json.loads(raw)
                assert set(row) == {'source', 'target', 'source_line', 'modifiers', 'in_bundle'}
                source, target = row['source'], row['target']
                assert source in ids
                assert type(row['source_line']) is int and 1 <= row['source_line'] <= modules[source]
                assert type(row['in_bundle']) is bool and row['in_bundle'] == (target in ids)
                counts['records'] += 1
                modifiers[row['modifiers']] += 1
                if row['in_bundle']:
                    counts['internal_import_occurrences'] += 1
                    outgoing[ids[source]].add(ids[target])
                    if source == target:
                        self_edges.append(row)
                else:
                    counts['external_import_occurrences'] += 1
                    external.add(target)
        assert size == part['bytes'] and rows == part['line_count'] and sha.hexdigest() == part['sha256']
        part_results.append({'file': part['file'], 'bytes': size, 'records': rows,
                             'sha256': sha.hexdigest(), 'matches_manifest': True})
    assert complete_sha.hexdigest() == manifest['original']['sha256']
    assert counts['records'] == manifest['original']['line_count']
    incoming = [[] for _ in names]
    remaining = []
    for source, targets in enumerate(outgoing):
        remaining.append(len(targets))
        for target in targets:
            incoming[target].append(source)
    ready = deque(index for index, count in enumerate(remaining) if count == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for dependent in incoming[node]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    unique_edges = sum(map(len, outgoing))
    return {
        'format': 'lean-baseline-module-import-archive-audit-v1',
        'archived_source_baseline_commit': 'b32465bf0a42b702d7834fbb5f983fe413fa5aa6',
        'scope': 'Archived source module header imports only; not theorem/declaration constant dependencies.',
        'module_count': len(names), **counts,
        'unique_internal_import_edges': unique_edges,
        'repeated_internal_import_edges': counts['internal_import_occurrences'] - unique_edges,
        'external_module_count': len(external),
        'import_modifiers_counts': dict(modifiers),
        'all_parts_and_concatenated_sha256_match': True,
        'concatenated_sha256': complete_sha.hexdigest(),
        'parts': part_results,
        'self_import_edges': self_edges,
        'topological_nodes_processed': visited,
        'internal_module_graph_acyclic': visited == len(names),
        'cyclic_or_cycle_dependent_remaining_nodes': sum(count > 0 for count in remaining),
        'declaration_level_cycle_check_performed': False,
        'kernel_type_checking_performed': False,
        'current_simplification_source_graph_rebuilt': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
