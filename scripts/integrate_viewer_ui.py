from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'site/graph-builder/viewer/index.html'
source = path.read_text(encoding='utf-8')
if 'id="dataset"' in source:
    raise SystemExit('Viewer already integrated')
source = source.replace('</head>', '<link rel="stylesheet" href="/viewer/egpot-ui.css">\n</head>')
source = source.replace('<main>', '''<main>
<div class="run-toolbar"><label>Graph <select id="dataset"><option value="carmein">Carmein · deployed snapshot</option><option value="boutique">Online Boutique · benchmark snapshot</option></select></label><span id="runMode" class="run-badge">Live graph</span><span id="graphEvidence" class="muted"></span></div>''')
source = source.replace('<h2>Retrieve affected code</h2>', '''<h2>Retrieve affected code</h2>
<label class="field">Run method<select id="runMethod"><option value="EGPOT">EG-POT · Pareto Beam-MCTS</option><option value="all">Compare EG-POT + R0–R13</option></select></label>
<label class="field">Start node (optional exact ID)<input id="startNode" placeholder="Automatic lexical + semantic localization"></label><button id="useStart" type="button">Use inspected node as start</button>
<details class="parameter-panel"><summary>Traversal parameters</summary><p id="providerNote" class="footnote"></p><div id="parameterFields" class="parameter-grid"></div><button id="resetParameters" type="button">Reset defaults</button><p class="footnote">Layer buttons on the map filter the drawing. Allowed edges here control traversal.</p></details>''')
source = source.replace('<h3 style="margin-top:12px">Candidate files</h3>', '''<details class="parameter-panel"><summary>Effective parameters</summary><pre id="effectiveParameters">Run a query to inspect settings.</pre></details>
<div id="pathPanel" hidden><h3>Traversal paths</h3><label class="field">Path<select id="pathChoice"></select></label><label class="field">Replay hops <input id="hopRange" type="range" min="0" value="0"><span id="hopCount"></span></label><div id="hopDetails" class="hop-details"></div></div>
<h3 style="margin-top:12px">Candidate files</h3>''')
source = source.replace('</main>', '''<section class="benchmark-panel side-card" aria-label="Recorded benchmark results">
<div class="benchmark-heading"><div><div class="eyebrow">Reproducible evaluation</div><h2>Traversal benchmarks</h2></div><span class="run-badge">24,000 recorded runs</span></div>
<p id="benchmarkScope">Loading recorded benchmark evidence…</p>
<div class="benchmark-controls"><label>Provider<select id="benchProvider"><option value="hashing">Hashing · BLAKE2</option><option value="minilm">MiniLM · recorded model</option></select></label><label>Node budget<select id="benchBudget"><option>20</option><option>40</option><option>60</option><option>100</option><option selected>200</option></select></label><label>Split<select id="benchSplit"><option value="test">Held-out test</option><option value="dev">Development</option></select></label></div>
<div class="table-scroll"><table><thead><tr><th>Method</th><th>Target hit</th><th>MRR@5</th><th>Hits@1</th><th>Hits@5</th><th>Path coverage</th><th>Ordered path</th><th>Latency ms</th><th>Visited</th></tr></thead><tbody id="benchmarkRows"></tbody></table></div>
<h3>Replay an actual benchmark run</h3><div class="benchmark-controls"><label class="wide">Query<select id="benchQuery"></select></label><label>Method<select id="benchMethod"></select></label><label>Seed<select id="benchSeed"><option>0</option><option>1</option><option>2</option><option>3</option><option>4</option></select></label><button id="replayBenchmark" type="button">Replay on graph</button></div>
<p id="benchmarkReplayStatus" class="query-status" aria-live="polite"></p><p class="footnote">Replays use the exact Online Boutique snapshot and saved selections. Gold targets are shown for evaluation only. MiniLM replay does not run a neural model in the live service. Expanded-budget uses twice the displayed cap. Latencies are local measurements, not server performance guarantees.</p>
<details class="parameter-panel"><summary>Existing shrey branch experiments · separate fixtures</summary><div id="branchBenchmarks"></div></details>
</section></main>''')
assert 'start();' in source
source = source.replace('start();', '// Bootstrapped by egpot-ui.js')
source = source.replace('</body>', '<script src="/viewer/egpot-ui.js"></script>\n</body>')
path.write_text(source, encoding='utf-8')
print(path)
