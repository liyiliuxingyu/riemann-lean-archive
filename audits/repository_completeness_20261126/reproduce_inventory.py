#!/usr/bin/env python3
"""Reproduce the saved inventory snapshot; never query live GitHub or large blobs.

The pinned historical Git tree must already exist locally. Git lazy fetching and
all transport protocols are disabled for this script's read-only Git commands.
The output must be explicitly selected and must not overwrite an existing file.
"""
from pathlib import Path
import argparse
import collections
import datetime
import hashlib
import json
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
DATA = {}
GIT_ENV = {}
ERRORS = []
INPUT_SHA256 = {
    'inventory_inputs.json': '242809d9374c8919d26233beb8634b69451481c8fe89c30d8cab73a505ad5869',
    'toolkit_delivery_manifest.json': 'a74c8a04bdd9adf98f9efb6aee16d9076dd2a82a1af63e2e775878893fcc0bd7',
    'dependency_manifest.json': '15a7a5a488013cd28a9486bb7e67e6f07b160a0490faef8b0343c5e5b181aeab',
    'candidate_audits_tree.json': '95a1eb86022288e6645c778268b34ccd910303bed7153354c66cec18a9cc20d3',
}


def git_bytes(*args):
    result = subprocess.run(['git', '-c', 'protocol.allow=never', *args], cwd=REPO,
                            env=GIT_ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(
            'Cannot read required local Git metadata. Check --repository and explicitly '
            'fetch the historical snapshot before retrying: git fetch --filter=blob:none '
            '--depth=1 origin ' + DATA['candidate_commit'] +
            '. This script does not fetch missing objects.')
    return result.stdout


def require(condition, message):
    if not condition:
        ERRORS.append(message)


def index(tree, prefix=''):
    require(tree.get('truncated') is False, 'Truncated tree: ' + str(tree.get('sha')))
    return {prefix + row['path']: row for row in tree['tree']}


def same_rows(before, after, omit=()):
    a, b = index(before), index(after)
    for name, row in a.items():
        if name not in omit:
            require(name in b and (row['sha'], row['type'], row['mode']) ==
                    (b[name]['sha'], b[name]['type'], b[name]['mode']), 'Changed or missing preserved entry: ' + name)


def main():
    global REPO, DATA, GIT_ENV
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=REPO,
                        help='Git repository root (default: this script\'s repository root)')
    parser.add_argument('--output', type=Path, required=True,
                        help='New JSON output path, for example /tmp/grh-inventory-reproduced.json')
    args = parser.parse_args()
    REPO = args.repository.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output == (HERE / 'inventory_report.json').resolve():
        parser.error('The original inventory_report.json is protected; select a different output path.')
    if output.exists():
        parser.error('Refusing to overwrite an existing output file; select a new path.')
    for name, expected in INPUT_SHA256.items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Saved input snapshot hash mismatch: ' + name)
    DATA = json.loads((HERE / 'inventory_inputs.json').read_text(encoding='utf-8'))
    GIT_ENV = os.environ.copy()
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        GIT_ENV.pop(key, None)
    GIT_ENV.update(GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
                   GIT_OPTIONAL_LOCKS='0', GIT_ALLOW_PROTOCOL='')
    annotree = index(DATA['annotation_tree'], 'annotations/')
    mainroot, newroot = index(DATA['main_root']), index(DATA['candidate_root'])
    require(mainroot['annotations']['sha'] == newroot['annotations']['sha'] == DATA['annotation_tree']['sha'],
            'Annotation tree changed')
    require(mainroot['solution_annotation_toolkit']['sha'] == newroot['solution_annotation_toolkit']['sha'] == DATA['toolkit_tree']['sha'],
            'Annotation toolkit tree changed')
    manifests = DATA['annotation_manifests']
    require(len(manifests) == 57, 'Expected 57 manifests')
    src = {x['file']: x for x in DATA['source_annotation_inventory']['parts']}
    source_parts = {x['file']: x for x in DATA['release_part_inventory']['parts']}
    toolkit = json.loads((HERE / 'toolkit_delivery_manifest.json').read_text(encoding='utf-8'))
    toolkit_parts = {x['file']: x for x in toolkit['parts']}
    previous = {x['part']: x for x in DATA['prior_annotation_verification']['volumes']}
    progress = {x['part']: x for x in DATA['annotation_progress']['completed_parts']}
    require(DATA['annotation_progress']['status'] == 'complete', 'Annotation progress is not complete')
    wanted_paths = set()
    volumes = []
    line_cursor = 1
    total_bytes = total_records = total_original_bytes = total_compressed_bytes = 0
    for part in range(1, 58):
        manifest_path = f'annotations/unpacked/part{part:03d}/manifest.json'
        fetched = manifests[manifest_path]
        m = fetched['data']
        require(annotree[manifest_path]['sha'] == fetched['sha'] == previous[part]['manifest_git_blob_sha1'],
                f'Manifest Git blob mismatch: {part}')
        require(m['status'] == 'complete' and m['part'] == part, f'Manifest not complete: {part}')
        require(m['source']['first_line'] == line_cursor, f'Volume line gap: {part}')
        source_file = m['source']['file']
        for field in ('first_line', 'last_line', 'records', 'original_bytes', 'original_sha256',
                      'annotated_bytes', 'compressed_bytes', 'compressed_sha256'):
            values = [m['source'][field], src[source_file][field], source_parts[source_file][field], toolkit_parts[source_file][field]]
            require(len(set(values)) == 1, f'Source inventory disagreement: {part}/{field}')
        byte_cursor = 0
        chunk_line_cursor = line_cursor
        for number, chunk in enumerate(m['chunks'], 1):
            path = chunk['path']
            require(path == f'annotations/unpacked/part{part:03d}/chunk{number:04d}.txt', f'Unexpected chunk path: {path}')
            require(path not in wanted_paths, f'Duplicate chunk path: {path}')
            wanted_paths.add(path)
            actual = annotree.get(path)
            require(actual is not None, f'Missing chunk: {path}')
            if actual:
                require(actual['type'] == 'blob' and actual['mode'] == '100644', f'Non-ordinary chunk: {path}')
                require(actual['sha'] == chunk['git_blob_sha1'] and actual['size'] == chunk['bytes'], f'Chunk metadata mismatch: {path}')
            require(chunk['first_line'] == chunk_line_cursor, f'Chunk line gap: {path}')
            require(chunk['last_line'] - chunk['first_line'] + 1 == chunk['records'], f'Chunk record count mismatch: {path}')
            require(chunk['annotated_start_byte'] == byte_cursor, f'Chunk byte gap: {path}')
            require(chunk['annotated_end_byte_exclusive'] - byte_cursor == chunk['bytes'], f'Chunk byte range mismatch: {path}')
            require(0 < chunk['bytes'] <= m['chunk_max_bytes'] == 50331648, f'Chunk size bound mismatch: {path}')
            chunk_line_cursor = chunk['last_line'] + 1
            byte_cursor = chunk['annotated_end_byte_exclusive']
        actual = m['actual']
        require(len(m['chunks']) == actual['chunks'] == progress[part]['chunks'] == previous[part]['chunks'], f'Chunk total mismatch: {part}')
        require(byte_cursor == actual['annotated_bytes'] == m['source']['annotated_bytes'] == progress[part]['annotated_bytes'], f'Volume byte total mismatch: {part}')
        require(chunk_line_cursor - line_cursor == actual['records'] == m['source']['records'], f'Volume record total mismatch: {part}')
        require(chunk_line_cursor - 1 == actual['last_line'] == m['source']['last_line'], f'Volume end mismatch: {part}')
        require(actual['original_sha256'] == m['source']['original_sha256'] == previous[part]['original_sha256'], f'Prior original digest mismatch: {part}')
        require(actual['annotated_sha256'] == progress[part]['annotated_sha256'] == previous[part]['annotated_sha256'], f'Prior annotated digest mismatch: {part}')
        directory = f'annotations/unpacked/part{part:03d}'
        require(annotree[directory]['sha'] == previous[part]['tree'], f'Volume tree differs from prior verified tree: {part}')
        volumes.append(dict(part=part, manifest=manifest_path, manifest_git_blob_sha1=fetched['sha'],
                            tree_sha1=annotree[directory]['sha'], chunks=len(m['chunks']), bytes=byte_cursor,
                            first_record=line_cursor, last_record=chunk_line_cursor - 1, records=actual['records']))
        total_bytes += byte_cursor
        total_records += actual['records']
        total_original_bytes += actual['original_bytes']
        total_compressed_bytes += m['source']['compressed_bytes']
        line_cursor = chunk_line_cursor
    remote_texts = {p for p in annotree if p.startswith('annotations/unpacked/part') and p.endswith('.txt')}
    require(remote_texts == wanted_paths, 'Remote TXT path set differs from the 57 manifests')
    require(len(wanted_paths) == 3380, 'Expected 3380 TXT files')
    require(total_bytes == 168547118127 == DATA['annotation_progress']['completed_annotated_bytes'], 'Global annotation byte count mismatch')
    require(total_records == 1080769508 == DATA['annotation_progress']['completed_original_records'], 'Global record count mismatch')

    release = DATA['live_release']
    remote_assets = {a['name']: a for a in release['assets']}
    expected_assets = DATA['release_inventory']['assets']
    require(len(remote_assets) == len(expected_assets) == 60, 'Release asset count mismatch')
    release_rows = []
    for expected in expected_assets:
        name = expected['uploaded_name']
        found = remote_assets.get(name)
        require(found is not None, f'Missing Release asset: {name}')
        if found:
            require(found['id'] == expected['asset_id'] and found['size'] == expected['bytes'] and
                    found['digest'] == 'sha256:' + expected['sha256'] and found['state'] == 'uploaded', f'Release metadata mismatch: {name}')
            release_rows.append(found)

    same_rows(DATA['main_project_top'], DATA['candidate_project_top'], omit=('lean',))
    same_rows(DATA['main_lean_top'], DATA['candidate_lean_top'])
    main_lean, new_lean = index(DATA['main_lean_top']), index(DATA['candidate_lean_top'])
    git_head = git_bytes('rev-parse', 'HEAD').decode('ascii').strip()
    # No -l / cat-file: only tree metadata, never large content blobs.
    rows = git_bytes('ls-tree', '-rz', DATA['candidate_commit'] + ':project/lean/original').split(b'\0')
    entries = [r.split(b'\t', 1) for r in rows if r]
    paths = [name.decode('utf-8') for _, name in entries]
    require(len(paths) == len(set(paths)) == 175190, 'Original path count mismatch')
    require(sum(p.startswith('src/') and p.endswith('.lean') for p in paths) == 175187, 'Original Lean count mismatch')
    require(main_lean['original']['sha'] == new_lean['original']['sha'] == 'e517b335d21898fd2506ad538a1e1775c0aaa4e4', 'Original tree changed')
    source_tree = git_bytes('rev-parse', DATA['candidate_commit'] + ':project/lean/original/src').decode('ascii').strip()
    require(source_tree == 'b41b516b1f7baee4d83ced235ecc71fd43c97695', 'Original source tree changed')

    blobs = DATA['project_blobs']
    present, converted = [], []
    conversions = {
        'lean/RH_AllSources.lean': {'kind': 'expanded_source_tree', 'destination': 'project/lean/original/', 'original_retained_in_release': True},
        'lean/RH_AllSources.dependencies.jsonl': {'kind': 'lossless_jsonl_parts', 'destination': 'project/lean/dependencies/', 'parts': 5},
        'third_party/ctex-kit-source.tar.gz': {'kind': 'expanded_archive', 'destination': 'project/third_party/ctex-kit-source/', 'files': 405},
    }
    for member in DATA['original_project_catalog']['files']:
        path = 'project/' + member['project_relative_path']
        found = blobs.get(path)
        if found:
            require(found['size'] == member['bytes'], f'Original project member size mismatch: {path}')
            present.append(dict(path=path, bytes=found['size'], git_blob_sha1=found['sha']))
        else:
            relative = member['project_relative_path']
            require(relative in conversions, f'Unresolved original project member: {path}')
            converted.append(dict(original_path=path, original_bytes=member['bytes'], original_sha256=member['sha256'], **conversions.get(relative, {})))
    require(len(present) == 267 and len(converted) == 3, 'Original ZIP member resolution mismatch')

    expanded = DATA['expanded_inventory']
    audit_tree = json.loads((HERE / 'candidate_audits_tree.json').read_text(encoding='utf-8'))
    all_expansion_blobs = dict(blobs)
    all_expansion_blobs.update({k: v for k, v in index(audit_tree, 'audits/').items() if v['type'] == 'blob'})
    all_expansion_blobs.update({k: v for k, v in index(DATA['toolkit_tree'], 'solution_annotation_toolkit/').items() if v['type'] == 'blob'})
    for f in expanded['files']:
        actual = all_expansion_blobs.get(f['path'])
        require(actual is not None and actual['size'] == f['bytes'] and actual['mode'] == f['mode'], 'Expanded-file mismatch: ' + f['path'])
    require(len(expanded['files']) == expanded['expanded_file_count'] == 643, 'Expanded file count mismatch')

    dep = json.loads((HERE / 'dependency_manifest.json').read_text(encoding='utf-8'))
    deptree = index(DATA['dependency_tree'])
    cursor = lines = 0
    dependency_parts = []
    for part in dep['parts']:
        f = deptree.get(part['file'])
        require(f is not None and f['size'] == part['bytes'], 'Dependency part size mismatch: ' + part['file'])
        require(part['start_byte'] == cursor and part['first_line'] == lines + 1, 'Dependency part gap')
        require(part['end_byte_exclusive'] - cursor == part['bytes'] and part['last_line'] - lines == part['line_count'], 'Dependency range mismatch')
        cursor, lines = part['end_byte_exclusive'], part['last_line']
        dependency_parts.append(dict(path='project/lean/dependencies/' + part['file'], bytes=part['bytes'], git_blob_sha1=f['sha']))
    require(cursor == dep['original']['bytes'] == 214948999 and lines == dep['original']['line_count'] == 909822, 'Dependency totals mismatch')

    issues = [dict(path='ndjson-files.public.json', field='upload_status', observed='pending',
                   scope='historical snapshot only; not a check of the current file',
                   snapshot_commit=DATA['baseline_commit'],
                   recommended='complete; retain the explicit metadata-only scope for this new recheck')]
    report = dict(
        schema='repository-inventory-snapshot-reproduction-v1', repository='liyiliuxingyu/riemann-lean-archive',
        reproduced_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        baseline_commit=DATA['baseline_commit'], candidate_commit=DATA['candidate_commit'],
        local_git_head_observed=git_head, file_presence_and_manifest_consistency_passed=not ERRORS, errors=ERRORS,
        annotation=dict(tree_sha1=DATA['annotation_tree']['sha'], recursive_api_truncated=False,
                        tree_entries=len(annotree), parts=57, txt_files=len(wanted_paths),
                        annotated_bytes=total_bytes, original_records=total_records,
                        original_bytes=total_original_bytes, compressed_bytes=total_compressed_bytes,
                        record_range_contiguous=[1, line_cursor - 1],
                        all_chunk_paths_sizes_modes_git_blob_ids_match=True,
                        manifest_git_blob_ids_unchanged_since_prior_verification=True, volumes=volumes),
        release=dict(id=release['id'], tag=release['tag_name'], assets=len(remote_assets),
                     bytes=sum(x['size'] for x in remote_assets.values()),
                     all_names_ids_sizes_server_sha256_digests_match=True, asset_metadata=release_rows),
        original_source=dict(tree_sha1=main_lean['original']['sha'], source_tree_sha1=source_tree,
                             preserved_between_main_and_candidate=True, files=len(paths), lean_files=175187,
                             configuration_files=3, non_ascii_paths=sum(not p.isascii() for p in paths)),
        project_archive_members=dict(total=270, original_paths_present=267, all_present_sizes_match=True,
                                     converted_members=converted, present_members=present),
        prior_archive_expansions=dict(files_checked=643, all_paths_sizes_modes_match=True,
                                      groups=dict(collections.Counter(x['path'].split('/')[0] for x in expanded['files']))),
        dependency_index=dict(parts=len(dependency_parts), bytes=cursor, records=lines,
                              continuity_and_sizes_match=True, tree_sha1=DATA['dependency_tree']['sha'], files=dependency_parts),
        toolkit=dict(tree_sha1=DATA['toolkit_tree']['sha'], preserved_between_main_and_candidate=True,
                     ordinary_files=sum(x['type'] == 'blob' for x in DATA['toolkit_tree']['tree']),
                     includes_one_new_decompressed_test_fixture=True),
        historical_snapshot_metadata_issues=issues,
        historical_inventory_notes=[
            'project-files.public.json remains the original ZIP member catalogue; its classifications describe initial delivery planning. Nineteen PDF-build evidence files now exist at ordinary Git paths.',
            'docs/release-expansion.json is a dated 2026-11-23 snapshot. Its then-unexpanded annotation status is superseded by annotations/unpacked/progress.json and the 2026-11-25 verification report.',
        ],
        verification_scope=dict(
            saved_historical_remote_metadata_and_manifest_comparison=True,
            live_remote_queries_performed=False,
            fresh_remote_git_metadata_and_manifest_comparison=False,
            fresh_original_source_path_enumeration_without_blob_download=True,
            local_git_tree_enumeration_uses_pinned_historical_commit=True,
            git_lazy_fetch_disabled=True,
            git_transport_protocols_disabled=True,
            all_large_content_bytes_downloaded_or_sha256_recomputed=False,
            release_asset_content_downloaded=False,
            whole_annotation_decompression_repeated=False,
            prior_byte_verification_records_reused_when_git_trees_unchanged=True,
            mathematical_proof_or_compilation_check_performed_by_this_audit=False,
        ),
        evidence=dict(prior_annotation_report='docs/full-annotation-upload-verification-20261125.json',
                      annotation_progress='annotations/unpacked/progress.json',
                      expanded_file_inventory='docs/unpacked-files-20261125.json',
                      original_project_catalog='project-files.public.json',
                      dependency_manifest='project/lean/dependencies/manifest.json',
                      saved_input_snapshot_sha256=INPUT_SHA256,
                      input_snapshot_sha256=hashlib.sha256((HERE/'inventory_inputs.json').read_bytes()).hexdigest()),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(output=str(output), snapshot_reproduction_passed=not ERRORS,
                          errors=ERRORS, live_remote_queries_performed=False,
                          historical_snapshot_metadata_issues=issues), ensure_ascii=False))
    return 0 if not ERRORS else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({'snapshot_reproduction_passed': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
