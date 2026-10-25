"""Copy the tested traversal core and benchmark evidence into the shrey checkout."""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / 'site/graph-builder'
    if not (target / 'viewer/index.html').is_file():
        raise SystemExit('Clone and select the shrey branch first')
    provenance = {}
    for source in (root / 'src/sckg').rglob('*.py'):
        relative = source.relative_to(root / 'src')
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        provenance[str(relative).replace('\\', '/')] = hashlib.sha256(source.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    data = target / 'viewer/data'
    data.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'tmp/deployed-graph.json', data / 'carmein.json')
    shutil.copyfile(root / 'output/benchmarks/online-boutique-graph.json', data / 'boutique.json')
    evidence = data / 'benchmarks'
    evidence.mkdir(exist_ok=True)
    shutil.copyfile(root / 'benchmarks/online-boutique.json', evidence / 'queries.json')
    for name in ['REPORT.md', 'graph-gaps.json', 'integrity-checks.json', 'budget-curves.png']:
        shutil.copyfile(root / 'output/benchmarks' / name, evidence / name)
    for provider in ['hashing', 'minilm']:
        source = root / 'output/benchmarks' / f'boutique-{provider}'
        dest = evidence / provider
        dest.mkdir(exist_ok=True)
        for name in ['manifest.json', 'summary.csv', 'significance.json', 'table.tex']:
            shutil.copyfile(source / name, dest / name)
        with (source / 'runs.jsonl').open('rb') as stream, gzip.open(dest / 'runs.jsonl.gz', 'wb') as zipped:
            shutil.copyfileobj(stream, zipped)
    (target / 'TRAVERSAL_CORE_PROVENANCE.json').write_text(json.dumps({
        'source': 'SCKGGraphSOP traversal implementation', 'files_sha256': provenance,
        'benchmark_runs': 24000,
        'hash_normalization': 'CRLF to LF only',
        'note': 'Vendored unchanged so live paths use the same Python engine as the benchmarks.'
    }, indent=2), encoding='utf-8')
    print(f'Prepared {len(provenance)} source files and benchmark evidence in {target}')


if __name__ == '__main__':
    main()
