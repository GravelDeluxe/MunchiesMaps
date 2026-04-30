#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def portable_targets_path(target_file: Path, output_dir: Path, artifact_root: Path | None) -> str:
    if artifact_root is not None:
        return str(target_file.resolve().relative_to(artifact_root.resolve()))
    try:
        return str(target_file.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        return str(target_file)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='artifacts/stale_targets.json')
    parser.add_argument('--output-dir', dest='output_dir', default='artifacts/stale-targets-by-country')
    parser.add_argument('--matrix-output', dest='matrix_output', default='artifacts/stale_matrix.json')
    parser.add_argument('--artifact-root', dest='artifact_root')
    parser.add_argument('--target-chunk-size', dest='target_chunk_size', type=int, default=25)
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding='utf-8')) if input_path.exists() else []

    grouped: dict[str, list[dict]] = {}
    for target in data:
        grouped.setdefault(target['country'], []).append(target)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = Path(args.artifact_root) if args.artifact_root else None

    include: list[dict[str, str]] = []
    for country in sorted(grouped):
        country_targets = grouped[country]
        chunk_size = args.target_chunk_size
        if chunk_size and chunk_size > 0 and len(country_targets) > chunk_size:
            total_chunks = (len(country_targets) + chunk_size - 1) // chunk_size
            for idx in range(total_chunks):
                chunk = idx + 1
                chunk_id = f'{chunk:03d}'
                start = idx * chunk_size
                end = start + chunk_size
                target_file = out_dir / f'{country}-chunk-{chunk_id}.json'
                target_file.write_text(json.dumps(country_targets[start:end], indent=2, ensure_ascii=False), encoding='utf-8')
                include.append(
                    {
                        'country': country,
                        'chunk': chunk_id,
                        'targets_file': portable_targets_path(target_file, out_dir, artifact_root),
                    }
                )
        else:
            target_file = out_dir / f'{country}.json'
            target_file.write_text(json.dumps(country_targets, indent=2, ensure_ascii=False), encoding='utf-8')
            include.append(
                {
                    'country': country,
                    'targets_file': portable_targets_path(target_file, out_dir, artifact_root),
                }
            )

    matrix = {'include': include}
    matrix_output = Path(args.matrix_output)
    matrix_output.parent.mkdir(parents=True, exist_ok=True)
    matrix_output.write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(matrix))


if __name__ == '__main__':
    main()
