#!/usr/bin/env python3
"""Safely extract the public immutable mirror of Alpöge's published Lean sources.

The GitHub tar.gz is a different container from the author's fourteen volumes.
This script checks its fixed commit, counts, source fingerprints, and gzip CRC.
It does not execute or compile Lean.
"""
from pathlib import Path,PurePosixPath
import gzip,hashlib,json,tarfile,time

BASE=Path(__file__).resolve().parent
DEST=BASE.parent/'original'/'lean'
ARCHIVE=BASE/'original_commit_source.tar.gz'
COMMIT='40e56bab026552e089d7afcfeff08d2defb9c005'
PREFIX='riemann-hypothesis-'+COMMIT
EXPECTED={'lean_files':175187,'lean_bytes':1030531854,'lean_physical_lines':17374215}
EXPECTED_ARCHIVE_SHA='64399e32d8dbce44d186c2f4ca5ee2a428e66b77d0c0b8a63ce0f8e5f0f8d192'

def main():
    started=time.time()
    with ARCHIVE.open('rb') as f:
        actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=EXPECTED_ARCHIVE_SHA:
        raise RuntimeError('The downloaded mirror archive has changed.')
    DEST.mkdir(parents=True,exist_ok=True)
    root=DEST.resolve();seen=set()
    counts={'members':0,'directories':0,'regular_files':0,'file_bytes':0,'lean_files':0,'lean_bytes':0,'lean_physical_lines':0}
    source_index=BASE/'all_source_files.jsonl'
    with source_index.open('w',encoding='utf-8') as index,gzip.open(ARCHIVE,'rb') as stream:
        with tarfile.open(fileobj=stream,mode='r|') as tar:
            for member in tar:
                parts=PurePosixPath(member.name).parts
                if not parts or parts[0]!=PREFIX or '..' in parts or PurePosixPath(member.name).is_absolute():
                    raise RuntimeError('Unsafe or unexpected path: '+member.name)
                relative=PurePosixPath(*parts[1:])
                normalized=relative.as_posix()
                if normalized in seen:
                    raise RuntimeError('Duplicate member: '+normalized)
                seen.add(normalized)
                if not(member.isdir() or member.isfile()):
                    raise RuntimeError('Unsupported member type: '+member.name)
                target=root/relative
                if not target.resolve().is_relative_to(root):
                    raise RuntimeError('Output would escape destination.')
                counts['members']+=1
                if member.isdir():
                    target.mkdir(parents=True,exist_ok=True);counts['directories']+=1
                    continue
                target.parent.mkdir(parents=True,exist_ok=True)
                reader=tar.extractfile(member)
                if reader is None:raise RuntimeError('File has no bytes.')
                data=reader.read()
                if len(data)!=member.size:raise RuntimeError('Archive member size mismatch.')
                target.write_bytes(data)
                counts['regular_files']+=1;counts['file_bytes']+=len(data)
                item={'path':normalized,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                if target.suffix=='.lean':
                    lines=data.count(b'\n')+(bool(data) and not data.endswith(b'\n'))
                    counts['lean_files']+=1;counts['lean_bytes']+=len(data);counts['lean_physical_lines']+=lines
                    item['physical_lines']=lines
                index.write(json.dumps(item,ensure_ascii=False,separators=(',',':'))+'\n')
        while stream.read(1024*1024):
            pass
    matches={key:counts[key]==value for key,value in EXPECTED.items()}
    previous=Path('/workspace/scratch/e8ff28430def/output/riemann_human/reference/source_selection/original/lean')
    comparisons=[]
    if previous.is_dir():
        for old in sorted(previous.rglob('*')):
            if old.is_file():
                relative=old.relative_to(previous)
                new=root/relative
                comparisons.append({'path':relative.as_posix(),'exists_in_mirror':new.is_file(),'byte_identical':new.is_file() and old.read_bytes()==new.read_bytes()})
    report={
        'status':'verified_and_extracted' if all(matches.values()) and all(x['byte_identical'] for x in comparisons) else 'mismatch_requires_review',
        'source_kind':'Officially linked public GitHub mirror at immutable first commit',
        'commit':COMMIT,'git_tree':'e517b335d21898fd2506ad538a1e1775c0aaa4e4',
        'mirror_archive_sha256':actual,'mirror_archive_bytes':ARCHIVE.stat().st_size,
        'original_fourteen_volume_archive_recovered':False,
        'author_archive_sha256':'9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc',
        'public_sources':['https://math.mit.edu/~drew/grh/','https://github.com/leanprover-community/riemann-hypothesis/blob/main/verification/NOTES.md'],
        'source_counts':counts,'published_count_checks':matches,
        'gzip_integrity':'passed by reading through EOF (CRC/ISIZE)',
        'safe_paths':True,'only_regular_files_and_directories':True,
        'destination':str(root),'all_file_fingerprints':str(source_index),
        'previously_recovered_selected_files_compared':len(comparisons),
        'previous_selected_files_all_identical':all(x['byte_identical'] for x in comparisons),
        'selected_file_comparisons':comparisons,
        'new_lean_compilation_performed':False,
        'elapsed_seconds':round(time.time()-started,3)
    }
    (BASE/'mirror_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ['status','source_counts','published_count_checks','destination','previously_recovered_selected_files_compared','previous_selected_files_all_identical','elapsed_seconds']},ensure_ascii=False),flush=True)
    if report['status']!='verified_and_extracted':raise RuntimeError('Source mismatch.')

if __name__=='__main__':main()
