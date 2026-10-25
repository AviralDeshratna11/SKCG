# Traversal architecture verification and benchmark results

Run date: 18 October 2026. Changes are local; the deployed site was not updated.

## Architecture findings

The deployed API contains 3,137 nodes and 7,898 edges across 11 relation types. It is a TypeScript application graph, rather than the Online Boutique graph described in the supplied PDF. It has no explicit RPC contract edges, no source snippets, and no edge confidence values. Import preserves that missing evidence instead of inventing it.

Direct graph import, syntax-edge traversal, query-scoped adjacency, distinct-node admission budgets, direction controls, parallel-edge deduplication for scoring, layer-aware Pareto pruning, normalized information gain, and intermediate stopping paths are implemented. The layer safeguard fixes premature removal of low-similarity contract bridges.

## Validation

- Project suite: 63 passed, including the real cached MiniLM integration test.
- Reference GRAFT suite: 53 passed.
- Deployed snapshot: 33 relation/direction checks and end-to-end retrieval/trace export passed.
- Existing Week 1 validation completed with hashing and MiniLM.
- Python compilation and diff whitespace checks passed. Ruff is not installed; no Ruff result is claimed.

## Benchmark scope

Each provider runs 30 rows × 5 seeds × 5 budgets × 16 methods = 12,000 runs. The methods comprise 10 baselines, EG-POT, and 5 ablations. Budgets are 20, 40, 60, 100, and 200 unique admitted nodes. Expanded-budget uses twice the nominal cap and is marked separately. The fixed split has 10 dev and 20 test rows; paired phrasings stay in the same split. Algorithm corrections were checked on the currency dev example before restarting the full matrix; held-out results were not used to adjust parameters. All methods receive the same start function, and only the scorer receives gold targets/paths.

The available Online Boutique snapshot has 1,794 nodes and 5,155 edges. The PDF headline is 1,796 nodes and 5,183 edges, so these runs must not be presented as an exact reproduction of that unpublished snapshot. 11 of the 15 expected consumer/contract/implementation paths lack the implementation-to-contract edge. These edges are left missing. Overall undirected connectivity can still exist through unrelated routes.

Gold source review commit: `38e7348eb289eb5b87c0c6e8cb19ced0449dc389`. Exact gold IDs and source evidence are in `benchmarks/online-boutique.json`. The graph export and downloaded current source can have different line locations.

## Held-out results at nominal budget 200

| Method | Hash hit | Hash MRR@5 | MiniLM hit | MiniLM MRR@5 |
|---|---:|---:|---:|---:|
| vector | 0.300 | 0.017 | 1.000 | 0.025 |
| vector_bfs_2 | 0.500 | 0.098 | 0.500 | 0.062 |
| vector_bfs_3 | 0.590 | 0.050 | 0.600 | 0.075 |
| vector_bfs_4 | 0.590 | 0.050 | 0.600 | 0.075 |
| vector_bfs_5 | 0.590 | 0.050 | 0.600 | 0.075 |
| ppr | 0.800 | 0.060 | 0.800 | 0.129 |
| beam | 0.050 | 0.000 | 0.100 | 0.000 |
| greedy | 0.000 | 0.000 | 0.000 | 0.000 |
| community | 0.150 | 0.050 | 0.250 | 0.027 |
| standard_mcts | 0.410 | 0.083 | 0.410 | 0.044 |
| egpot | 0.200 | 0.133 | 0.200 | 0.054 |
| weighted_sum | 0.200 | 0.133 | 0.150 | 0.075 |
| no_entropy | 0.100 | 0.100 | 0.100 | 0.020 |
| no_contracts | 0.200 | 0.108 | 0.200 | 0.054 |
| no_mcts | 0.000 | 0.000 | 0.050 | 0.017 |
| expanded_budget | 0.200 | 0.133 | 0.200 | 0.054 |

Expanded-budget in this table admits up to 400 nodes. Hit means that the exact gold implementation is somewhere in the returned node set; MRR@5 uses the shared semantic reranker.

## Baseline wins and interpretation

- hashing, budget 20: highest MRR@5 is ppr (0.150); EG-POT is 0.000.
- hashing, budget 40: highest MRR@5 is ppr (0.155); EG-POT is 0.000.
- hashing, budget 60: highest MRR@5 is ppr (0.105); EG-POT is 0.000.
- hashing, budget 100: highest MRR@5 is weighted_sum (0.133); EG-POT is 0.083.
- hashing, budget 200: highest MRR@5 is egpot (0.133); EG-POT is 0.133.
- minilm, budget 20: highest MRR@5 is ppr (0.117); EG-POT is 0.000.
- minilm, budget 40: highest MRR@5 is ppr (0.104); EG-POT is 0.000.
- minilm, budget 60: highest MRR@5 is ppr (0.102); EG-POT is 0.000.
- minilm, budget 100: highest MRR@5 is egpot (0.054); EG-POT is 0.054.
- minilm, budget 200: highest MRR@5 is ppr (0.129); EG-POT is 0.054.

The benchmark does not establish that EG-POT beats every baseline. Inspect the complete per-budget results and individual paths before drawing a performance conclusion. Missing producer links, name-only exports, local beam pruning, and hard hub suppression remain limitations.

## Artifacts and reproducibility

- `deployed/verification.json`: graph audit, structural checks, and retrieved context.
- `deployed/retrieval-trace.json`: end-to-end traversal trace.
- `online-boutique-graph.json`: the exact benchmark graph snapshot.
- `graph-gaps.json`: missing expected contract edges with source evidence; no edges injected.
- `integrity-checks.json`: all 24,000 runs checked for unique keys, budgets, exact hits, valid edges, cycles, hop limits, and common starts.
- `boutique-{hashing,minilm}/manifest.json`: graph/query hashes, provider, budgets, seeds, and scope.
- `boutique-{hashing,minilm}/runs.jsonl`: every run with exact selected IDs and ordered paths.
- `boutique-{hashing,minilm}/summary.csv`: dev/test metrics by method and budget.
- `boutique-{hashing,minilm}/significance.json`: paired Wilcoxon results with Holm adjustment.
- `boutique-{hashing,minilm}/table.tex`: test-split LaTeX tables.
- `budget-curves.png`: accuracy and latency curves for representative methods.

Embedding matrix and Louvain construction are excluded from latency. Query scoring is included on first use; CPU contention from concurrent provider runs affects wall-clock latency. Treat these as local comparative timings. Five deterministic EG-POT repetitions are not independent samples. Significance tests average seeds per query; paired phrasings remain correlated, so statistical results are exploratory.

## Remaining scope

The linked polyglot-repo-list contains a catalog, not executable tests or shared relevance labels. The other seven systems were not benchmarked. No accuracy claim is made for those systems or for semantic relevance on the deployed graph, which has no supplied gold labels. No downstream LLM evaluation or Tree-of-Thoughts baseline is included. See `docs/TRAVERSAL_ARCHITECTURE.md` for exact algorithm and baseline definitions.
