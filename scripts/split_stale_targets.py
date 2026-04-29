#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input', default='artifacts/stale_targets.json')
    p.add_argument('--output-dir', dest='output_dir', default='artifacts/stale-targets-by-country')
    p.add_argument('--matrix-output', dest='matrix_output', default='artifacts/stale_matrix.json')
    a=p.parse_args()
    data=json.loads(Path(a.input).read_text(encoding='utf-8')) if Path(a.input).exists() else []
    grouped={}
    for t in data:
      grouped.setdefault(t['country'], []).append(t)
    out_dir=Path(a.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    include=[]
    for country in sorted(grouped):
      target_file=out_dir/f'{country}.json'
      target_file.write_text(json.dumps(grouped[country], indent=2, ensure_ascii=False), encoding='utf-8')
      include.append({'country':country,'targets_file':str(target_file)})
    matrix={'include':include}
    Path(a.matrix_output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.matrix_output).write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(matrix))

if __name__=='__main__': main()
