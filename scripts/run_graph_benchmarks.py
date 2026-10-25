"""Run the PDF's method/budget matrix on exact, reviewed Online Boutique labels.

Example (PowerShell):
  $env:PYTHONPATH='src'
  python scripts/run_graph_benchmarks.py --graph graph.json --queries benchmarks/online-boutique.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

from scipy.stats import wilcoxon

from sckg.eval.graph_benchmark import Benchmark, METHODS, score_result
from sckg.graph.import_graph import import_graph, audit_graph
from sckg.graph.json_store import JsonGraphStore
from sckg.retrieval.semantic import make_embedding_provider


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('output/benchmarks'))
    parser.add_argument('--provider', choices=['hashing', 'sentence-transformers'], default='hashing')
    parser.add_argument('--budgets', nargs='+', type=int, default=[20, 40, 60, 100, 200])
    parser.add_argument('--seeds', nargs='+', type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument('--methods', nargs='+', choices=METHODS, default=list(METHODS))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    document = import_graph(args.graph)
    store = JsonGraphStore(args.output / 'unused-store.json')
    store.symbols = {s.id: s for s in document.symbols}
    store.relations = {r.id: r for r in document.relations}
    queries = json.loads(args.queries.read_text(encoding='utf-8'))['queries']
    for row in queries:
        if not {row['start'], row['target'], *row['path']} <= store.symbols.keys():
            raise ValueError(f"Missing exact graph IDs in {row['id']}")
        if row['split'] not in {'dev', 'test'}:
            raise ValueError('An explicit dev/test split is required')
    provider = make_embedding_provider(args.provider, local_files_only=True)
    benchmark = Benchmark(store, provider)
    manifest = {
        'graph_sha256': hashlib.sha256(args.graph.read_bytes()).hexdigest(),
        'queries_sha256': hashlib.sha256(args.queries.read_bytes()).hexdigest(),
        'provider': args.provider, 'model': getattr(provider, 'model_name', 'blake2-256'),
        'methods': args.methods, 'budgets': args.budgets, 'seeds': args.seeds,
        'audit': audit_graph(document),
        'budget_definition': 'distinct admitted nodes including common start; embedding scoring is global',
        'expanded_budget': '2x listed budget, report effective_budget explicitly',
        'seed_note': 'EG-POT is deterministic; repeated seeds are repetitions, not independent samples',
        'latency_note': 'Louvain partition and embedding matrix preprocessing excluded; per-query scoring included on first use',
        'gold_used_by_algorithms': False,
        'unreachable_targets': [q['id'] for q in queries if not __import__('networkx').has_path(
            benchmark.graph, q['start'], q['target'])],
    }
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    rows = []
    with (args.output / 'runs.jsonl').open('w', encoding='utf-8') as output:
        for budget in args.budgets:
            for seed in args.seeds:
                for q in queries:
                    for method in args.methods:
                        # No gold target/path or split is supplied to any search implementation.
                        result = benchmark.run(method, q['query'], q['start'], budget, seed,
                                               provider_name=args.provider)
                        row = {'query_id': q['id'], 'split': q['split'], 'method': method,
                               'budget': budget, 'seed': seed,
                               'effective_budget': result['effective_budget'],
                               **score_result(result, q)}
                        rows.append(row)
                        output.write(json.dumps({**row, 'selected': result['selected'],
                                                 'paths': result['paths']}) + '\n')
                output.flush()
                print(f'budget={budget} seed={seed} completed runs={len(rows)}', flush=True)
    groups = defaultdict(list)
    for row in rows:
        groups[(row['split'], row['method'], row['budget'])].append(row)
    metrics = ['hit', 'hits_at_1', 'hits_at_5', 'mrr_at_5', 'path_coverage',
               'ordered_path', 'redundancy', 'latency_ms', 'visited']
    summaries = [{'split': split, 'method': method, 'budget': budget, 'runs': len(group),
                  **{metric: statistics.mean(row[metric] for row in group) for metric in metrics}}
                 for (split, method, budget), group in sorted(groups.items())]
    with (args.output / 'summary.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    # Pair at query level after averaging seeds. Repeated deterministic runs are not n=5 evidence.
    significance = []
    for budget in args.budgets:
        for method in args.methods:
            if method == 'egpot' or 'egpot' not in args.methods:
                continue
            diffs = []
            for q in queries:
                if q['split'] == 'test':
                    values = {m: statistics.mean(r['mrr_at_5'] for r in rows if
                              r['query_id'] == q['id'] and r['budget'] == budget and r['method'] == m)
                              for m in ['egpot', method]}
                    diffs.append(values['egpot'] - values[method])
            # Explicitly handle all-zero paired differences; SciPy otherwise returns NaN.
            p = float(wilcoxon(diffs).pvalue) if any(diffs) else 1.0
            significance.append({'budget': budget, 'competitor': method,
                                 'paired_queries': len(diffs), 'raw_p': p})
    # Holm adjustment across the full method/budget family.
    peak = 0.0
    for i, row in enumerate(sorted(significance, key=lambda r: r['raw_p'])):
        peak = max(peak, min(1.0, row['raw_p'] * (len(significance) - i)))
        row['holm_p'] = peak
    (args.output / 'significance.json').write_text(json.dumps(significance, indent=2), encoding='utf-8')
    table = ['% Test split only. Reproduce from manifest.json; no cross-dataset paper claims.',
             r'\begin{tabular}{lrrrr}', r'Method & Budget & Hit & MRR@5 & Latency ms \\']
    for s in summaries:
        if s['split'] == 'test':
            name = s['method'].replace('_', r'\_')
            table.append(f"{name} & {s['budget']} & {s['hit']:.3f} & {s['mrr_at_5']:.3f} & {s['latency_ms']:.1f} " + r'\\')
    table.append(r'\end{tabular}')
    (args.output / 'table.tex').write_text('\n'.join(table), encoding='utf-8')
    print(f'Finished {len(rows)} runs; results: {args.output}', flush=True)


if __name__ == '__main__':
    main()
