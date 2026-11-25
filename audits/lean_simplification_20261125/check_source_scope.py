#!/usr/bin/env python3
"""Verify the complete source-tree change set against an explicit manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASELINE='b32465bf0a42b702d7834fbb5f983fe413fa5aa6'
PREFIX='project/lean/original/src/'


def git(repo,*args):
    return subprocess.check_output(['git','-c','core.hooksPath=/dev/null',*args],cwd=repo)


def verify(repo,changes,extra=None):
    entries=[json.loads(line) for line in changes.read_text().splitlines() if line.strip()]
    expected={entry['path']:entry['after_sha256'] for entry in entries}
    allowed_additions=set()
    if extra:
        for entry in json.loads(extra.read_text())['files']:
            path=entry['path']
            if path in expected:
                raise ValueError('Additional proof edits overlap the import-only manifest')
            expected[path]=entry['after_sha256']
            if entry.get('before_sha256') is None:
                allowed_additions.add(path)
    for path in expected:
        p=Path(path)
        if not path.startswith(PREFIX) or not path.endswith('.lean') or p.is_absolute() or '..' in p.parts:
            raise ValueError('Unsafe or out-of-scope manifest path')
    raw=git(repo,'diff','--raw','--no-renames','-z',BASELINE,'--',PREFIX).split(b'\0')
    statuses={}
    tracked_additions=set()
    for index in range(0,len(raw)-1,2):
        header,path=raw[index].decode(),raw[index+1].decode()
        modes=header[1:].split()
        old_mode,new_mode,old_oid,new_oid,status=modes
        if status=='A' and path in allowed_additions and old_mode=='000000' and new_mode=='100644':
            tracked_additions.add(path)
        elif old_mode!='100644' or new_mode!='100644' or status!='M':
            raise ValueError('Unexpected source deletion, addition, type or mode change: '+path)
        statuses[path]=status
    untracked={x.decode() for x in git(repo,'ls-files','--others','-z','--',PREFIX).split(b'\0') if x}
    if untracked!=allowed_additions-tracked_additions:
        raise ValueError('Untracked source set does not match reviewed new modules')
    if set(statuses)|untracked!=set(expected):
        raise ValueError('Complete source difference set does not match reviewed manifests')
    digest=hashlib.sha256()
    for relative in sorted(expected):
        path=repo/relative
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o111:
            raise ValueError('Source is not an ordinary nonexecutable file: '+relative)
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=expected[relative]:
            raise ValueError('Final source hash mismatch: '+relative)
        digest.update((relative+'\0'+actual+'\n').encode())
    for name in ('lean-toolchain','lakefile.toml','lake-manifest.json'):
        relative='project/lean/original/'+name
        if git(repo,'show',BASELINE+':'+relative)!=(repo/relative).read_bytes():
            raise ValueError('Pinned build configuration changed: '+relative)
    return {'format':'lean-source-change-scope-v1','baseline_commit':BASELINE,
            'source_directory':PREFIX.rstrip('/'),'modified_source_files':sum(value=='M' for value in statuses.values()),
            'added_source_files':sorted(allowed_additions),'deleted_source_files':[],
            'all_and_only_reviewed_source_files_changed':True,'all_final_source_hashes_match':True,
            'all_source_file_modes_preserved':True,'all_three_build_configurations_unchanged':True,
            'final_changed_source_path_hash_pairs_sha256':digest.hexdigest(),
            'scope':'Checks the complete tracked/untracked source difference set and final file hashes; does not elaborate declarations or perform a whole-project build.',
            'passed':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--changes',type=Path,required=True)
    parser.add_argument('--extra',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=verify(args.repo.resolve(),args.changes,args.extra)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
