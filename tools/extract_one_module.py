#!/usr/bin/env python3
"""Extract one original module using the byte-offset index; verify its hash."""
import argparse
import hashlib
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--module',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    selected=None
    with a.index.open(encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            if r.get('kind')=='source' and a.module in (r['module'],r['path']):
                selected=r
                break
    if selected is None:raise SystemExit('Module not found in index: '+a.module)
    with a.bundle.open('rb') as f:
        f.seek(selected['byte_offset'])
        body=f.read(selected['bytes'])
    if len(body)!=selected['bytes'] or hashlib.sha256(body).hexdigest()!=selected['sha256']:
        raise SystemExit('Byte length or SHA256 mismatch; no output written.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as f:f.write(body)
    print(json.dumps({'module':selected['module'],'path':str(a.output),'bytes':len(body),'sha256':selected['sha256'],'verified':True},ensure_ascii=False))

if __name__=='__main__':main()
