# EG-POT Week 1 Update: Changes, Reasoning, and Verification

This guide explains the search-engine update and the visualization added afterward. It is written for someone who wants to understand the behaviour without first reading the implementation.

**The goal:** given a question about a repository, find a useful, connected set of code symbols and show how the search reached them.

**Delivered:** Beam-MCTS search, working hub suppression, configurable local embeddings, reproducible hashing, configuration and CLI controls, richer traces, and an interactive way to compare and replay results.

The scope comes from the two requested screenshot features and **Hop 1 / Week 1** of the [30-day plan](.sckg/egpot-30day-plan.pdf). The later baseline, benchmark, experiment, and LLM-harness tasks are outside this update.

## 1. Why this update was needed

The repository already had a working retrieval pipeline. It could index Python code into a graph, find symbols related to a question, follow relationships, and pack selected code into a context response.

It also already had the four EG-POT objectives and Pareto selection. The following gaps remained:

| Before | Why it mattered | What changed |
|---|---|---|
| Per-hop Pareto beam search without simulations or backpropagation | A relevant target can sit behind an intermediate symbol that looks less relevant at first. | Added a search tree, PUCT selection, bounded rollouts, and reward backpropagation. |
| Hub-suppression setting had no working effect | Shared utility symbols could distract search from the question. | Connected the setting to seed filtering, graph expansion, and entropy discounting. |
| Semantic scoring used hashed token counts | Matching words is a limited substitute for learned similarity. | Added a local trained embedding provider shared by localization and traversal. |
| Hashing used Python's process-dependent hash function | Separate runs could produce different vectors. | Replaced it with stable BLAKE2 hashing. |
| CLI did not load EG-POT YAML into retrieval | Editing configuration did not provide the intended control. | Added explicit YAML loading and CLI overrides. |
| Viewer highlighted only the final selected subgraph | Search paths and differences between runs were difficult to inspect. | Added run selection, path replay, hub indicators, and MCTS statistics. |

These changes make the intended Week 1 search executable and inspectable. They do not, by themselves, establish the paper's benchmark claims.

## 2. What nodes, hops, and trajectories mean

A **node** is an indexed symbol, such as a function, method, class, or import. For example, `AuthenticationMiddleware.validate` can be a node.

An **edge** records a relationship between symbols. The default EG-POT relationship types are:

| Type | Meaning |
|---|---|
| `CALLS` | One symbol calls another. |
| `REFERENCES` | One symbol refers to another. |
| `IMPORTS` | An import relationship connects symbols. |
| `INHERITS` | A class inherits from another. |
| `IMPLEMENTS` | A symbol implements an interface or related contract. |
| `OVERRIDES` | A method overrides another method. |

These are allowed types, not a claim that the Python frontend emits every type for every repository. Its existing resolution limitations still apply.

A **seed** is a promising starting symbol. EG-POT uses up to three seeds by default.

A **hop** means crossing one graph edge:

```text
Starting symbol -> related symbol -> another related symbol
     hop 0             hop 1                hop 2
```

A **trajectory** is the complete ordered path: its starting node, subsequent nodes, and the edges used to reach them.

**Hopping does not execute the code.** It searches relationships in the indexed graph. The traverser can follow incoming and outgoing relationships. It can move toward a function's caller as well as toward something the function calls. A trajectory therefore does not necessarily represent runtime execution order.

Two trajectories can reach the same node through different routes. In the MCTS tree, these are different states because history affects depth, novelty, and cycle checks.

The final **context subgraph** is the union of the selected trajectories, with duplicate nodes and edges removed. Existing ranking and packing stages turn it into the retrieval response.

## 3. What happens when you submit a question

For example:

> Trace why authentication refresh tokens are rejected

The pipeline:

1. Obtains the indexed symbols.
2. Excludes seed candidates above the hub threshold when suppression is enabled.
3. Scores symbols using lexical matching and the configured embedding provider.
4. Combines the scores and chooses seed candidates.
5. For `--strategy egpot`, runs Beam-MCTS by default from the best seeds.
6. Evaluates possible hops using the four EG-POT objectives.
7. Prunes candidates, simulates retained branches, and updates the search tree.
8. Selects the best sampled terminal trajectories and forms their context subgraph.
9. Ranks and packs the selected code under the context budget.
10. Optionally prints an explanation and saves a visualization trace.

The retained default seed-score combination is 55% lexical and 45% semantic. The representation supplying the semantic score changed.

The normal CLI strategy is still `hybrid`. Use **`--strategy egpot`** to invoke Beam-MCTS. Provider selection and hub filtering also apply to hybrid retrieval.

## 4. Local embeddings: what changed and why

Previously, tokens were counted into hash buckets. Texts with overlapping words could produce similar vectors, but this was not a trained representation of meaning. Unrelated tokens could also collide.

The default trained provider now uses:

```text
sentence-transformers/all-MiniLM-L6-v2
```

It converts the question and symbol text into vectors and compares them using cosine similarity. Symbol text includes names, paths, signatures, and source text where available. Traversal scoring also includes available type metadata.

This is a lightweight general-purpose text model that accepts code snippets. It is not presented as a specially trained code-retrieval model.

The existing `EmbeddingProvider` interface made this a contained change. The search algorithm can use another representation without needing a hosted inference service or a redesign.

The provider loads its model lazily and caches repeated text embeddings. Localization and traversal within a pipeline share the selected provider instance.

Inference runs locally on CPU. The first load can download model weights if they are not cached. That preparation may require internet access; subsequent local inference does not require a hosted model API.

### Offline and compatibility mode

Use `--use-hash-sim`, or set:

```yaml
egpot:
  embedding_provider: hashing
```

Hashing now uses BLAKE2, making its vectors reproducible across separate Python processes. The cosine helper also handles unnormalized vectors and zero vectors correctly.

The system does not silently change providers halfway through a query. Model-loading failures explain how to install/cache the model or select hashing.

To restrict trained-model loading to cached/local files:

```yaml
egpot:
  embedding_local_files_only: true
```

Change `embedding_model` to try another compatible model. Its quality and resource requirements should be evaluated separately.

## 5. How each possible hop is scored

The four objective definitions already existed. This update retains them, connects the configured embedding provider, adds hub-aware entropy, and uses their weighted value in MCTS.

### Semantic relevance

Cosine similarity between the question and the candidate symbol. It is an estimate of relevance, not a probability that the symbol contains a bug.

### Hop efficiency

Longer paths receive a larger negative score:

```text
hop score = -hop_lambda * trajectory depth
```

With the default lambda of `0.15`:

| Depth | Score |
|---|---:|
| 1 | -0.15 |
| 2 | -0.30 |
| 3 | -0.45 |
| 5 | -0.75 |

The reasoning is that an extra hop should provide some benefit to justify additional exploration and context.

### Contract consistency

A heuristic using type metadata and relation confidence:

- Matching available symbol types normally receive `1.0`.
- A relationship with confidence at least `0.95` normally receives `1.0`.
- Missing type metadata normally receives `0.6`.
- Differing available types with lower-confidence relations are labelled inconsistent, but currently also receive the configured unknown score, normally `0.6`.

The labels distinguish unknown from inconsistent, but the current numeric scoring does not assign separate penalties. This is not a type checker or proof of runtime compatibility.

### Information gain

```text
information gain = structural entropy * novelty
```

Structural entropy measures the distribution of outgoing relationship types. A node with only `CALLS` edges has zero relationship-type entropy, even if it has many outgoing calls. A mix of calls and references can have positive entropy.

It is a structural heuristic, not a direct measurement of useful knowledge.

Novelty starts at `1.0` and applies these discounts:

| Condition | Multiplier |
|---|---:|
| Candidate is in a file already represented in the path | 0.75 |
| Candidate source text equals a previous node's source text | 0.25 |
| The edge type has already appeared in the path | 0.85 |

The discounts multiply when several apply. Cycle-producing candidates are rejected before becoming valid extensions.

### Combining the objectives

The weights are ordered as semantic, hop efficiency, contract consistency, and information gain:

```yaml
objective_weights: [1.0, 1.0, 1.0, 1.0]
```

An illustrative calculation, not a measured example result:

```text
semantic = 0.80
hop      = -0.30
contract = 1.00
info     = 0.20

value with equal weights = 1.70
```

Equal weights do not ensure equal influence because objective ranges differ.

**Reward uses the endpoint's objective vector. It does not sum the semantic scores of every hop.** The endpoint vector still contains path-dependent terms such as depth and novelty.

## 6. How Beam-MCTS works

### Why look ahead?

Consider this illustrative graph:

```text
Seed
  |-- A: strong immediate match -> unhelpful endpoint
  |
  `-- B: weaker immediate match -> relevant target
```

Looking farther along B can reveal its usefulness. This motivates simulations and backpropagation. However, B must first survive pruning: MCTS cannot recover a branch that was removed.

### A. Expand

Find neighbours connected by allowed relationships. Reject cycles, suppressed hubs, and extensions exceeding the estimated token budget.

### B. Pareto-prune

A dominates B when A is at least as good on every objective and strictly better on at least one, subject to a small tolerance.

If A has better semantic relevance but B has better contract consistency, neither necessarily dominates the other.

MCTS expansion keeps the first non-dominated front. If it exceeds the beam width, crowding distance helps preserve different objective trade-offs. By default, at most five children survive an expansion. This does not limit the entire tree to five nodes.

### C. Select using PUCT

Selection balances promising results with alternatives that deserve more exploration. The implementation gives unvisited alternatives an initial visit preference. For visited alternatives:

```text
selection score = mean value
                + ucb_c * prior * sqrt(parent visits) / (1 + child visits)
```

The prior is derived from retained candidates' weighted values using a softmax. It is a search preference, not a calibrated correctness probability. The default `ucb_c` is `1.4`.

### D. Roll out

After reaching an unvisited state, a greedy rollout follows surviving children until the hop limit or a dead end. Rollout states remain in the tree so later simulations can explore other retained alternatives.

Although named Monte Carlo Tree Search, this implementation uses deterministic selection and rollout rules rather than random walks.

### E. Backpropagate

The terminal weighted value is sent back through every state on that simulation path. Each state updates its visits and accumulated reward.

This gives earlier decisions credit for useful endpoints discovered farther along the path.

### F. Return paths

The output contains the highest-valued sampled terminal trajectories, up to the beam width. Final selection uses terminal weighted value, not simply the most-visited state. The selected path union is also checked against the token estimate.

### Simulations are different from hops

Defaults:

```text
simulation_budget = 64
max_hops = 5
beam_width = 5
```

This means up to 64 bounded exploration attempts, each at most five hops long. It does not mean one 64-hop path or exactly 320 unique explored nodes. Simulations share states, expansions inspect multiple neighbours, and paths can stop early.

A terminal seed can produce a zero-hop path. Empty seeds and zero-hop requests do not perform the normal MCTS simulations.

Use `--no-mcts` to retain the earlier per-hop Pareto beam behaviour for comparison.

## 7. Hub suppression and its reasoning

A logger can receive calls from unrelated parts of the repository. High connectivity alone does not make it useful for the user's question.

We count **distinct incoming neighbours**, excluding self-loops. Multiple relationships from the same source count as one incoming neighbour.

```text
hub condition: in-degree > hub_degree_threshold
```

The default threshold is 10. Exactly 10 incoming neighbours is not above that threshold.

### Two behaviours

**Filtering:** hubs are excluded from seed candidates and expansion in both hybrid and EG-POT retrieval.

**Entropy discounting:** the entropy estimator applies:

```text
discounted entropy = original entropy * threshold / in-degree
```

With original entropy `1.0`, threshold `10`, and in-degree `50`, the discounted entropy is `0.2`.

The screenshots requested actual filtering; the Week 1 plan also requested entropy discounting. Both are implemented. Because filtered hubs never become normal expansion candidates, filtering directly causes the demo's path change. Entropy discounting is tested separately.

### Controlled demonstration

The synthetic graph has 50 callers pointing to `logger`. `caller0` also connects to `useful`:

```text
Suppression OFF: caller0 -> logger
Suppression ON:  caller0 -> useful
```

The demo disables semantic scoring and uses hashing to isolate hub behaviour. It is a synthetic fixture, not a real bug-localization benchmark.

Use `--no-suppress-hubs` to disable filtering and discounts. Raising the threshold makes suppression less aggressive. A highly connected function can still be relevant, which is why this remains configurable.

## 8. Limits and stopping behaviour

- `max_hops` bounds trajectory depth.
- `simulation_budget` bounds MCTS attempts.
- `beam_width` bounds expansion survivors and the returned trajectory count.
- Cycle detection prevents revisiting a node in the same trajectory.
- Token estimation limits individual extensions and the selected path union.
- Empty or dead-end branches stop extending.

Search token estimates use whitespace over available symbol text. The existing packer still controls the final context response. This is not exact token accounting for a downstream LLM.

Stop labels include `MAX_HOPS`, `NO_CANDIDATES`, and `TOKEN_BUDGET`. Read the simulation count alongside the label; there is no separate simulation-budget stop label.

These limits bound work but do not establish a latency or global-optimality guarantee.

## 9. Configuration and CLI controls

The full configuration is in [configs/egpot.yaml](configs/egpot.yaml).

| Setting | Default | What it controls |
|---|---|---|
| `mcts_enabled` | `true` | Whether EG-POT uses Beam-MCTS. |
| `simulation_budget` | `64` | Simulation attempts per query. |
| `max_hops` | `5` | Maximum edges per trajectory. |
| `beam_width` | `5` | Expansion survivors and maximum returned paths. |
| `ucb_c` | `1.4` | Exploration contribution in PUCT. |
| `objective_weights` | `[1, 1, 1, 1]` | Terminal reward weights in the documented order. |
| `hub_suppression.enabled` | `true` | Hub filtering and entropy discounts. |
| `hub_degree_threshold` | `10` | Suppress nodes strictly above this incoming-neighbour count. |
| `embedding_provider` | `sentence-transformers` | Trained provider or `hashing`. |
| `embedding_model` | `sentence-transformers/all-MiniLM-L6-v2` | Model identifier or compatible local model path. |
| `embedding_local_files_only` | `false` | Restrict loading to cached/local weights when true. |
| `seed.max_seeds` | `3` | Maximum EG-POT seeds. |
| `hop.lambda` | `0.15` | Penalty per hop. |
| `context.token_budget` | `8192` | EG-POT context budget. |

Pass `--config configs/egpot.yaml` to load that file explicitly. Without it, Python defaults are used; the CLI does not automatically discover the YAML file.

CLI overrides take precedence. Useful options:

```text
--strategy egpot
--mcts / --no-mcts
--simulation-budget 64
--max-hops 5
--beam-width 5
--ucb-c 1.4
--suppress-hubs / --no-suppress-hubs
--hub-degree-threshold 10
--embedding-provider hashing
--use-hash-sim
--token-budget 8192
--explain
--trace .sckg/my-trace.json
```

`--use-hash-sim` takes precedence over `--embedding-provider` if both are supplied. Objective weights and model identifiers are configured through YAML.

## 10. What the visualization now shows

The viewer remains standalone HTML containing recorded graph and trace data. It does not require a hosted JavaScript library.

### Recorded run

Choose a saved result to inspect. The generated auth-service comparison includes the current trained-embedding run, an MCTS hashing run, and the original baseline.

Metrics show search mode, simulation count, embedding provider, and selected-node count. Missing information in older traces is labelled unavailable rather than invented.

### Selected trajectory

To select a path:

1. Open the updated graph.
2. Find **Search evidence** in the left sidebar.
3. Choose **Current run** or **MCTS + hashing** under **Recorded run**.
4. Open **Selected trajectory**.
5. Choose **Path 1**, **Path 2**, or another available path.

The original baseline cannot replay ordered trajectories because its trace did not store them.

### Replay hops

The slider reveals a recorded path incrementally:

```text
Hop 0: starting node
Hop 1: first edge and the node it reaches
Hop 2: first two edges and their nodes
```

It does not execute code, call the embedding model, or rerun search.

### MCTS visits and values

| Field | Meaning |
|---|---|
| Visits | Simulations passing through that trajectory-tree state. |
| Mean value | Average backpropagated terminal reward. |
| Prior | Initial preference among retained alternatives. |

A zero-visit state was created but has not been traversed by a simulation through that state. Values and priors are not probabilities of correctness.

### Colours and graph scope

- Red outlines indicate selected context or the replayed path.
- Cyan outlines indicate seeds.
- Amber dashed outlines mark nodes above the run's hub threshold.
- **All** includes nodes outside selected context, including suppressed hubs.
- Clicking a node exposes code, relationships, objectives, and hub information.

Hub styles can override other outline styles. Viewer in-degree is calculated from the displayed graph. A filtered or truncated export may therefore show fewer neighbours than the full graph used by retrieval.

The recorded excluded-hub list reports encountered exclusions in that run. It is not a census of every hub in the repository.

Changing a dropdown switches saved evidence. After changing code, configuration, or graph data, regenerate the traces and HTML and refresh the page.

## 11. What we observed on the example repository

The verification script ran:

> Trace why authentication refresh tokens are rejected

against the auth-service example graph.

| Result | Simulations | Selected nodes |
|---|---|---:|
| Original baseline | Not recorded | 7 |
| New MCTS with hashing | 64 | 9 |
| New MCTS with trained embeddings | 64 | 9 |

Both new traces differ from the original. The new providers selected the same node set in this comparison, but their paths and scores differ.

One recorded trained-model path is:

```text
auth.auth.tokens
  -> auth.tokens.RefreshTokenValidator
  -> auth.middleware.auth.tokens
  -> auth.tokens.extract_user_id
  -> auth.middleware.AuthenticationMiddleware.validate
```

This is a four-hop search trajectory. Some nodes represent imports. It is not a runtime stack trace.

**Nine selected nodes instead of seven does not prove higher accuracy.** It demonstrates changed selection. Gold-labelled tasks are needed to evaluate quality.

The old baseline is historical evidence, not a controlled experiment isolating a single feature. To isolate one change, keep the graph, query, provider, and other settings fixed while toggling that feature.

See the [comparison report](.sckg/week1-validation/comparison.json) for paths and node-set differences.

## 12. How to verify the update yourself

Run these commands from the repository root in PowerShell.

### A. Install dependencies

```powershell
python -m pip install -e ".[dev,embeddings]"
$env:PYTHONPATH = "src"
```

The `embeddings` extra installs the trained-provider dependency. Hashing does not require model weights.

If MiniLM is not cached, download/cache it once:

```powershell
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

This preparation may access the internet. The verification script itself uses cached model files only.

### B. Run verification

```powershell
python scripts/verify_egpot_week1.py
```

Default inputs:

```text
.sckg/auth-service-graph.json
.sckg/egpot-trace.json
configs/egpot.yaml
```

The existing graph and original trace are preserved. New outputs go under `.sckg/week1-validation/`.

The script accepts `--store`, `--baseline`, `--repo`, `--config`, and `--output` for other paths. It expects a compatible existing indexed graph and baseline trace; it does not construct a benchmark corpus.

### C. Open the graphs

These files open directly in a browser:

- [Auth-service comparison](.sckg/week1-validation/graph.html)
- [Synthetic hub demo](.sckg/week1-validation/hub-suppression.html)

Alternatively:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8765/.sckg/week1-validation/graph.html
http://127.0.0.1:8765/.sckg/week1-validation/hub-suppression.html
```

Reuse an existing server if port 8765 is already in use. These URLs work only while the local server is running.

### D. Check hopping and MCTS

1. Select the current trained-model run in the auth-service viewer.
2. Confirm **Beam-MCTS** and **64** simulations.
3. Choose a trajectory and move the slider from zero to its end.
4. Expand **MCTS visits and values**.
5. Switch to hashing and compare paths.
6. Switch to the original baseline to compare selected context.

### E. Check hub suppression

1. Open the synthetic demo. The current run has suppression ON and selects `caller0 -> useful`.
2. Switch to **Suppression OFF** and confirm `caller0 -> logger`.
3. Click **All** to reveal the fixture.
4. Inspect `logger` and its 50 incoming neighbours.

This fixture isolates the toggle's behaviour. A real graph without nodes above the threshold may show no difference, which is expected.

### F. Run your own question

This example uses hashing and the supplied graph:

```powershell
$env:PYTHONPATH = "src"
$env:SCKG_STORE = "json"
$env:SCKG_JSON_STORE = ".sckg/auth-service-graph.json"

python -m sckg.cli.main retrieve "Trace why authentication refresh tokens are rejected" --repo examples/auth_service_repo --strategy egpot --config configs/egpot.yaml --use-hash-sim --explain --trace .sckg/my-trace.json

python -m sckg.cli.main visualize --egpot-trace .sckg/my-trace.json --compare-trace .sckg/egpot-trace.json --output .sckg/my-graph.html
```

Remove `--use-hash-sim` to use the configured trained model. Repeat `--compare-trace` to include additional results. Compare traces from the same indexed graph.

If source code changes, reindex before interpreting new retrieval results:

```powershell
python -m sckg.cli.main index examples/auth_service_repo
```

This updates the store selected by `SCKG_JSON_STORE`. Choose a separate store path to preserve an earlier graph snapshot. Retrieval's `--repo` should match the indexed repository.

### G. Compare MCTS on and off

With the environment above, keep the question, graph, and provider fixed:

```powershell
python -m sckg.cli.main retrieve "refresh tokens rejected" --repo examples/auth_service_repo --strategy egpot --use-hash-sim --mcts --trace .sckg/mcts-on.json

python -m sckg.cli.main retrieve "refresh tokens rejected" --repo examples/auth_service_repo --strategy egpot --use-hash-sim --no-mcts --trace .sckg/mcts-off.json

python -m sckg.cli.main visualize --egpot-trace .sckg/mcts-on.json --compare-trace .sckg/mcts-off.json --output .sckg/mcts-comparison.html
```

The same approach works with `--suppress-hubs` and `--no-suppress-hubs`.

## 13. Testing and evidence

At the end of the implementation and visualization update, the full suite reported **50 passed** with the real-model test enabled.

Normal suite:

```powershell
python -m pytest -q
```

Without the opt-in setting, the real-model integration test is skipped. The validation snapshot then reported 49 passed and 1 skipped.

To include the actual cached-model test:

```powershell
$env:SCKG_TEST_REAL_EMBEDDINGS = "1"
python -m pytest -q
```

| Area | Evidence covered |
|---|---|
| MCTS | Known target path, visit counts, and backpropagated values on a constructed graph. |
| Objective weights | Different weights change the preferred terminal path. |
| Bounds | Hop and token limits, empty seeds, and invalid settings. |
| Cycles | A trajectory does not revisit a node. |
| Pareto | Dominated candidates are pruned and expansion width is bounded. |
| Hubs | A 50-in-degree logger is selected with suppression off and excluded with it on, in both traversal modes. |
| Entropy | Discount math and the strict threshold boundary. |
| Graph access | Degree counting through JSON and the generic neighbour API. |
| Provider behaviour | Lazy loading, caching, cosine, and actionable load failures. |
| Real model | Addition snippets score more similarly than an unrelated file-deletion snippet. |
| Reproducibility | Hash vectors agree across processes with different Python hash seeds. |
| Configuration | YAML and CLI overrides reach the actual trace. |
| Visualization | Ordered paths and comparison runs export correctly, with script-ending text escaped. |

Both generated visualizations passed JavaScript syntax checks. An interactive browser connection was unavailable during the update, so rendered layout and click behaviour were not verified through browser automation. Python tests and syntax checks do not replace that visual inspection.

These counts are a recorded validation snapshot, not a claim that tests rerun whenever this guide is opened.

## 14. File-by-file reference

| File | Responsibility |
|---|---|
| [mcts.py](src/sckg/retrieval/egpot/mcts.py) | Tree, PUCT, rollouts, backpropagation, and terminal-path selection. |
| [hub_suppression.py](src/sckg/retrieval/egpot/hub_suppression.py) | Degree counts, filtering decisions, discounts, and encountered exclusions. |
| [embeddings provider](src/sckg/retrieval/embeddings/__init__.py) | Lazy local model and text-embedding cache. |
| [semantic.py](src/sckg/retrieval/semantic.py) | Provider factory, stable hashing, cosine, and semantic ranking. |
| [config.py](src/sckg/retrieval/egpot/config.py) | Settings, parsing, and validation. |
| [egpot.yaml](configs/egpot.yaml) | Editable defaults. |
| [objectives.py](src/sckg/retrieval/egpot/objectives.py) | Provider and hub-aware entropy connected to existing scoring. |
| [explorer.py](src/sckg/retrieval/egpot/explorer.py) | MCTS integration, constraints, and richer trace serialization. |
| [serializer.py](src/sckg/retrieval/egpot/serializer.py) | Human-readable mode, provider, simulations, and paths. |
| [pipeline.py](src/sckg/retrieval/pipeline.py) | Shared provider and seed hub filtering. |
| [traversal.py](src/sckg/retrieval/traversal.py) | Hub-aware hybrid expansion. |
| [CLI](src/sckg/cli/main.py) | YAML and flag wiring, traces, and comparison options. |
| [visualization exporter](src/sckg/visualization/export.py) | Standalone HTML with graph data and multiple traces. |
| [trace_panel.js](src/sckg/visualization/trace_panel.js) | Run selection, hop replay, metrics, and MCTS/hub inspection. |
| [verification script](scripts/verify_egpot_week1.py) | Both providers, baseline comparison, and both visual demos. |
| [pyproject.toml](pyproject.toml) | Optional trained-embedding dependency group. |
| [unit tests](tests/unit) and [integration tests](tests/integration) | Behavioural checks and explicit hashing for offline regressions. |
| [README.md](README.md) | Installation and usage instructions. |

The output directory includes `comparison.json`, provider traces, `hub-on-trace.json`, `hub-off-trace.json`, `graph.html`, and `hub-suppression.html`. The repository's `.sckg/graph.html` was also regenerated with comparisons. The original `.sckg/egpot-trace.json` was preserved.

## 15. Current limitations and what comes next

- Global optimality is not guaranteed: pruning and finite simulations can miss useful paths.
- No speedup or millisecond latency is claimed. Simulations and trained embeddings add work that needs profiling.
- A changed trace does not prove higher accuracy.
- Weeks 2-4 baseline traversals, benchmark corpora, experiment runs, and downstream LLM evaluation remain outside this update.
- No LLM is called to answer the question or measure downstream answer quality.
- Python extraction retains its existing conservative static-analysis limitations.
- Entropy, novelty, and contract scoring remain heuristics.
- The default embedding model is general-purpose; code-specific model quality needs separate evaluation.
- Hashing is reproducible, but exact trained-model outputs across hardware and library versions are not guaranteed.
- Visualization replays recorded evidence; it is not a live search backend.

The intended Week 1 mechanisms now run, their settings affect behaviour, and their decisions can be inspected and reproduced. The next stage is to evaluate those decisions against gold-labelled tasks rather than assume that more sophisticated search must produce better answers.
