#!/usr/bin/env python3
"""Reassemble the fourteen original volumes and safely inspect/extract the archive.

This program does not execute Lean code and does not establish theorem correctness.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import shutil
import tarfile
import time

EXPECTED_SHA256 = '9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc'
EXPECTED_BYTES = 239275554

def sha256_file(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parts-dir',type=Path)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    started=time.time()
    report={'status':'in_progress','executes_lean':False,'parts':[]}
    if args.parts_dir:
        parts=[args.parts_dir/f'lean.tar.gz.part{i:02d}' for i in range(1,15)]
        missing=[str(p) for p in parts if not p.is_file()]
        if missing:
            raise FileNotFoundError(f'Missing parts: {missing}')
        args.archive.parent.mkdir(parents=True,exist_ok=True)
        temporary=args.archive.with_suffix(args.archive.suffix+'.assembling')
        with temporary.open('wb') as destination:
            for i,part in enumerate(parts,1):
                digest=sha256_file(part)
                report['parts'].append({'part':i,'filename':part.name,'bytes':part.stat().st_size,'sha256':digest})
                with part.open('rb') as source:
                    shutil.copyfileobj(source,destination,1024*1024)
        temporary.replace(args.archive)
    actual_size=args.archive.stat().st_size
    actual_sha=sha256_file(args.archive)
    report['archive']={'path':str(args.archive.resolve()),'bytes':actual_size,'sha256':actual_sha}
    if actual_size!=EXPECTED_BYTES or actual_sha!=EXPECTED_SHA256:
        report['status']='unexpected_archive'
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        raise RuntimeError('Archive differs from the prior verified source; stop before extraction.')
    args.destination.mkdir(parents=True,exist_ok=True)
    destination=args.destination.resolve()
    seen=set()
    totals={'members':0,'directories':0,'regular_files':0,'file_bytes':0,'lean_files':0,'lean_physical_lines':0,'lean_bytes':0}
    with tarfile.open(args.archive,'r:gz') as archive:
        members=archive.getmembers()
        for member in members:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise RuntimeError(f'Unsafe member path: {member.name}')
            normalized=path.as_posix()
            if normalized in seen:
                raise RuntimeError(f'Duplicate archive member: {member.name}')
            seen.add(normalized)
            if not(member.isdir() or member.isfile()):
                raise RuntimeError(f'Unsupported member type: {member.name}')
        for member in members:
            totals['members']+=1
            target=destination/member.name
            if not target.resolve().is_relative_to(destination):
                raise RuntimeError(f'Unsafe output path: {member.name}')
            if member.isdir():
                target.mkdir(parents=True,exist_ok=True)
                totals['directories']+=1
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            reader=archive.extractfile(member)
            if reader is None:
                raise RuntimeError(f'No file bytes: {member.name}')
            with reader, target.open('wb') as writer:
                shutil.copyfileobj(reader,writer,1024*1024)
            if target.stat().st_size!=member.size:
                raise RuntimeError(f'Size mismatch: {member.name}')
            totals['regular_files']+=1
            totals['file_bytes']+=member.size
            if target.suffix=='.lean':
                data=target.read_bytes()
                totals['lean_files']+=1
                totals['lean_bytes']+=len(data)
                totals['lean_physical_lines']+=data.count(b'\n')+(bool(data) and not data.endswith(b'\n'))
    report['counts']=totals
    report['status']='verified_and_extracted'
    report['destination']=str(destination)
    report['elapsed_seconds']=round(time.time()-started,3)
    report['safety']={'all_paths_relative':True,'no_parent_components':True,'no_duplicate_members':True,'regular_files_and_directories_only':True}
    report['formal_compilation_performed']=False
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'archive':report['archive'],'counts':totals,'destination':str(destination)},ensure_ascii=False))

if __name__=='__main__':
    main()
