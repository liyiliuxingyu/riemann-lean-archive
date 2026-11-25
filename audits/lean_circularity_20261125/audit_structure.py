#!/usr/bin/env python3
"""Audit source identity, module cycles and explicit trust-related source tokens.

This does not construct an elaborated declaration dependency graph or check the
whole mathematical proof. Source files are read only. External packages are not
recursively audited. Header and lexical helpers are conservative source scanners.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True

import lexical_helpers as lexical


def load_header_helper(repo):
    path = repo / 'audits/lean_simplification_20261125/audit_imports.py'
    spec = importlib.util.spec_from_file_location('circularity_import_helper', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=repo)


def run(repo, output, commit):
    started = time.monotonic()
    prefix = 'project/lean/original/src/'
    output.mkdir(parents=True, exist_ok=True)
    header, header_sha = load_header_helper(repo)
    tree = git(repo, 'ls-tree', '-rz', '--full-tree', commit, '--', prefix)
    entries = []
    for record in tree.split(b'\0'):
        if not record:
            continue
        properties, raw_path = record.split(b'\t', 1)
        mode, kind, oid = properties.split()
        path = raw_path.decode('utf-8')
        if path.endswith('.lean'):
            if mode != b'100644' or kind != b'blob':
                raise ValueError('Unexpected source object kind or mode: ' + path)
            entries.append((path, oid.decode()))
    entries.sort()
    actual_paths = {p.relative_to(repo).as_posix() for p in (repo / prefix).rglob('*.lean')}
    if actual_paths != {path for path, _ in entries}:
        raise ValueError('Current source inventory differs from the fixed commit')
    names = ['.'.join(header.quote_component(part) for part in Path(path[len(prefix):]).with_suffix('').parts)
             for path, _ in entries]
    ids = {name: index for index, name in enumerate(names)}
    if len(ids) != len(names):
        raise ValueError('Duplicate module identity')
    adjacency = [[] for _ in names]
    raw_counts = Counter()
    clean_counts = Counter()
    keywords = sorted(set(lexical.KEYWORDS) | {'mutual'})
    pattern = re.compile(rb"(?<![A-Za-z0-9_'])\b(?:" + b'|'.join(re.escape(k.encode()) for k in sorted(keywords, key=len, reverse=True)) + rb")\b(?![A-Za-z0-9_'])")
    matches, strings, warnings, errors, unresolved = [], [], [], [], []
    external = set()
    source_digest = hashlib.sha256()
    graph_digest = hashlib.sha256()
    total_bytes = total_lines = raw_imports = advanced = 0
    unique_all_edges = 0
    for index, ((relative, oid), module_name) in enumerate(zip(entries, names)):
        path = repo / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('Source is not a regular file: ' + relative)
        data = path.read_bytes()
        actual_oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual_oid != oid:
            raise ValueError('Source content differs from the audited commit: ' + relative)
        source_sha = hashlib.sha256(data).hexdigest()
        source_digest.update((relative + '\0' + source_sha + '\n').encode())
        total_bytes += len(data)
        total_lines += len(data.splitlines())
        try:
            parsed = header.parse_header(data.decode('utf-8'))
            advanced += not parsed.ordinary
            raw_imports += len(parsed.imports)
            deps = sorted({item.target for item in parsed.imports})
            unique_all_edges += len(deps)
            for dep in deps:
                graph_digest.update((module_name + '\0' + dep + '\n').encode())
                if dep in ids:
                    adjacency[index].append(ids[dep])
                elif dep.split('.')[0] in {'Mathlib', 'Lean', 'Batteries', 'Init'}:
                    external.add(dep)
                else:
                    unresolved.append({'module': module_name, 'import': dep})
        except (ValueError, UnicodeError) as error:
            errors.append({'path': relative, 'error': str(error)})
        raw_counts.update(match.group().decode() for match in pattern.finditer(data))
        clean, hidden, lexical_warnings = lexical.masked_source(data)
        for item in hidden:
            strings.append({'path': relative, 'line': data.count(b'\n', 0, item['offset']) + 1, **item})
        for item in lexical_warnings:
            warnings.append({'path': relative, **item})
        for match in pattern.finditer(clean):
            token = match.group().decode()
            clean_counts[token] += 1
            if token == 'set_option':
                continue
            offset = match.start()
            line_start = data.rfind(b'\n', 0, offset) + 1
            line_end = data.find(b'\n', offset)
            if line_end < 0:
                line_end = len(data)
            matches.append({'path': relative, 'sha256': source_sha,
                            'line': data.count(b'\n', 0, offset) + 1,
                            'token': token, 'code_line': data[line_start:line_end].decode('utf-8')})
        if (index + 1) % 25000 == 0:
            print(json.dumps({'modules_scanned': index + 1, 'elapsed_seconds': round(time.monotonic() - started, 2)}), flush=True)
    if errors or unresolved:
        raise ValueError('Module scan has parse errors or unresolved imports')
    order, _ = header.topological_order(adjacency)
    rank = [0] * len(order)
    for place, node in enumerate(order):
        rank[node] = place
    if not all(rank[dep] < rank[user] for user, deps in enumerate(adjacency) for dep in deps):
        raise ValueError('Topological order does not certify every internal edge')
    main_closure = header.closure([ids['Main']], adjacency)
    summary = {
        'format': 'lean-circularity-source-structure-v1',
        'source_commit': commit, 'source_directory': prefix.rstrip('/'),
        'source_files': len(names), 'source_bytes': total_bytes, 'source_lines': total_lines,
        'all_source_blobs_match_fixed_git_commit': True,
        'source_path_sha256_pairs_digest': source_digest.hexdigest(),
        'raw_import_occurrences': raw_imports, 'unique_all_import_edges': unique_all_edges,
        'unique_internal_import_edges': sum(map(len, adjacency)),
        'external_imported_modules': len(external), 'unresolved_imports': len(unresolved),
        'header_parse_errors': len(errors), 'advanced_or_prelude_headers': advanced,
        'module_graph_acyclic': True, 'topological_nodes_processed': len(order),
        'each_internal_edge_respects_topological_order': True,
        'self_import_edges': sum(user in deps for user, deps in enumerate(adjacency)),
        'main_import_closure_internal_modules': len(main_closure),
        'unique_import_edge_sequence_sha256': graph_digest.hexdigest(),
        'topological_module_sequence_sha256': hashlib.sha256(('\n'.join(names[node] for node in order) + '\n').encode()).hexdigest(),
        'raw_token_occurrences': {key: raw_counts[key] for key in keywords},
        'masked_token_occurrences': {key: clean_counts[key] for key in keywords},
        'lexical_warning_count': len(warnings), 'strings_with_selected_keywords': len(strings),
        'header_helper_sha256': header_sha,
        'lexical_helper_sha256': hashlib.sha256(Path(lexical.__file__).read_bytes()).hexdigest(),
        'source_files_modified': False, 'full_project_build_performed': False,
        'elaborated_declaration_dependency_graph_constructed': False,
        'final_theorem_recursive_axioms_recomputed': False,
        'all_semantic_circularity_excluded': False,
        'limits': [
            'No import cycle does not establish the absence of all declaration-level or semantic circularity.',
            'Source token counts do not replace elaboration or recursively checking the final theorem axioms.',
            'External packages are not recursively scanned; quoted syntax and generated declarations require manual interpretation.',
        ],
        'elapsed_seconds': round(time.monotonic() - started, 3),
    }
    for name, payload in [('structure_summary.json', summary), ('trust_token_matches.json', matches),
                          ('lexical_warnings.json', warnings), ('strings_with_keywords.json', strings)]:
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: summary[key] for key in ('source_files', 'source_bytes', 'unique_internal_import_edges', 'module_graph_acyclic', 'lexical_warning_count', 'elapsed_seconds')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', default='a132f8e71629fed5febae6733f31b08171f3183a')
    args = parser.parse_args()
    run(args.repo.resolve(), args.output.resolve(), args.commit)
