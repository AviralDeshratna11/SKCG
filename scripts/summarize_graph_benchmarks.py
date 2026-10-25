"""Create a reviewable report and budget curves from completed benchmark outputs."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main() -> None:
    root = Path('output/benchmarks')
    queries = json.loads(Path('benchmarks/online-boutique.json').read_text(encoding='utf-8'))
    original = Path('.reference-sckg-build/online_boutique_graph.json')
    graph = json.loads(original.read_text(encoding='utf-8'))
    shutil.copyfile(original, root / 'online-boutique-graph.json')
    endpoints = {(e['source'], e['target'], e['relation']) for e in graph['edges']}
    missing = [q for q in queries['queries'] if q['kind'] == 'explicit' and
               (q['target'], q['path'][1], 'IMPLEMENTS') not in endpoints]
    deployed = json.loads((root / 'deployed/verification.json').read_text(encoding='utf-8'))
    text = ['# Traversal architecture verification and benchmark results', '',
            'Run date: 18 October 2026. Changes are local; the deployed site was not updated.', '',
            '## Architecture findings', '',
            f"The deployed API contains {deployed['audit']['nodes']:,} nodes and {deployed['audit']['edges']:,} edges across 11 relation types. "
            'It is a TypeScript application graph, rather than the Online Boutique graph described in the supplied PDF. '
            'It has no explicit RPC contract edges, no source snippets, and no edge confidence values. '
            'Import preserves that missing evidence instead of inventing it.', '',
            'Direct graph import, syntax-edge traversal, query-scoped adjacency, distinct-node admission budgets, '
            'direction controls, parallel-edge deduplication for scoring, layer-aware Pareto pruning, '
            'normalized information gain, and intermediate stopping paths are implemented. '
            'The layer safeguard fixes premature removal of low-similarity contract bridges.', '',
            '## Validation', '',
            '- Project suite: 63 passed, including the real cached MiniLM integration test.',
            '- Reference GRAFT suite: 53 passed.',
            '- Deployed snapshot: 33 relation/direction checks and end-to-end retrieval/trace export passed.',
            '- Existing Week 1 validation completed with hashing and MiniLM.',
            '- Python compilation and diff whitespace checks passed. Ruff is not installed; no Ruff result is claimed.', '',
            '## Benchmark scope', '',
            'Each provider runs 30 rows × 5 seeds × 5 budgets × 16 methods = 12,000 runs. '
            'The methods comprise 10 baselines, EG-POT, and 5 ablations. '
            'Budgets are 20, 40, 60, 100, and 200 unique admitted nodes. '
            'Expanded-budget uses twice the nominal cap and is marked separately. '
            'The fixed split has 10 dev and 20 test rows; paired phrasings stay in the same split. '
            'Algorithm corrections were checked on the currency dev example before restarting the full matrix; '
            'held-out results were not used to adjust parameters. '
            'All methods receive the same start function, and only the scorer receives gold targets/paths.', '',
            f"The available Online Boutique snapshot has {len(graph['nodes']):,} nodes and {len(graph['edges']):,} edges. "
            'The PDF headline is 1,796 nodes and 5,183 edges, so these runs must not be presented as an exact reproduction of that unpublished snapshot. '
            f"{len(missing)} of the 15 expected consumer/contract/implementation paths lack the implementation-to-contract edge. "
            'These edges are left missing. Overall undirected connectivity can still exist through unrelated routes.', '',
            f"Gold source review commit: `{queries['source_commit']}`. "
            'Exact gold IDs and source evidence are in `benchmarks/online-boutique.json`. '
            'The graph export and downloaded current source can have different line locations.', '',
            '## Held-out results at nominal budget 200', '',
            '| Method | Hash hit | Hash MRR@5 | MiniLM hit | MiniLM MRR@5 |',
            '|---|---:|---:|---:|---:|']
    datasets = {}
    integrity = {}
    query_by_id = {q['id']: q for q in queries['queries']}
    adjacency = {(e['source'], e['target']) for e in graph['edges']}
    for provider in ['hashing', 'minilm']:
        folder = root / f'boutique-{provider}'
        manifest = json.loads((folder / 'manifest.json').read_text())
        assert manifest['graph_sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
        with (folder / 'summary.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        total = sum(int(r['runs']) for r in rows)
        assert total == 12000, f'Incomplete run: {provider}: {total}'
        seen = set()
        with (folder / 'runs.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                run = json.loads(line)
                key = (run['query_id'], run['method'], run['budget'], run['seed'])
                assert key not in seen, key
                seen.add(key)
                q = query_by_id[run['query_id']]
                assert run['visited'] <= run['effective_budget']
                assert len(run['selected']) <= run['visited']
                assert len(set(run['selected'])) == len(run['selected'])
                assert run['hit'] == float(q['target'] in run['selected'])
                for path in run['paths']:
                    assert path[0] == q['start']
                    assert len(path) == len(set(path))
                    assert len(path) <= 6
                    assert all((a, b) in adjacency or (b, a) in adjacency
                               for a, b in zip(path, path[1:]))
        assert len(seen) == 12000
        integrity[provider] = {'unique_runs': len(seen), 'budget_checks': 'passed',
                               'exact_hit_checks': 'passed', 'path_edge_checks': 'passed',
                               'cycle_hop_start_checks': 'passed'}
        datasets[provider] = [r for r in rows if r['split'] == 'test']
    (root / 'integrity-checks.json').write_text(json.dumps(integrity, indent=2), encoding='utf-8')
    methods = json.loads((root / 'boutique-hashing/manifest.json').read_text())['methods']
    for method in methods:
        values = [next(r for r in datasets[p] if r['method'] == method and int(r['budget']) == 200)
                  for p in ['hashing', 'minilm']]
        text.append(f"| {method} | {float(values[0]['hit']):.3f} | {float(values[0]['mrr_at_5']):.3f} | "
                    f"{float(values[1]['hit']):.3f} | {float(values[1]['mrr_at_5']):.3f} |")
    text += ['', 'Expanded-budget in this table admits up to 400 nodes. Hit means that the exact gold implementation '
             'is somewhere in the returned node set; MRR@5 uses the shared semantic reranker.', '',
             '## Baseline wins and interpretation', '']
    for provider, rows in datasets.items():
        for budget in [20, 40, 60, 100, 200]:
            comparable = [r for r in rows if int(r['budget']) == budget and r['method'] != 'expanded_budget']
            best = max(comparable, key=lambda r: float(r['mrr_at_5']))
            egpot = next(r for r in comparable if r['method'] == 'egpot')
            text.append(f"- {provider}, budget {budget}: highest MRR@5 is {best['method']} "
                        f"({float(best['mrr_at_5']):.3f}); EG-POT is {float(egpot['mrr_at_5']):.3f}.")
    text += ['', 'The benchmark does not establish that EG-POT beats every baseline. Inspect the complete '
             'per-budget results and individual paths before drawing a performance conclusion. '
             'Missing producer links, name-only exports, local beam pruning, and hard hub suppression remain limitations.', '',
             '## Artifacts and reproducibility', '',
             '- `deployed/verification.json`: graph audit, structural checks, and retrieved context.',
             '- `deployed/retrieval-trace.json`: end-to-end traversal trace.',
             '- `online-boutique-graph.json`: the exact benchmark graph snapshot.',
             '- `graph-gaps.json`: missing expected contract edges with source evidence; no edges injected.',
             '- `integrity-checks.json`: all 24,000 runs checked for unique keys, budgets, exact hits, valid edges, cycles, hop limits, and common starts.',
             '- `boutique-{hashing,minilm}/manifest.json`: graph/query hashes, provider, budgets, seeds, and scope.',
             '- `boutique-{hashing,minilm}/runs.jsonl`: every run with exact selected IDs and ordered paths.',
             '- `boutique-{hashing,minilm}/summary.csv`: dev/test metrics by method and budget.',
             '- `boutique-{hashing,minilm}/significance.json`: paired Wilcoxon results with Holm adjustment.',
             '- `boutique-{hashing,minilm}/table.tex`: test-split LaTeX tables.',
             '- `budget-curves.png`: accuracy and latency curves for representative methods.', '',
             'Embedding matrix and Louvain construction are excluded from latency. Query scoring is included on first use; '
             'CPU contention from concurrent provider runs affects wall-clock latency. Treat these as local comparative timings. '
             'Five deterministic EG-POT repetitions are not independent samples. Significance tests average seeds per query; '
             'paired phrasings remain correlated, so statistical results are exploratory.', '',
             '## Remaining scope', '',
             'The linked polyglot-repo-list contains a catalog, not executable tests or shared relevance labels. '
             'The other seven systems were not benchmarked. No accuracy claim is made for those systems or for semantic '
             'relevance on the deployed graph, which has no supplied gold labels. '
             'No downstream LLM evaluation or Tree-of-Thoughts baseline is included. '
             'See `docs/TRAVERSAL_ARCHITECTURE.md` for exact algorithm and baseline definitions.']
    (root / 'REPORT.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    shown = ['egpot', 'vector', 'vector_bfs_3', 'ppr', 'beam', 'standard_mcts', 'no_mcts']
    for col, (provider, rows) in enumerate(datasets.items()):
        for method in shown:
            group = sorted([r for r in rows if r['method'] == method], key=lambda r: int(r['budget']))
            x = [int(r['budget']) for r in group]
            axes[0, col].plot(x, [float(r['hit']) for r in group], marker='o', label=method)
            axes[1, col].plot(x, [float(r['latency_ms']) for r in group], marker='o', label=method)
        axes[0, col].set(title=f'{provider}: held-out target hit', ylabel='Exact target hit rate', ylim=(0, 1))
        axes[1, col].set(title=f'{provider}: local traversal latency', ylabel='Mean milliseconds', yscale='log')
        for ax in axes[:, col]:
            ax.set_xlabel('Distinct admitted-node budget')
            ax.grid(alpha=0.2)
        axes[0, col].legend(fontsize=8)
    fig.savefig(root / 'budget-curves.png', dpi=160)
    plt.close(fig)
    print(root / 'REPORT.md')


if __name__ == '__main__':
    main()
