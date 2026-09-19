// Replay saved retrieval evidence. Controls never pretend to rerun inference.
(() => {
  const runs = Object.entries(graph.egpot.runs || {});
  if (!runs.length) return;
  const style = document.createElement('style');
  style.textContent = `
    .run-panel { margin-top:16px; padding-top:14px; border-top:1px solid var(--line); }
    .run-panel h2 { font-size:16px; margin:0 0 4px; }
    .run-note { color:#64748b; font-size:12px; margin:6px 0; }
    .run-metrics { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:12px 0; }
    .run-metric { padding:9px; background:#f1f5f9; border-radius:7px; overflow-wrap:anywhere; }
    .run-metric b { display:block; color:#0f172a; font-size:17px; }
    .run-metric span { font-size:11px; color:#475569; }
    .run-path { line-height:1.8; overflow-wrap:anywhere; padding:8px; background:#eff6ff; border-radius:6px; }
    .run-tree { max-height:190px; overflow:auto; }
    .run-tree button { margin:3px 0; width:100%; height:auto; padding:8px; text-align:left; overflow-wrap:anywhere; }
    .node.hub circle:not(.hit-circle) { stroke:#d97706; stroke-width:3; stroke-dasharray:2 2; }
    .node.suppressed circle:not(.hit-circle) { fill:#fef3c7; opacity:.5; }
    .run-panel input[type=range] { padding:0; }
  `;
  document.head.appendChild(style);
  const panel = document.createElement('section');
  panel.className = 'run-panel';
  panel.innerHTML = `
    <h2>Search evidence</h2>
    <p class="run-note">Recorded runs from the Python retrieval engine. Choose a run to compare its actual results.</p>
    <label for="runSelect">Recorded run</label><select id="runSelect"></select>
    <div class="run-metrics" id="runMetrics"></div>
    <p class="run-note" id="hubStatus"></p>
    <p class="run-note" id="runDifference"></p>
    <label for="pathSelect">Selected trajectory</label><select id="pathSelect"></select>
    <label for="hopStep" id="hopLabel">Replay hops</label>
    <input id="hopStep" type="range" min="0" value="0" aria-label="Replay hops">
    <div class="run-path" id="pathDescription"></div>
    <p class="run-note">Red outlines: selected path. Cyan: seed. Amber dashes: high in-degree hub. Use All to inspect excluded nodes.</p>
    <details><summary>MCTS visits and values</summary><p class="run-note">Each row is a trajectory-tree state. Values are mean backpropagated rewards; they are not probabilities.</p><div class="run-tree" id="runTree"></div></details>
  `;
  egpotSummary.after(panel);
  const el = id => document.getElementById(id);
  const runSelect = el('runSelect'), pathSelect = el('pathSelect'), hopStep = el('hopStep');
  runs.forEach(([label], index) => runSelect.add(new Option(label, String(index))));
  let current = runs[0][1], paths = [], suppressed = new Set();
  const incoming = new Map(nodes.map(n => [n.id, new Set()]));
  for (const edge of links) if (edge.source !== edge.target) incoming.get(edge.target)?.add(edge.source);
  const name = id => nodeById.get(id)?.qualifiedName || id;
  const metric = (label, value) => `<div class="run-metric"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`;
  const originalShowNode = showNode;
  showNode = function(node) {
    originalShowNode(node);
    const row = document.createElement('div');
    row.className = 'details-row';
    row.textContent = `In-degree in displayed graph: ${incoming.get(node.id)?.size || 0}. ${suppressed.has(node.id) ? 'Excluded as a hub in this run.' : node.isHub ? 'Above this run’s hub threshold.' : ''}`;
    details.prepend(row);
    decorate();
  };
  const originalRender = render;
  render = function(...args) { originalRender(...args); decorate(); };
  function decorate() {
    if (!latestActive) return;
    // Node groups are created in the same order as filtered graph nodes.
    const visible = filtered().nodes;
    svg.querySelectorAll('g.node').forEach((group, index) => {
      const node = visible[index];
      group.classList.toggle('hub', Boolean(node?.isHub));
      group.classList.toggle('suppressed', suppressed.has(node?.id));
    });
  }
  function chooseRun() {
    current = runs[Number(runSelect.value)][1];
    const searchInfo = current.search || {};
    suppressed = new Set(searchInfo.suppressed_hubs || []);
    const selected = new Set(current.selected_nodes || []);
    const baseline = new Set(runs[runs.length - 1][1].selected_nodes || []);
    const added = [...selected].filter(id => !baseline.has(id)).length;
    const removed = [...baseline].filter(id => !selected.has(id)).length;
    const mode = searchInfo.mcts_enabled === true ? 'Beam-MCTS' : searchInfo.mcts_enabled === false ? 'Pareto beam' : 'Legacy trace';
    el('runMetrics').innerHTML = metric('Search', mode) + metric('Simulations', searchInfo.simulations ?? 'Not recorded') + metric('Embedding provider', searchInfo.embedding_provider ?? 'Not recorded') + metric('Selected nodes', selected.size);
    egpotSummary.innerHTML = `<strong>EG-POT trace loaded</strong><br>${escapeHtml(current.query || '')}<br>Stop: ${escapeHtml(current.stop_reason || '')}`;
    el('hubStatus').textContent = searchInfo.hub_suppression_enabled === undefined
      ? 'Hub settings were not recorded in this older trace.'
      : `Hub suppression ${searchInfo.hub_suppression_enabled ? 'ON' : 'OFF'} · threshold > ${searchInfo.hub_degree_threshold} · ${suppressed.size} encountered hubs excluded.`;
    el('runDifference').textContent = runs.length > 1 ? `Compared with ${runs[runs.length - 1][0]}: ${added} added, ${removed} removed nodes. Paths can change even when node sets match.` : '';
    nodes.forEach(node => {
      node.egpotSeed = (current.seeds || []).includes(node.id);
      node.egpotObjectives = current.objective_scores?.[node.id] || [];
      node.isHub = searchInfo.hub_degree_threshold !== undefined && incoming.get(node.id).size > searchInfo.hub_degree_threshold;
    });
    paths = current.trajectories || [];
    pathSelect.replaceChildren(new Option('All selected context', '-1'));
    paths.forEach((path, index) => pathSelect.add(new Option(`Path ${index + 1} · ${path.edges.length} hops · ${name(path.nodes[path.nodes.length - 1])}`, String(index))));
    pathSelect.value = '-1';
    const tree = searchInfo.tree || [];
    el('runTree').replaceChildren();
    if (!tree.length) el('runTree').textContent = 'No MCTS tree recorded in this run.';
    tree.forEach(row => {
      const button = document.createElement('button');
      button.textContent = `${row.path.map(name).join(' → ')} | visits ${row.visits} | value ${Number(row.mean_value).toFixed(3)} | prior ${Number(row.prior).toFixed(3)}`;
      button.onclick = () => { const node = nodeById.get(row.path[row.path.length - 1]); if (node) showNode(node); };
      el('runTree').appendChild(button);
    });
    selectedNodeId = ''; selectedLinkId = '';
    details.textContent = 'Select a node or edge to inspect it.';
    choosePath();
  }
  function choosePath() {
    const path = paths[Number(pathSelect.value)];
    hopStep.disabled = !path;
    hopStep.max = path ? path.edges.length : 0;
    hopStep.value = hopStep.max;
    replay();
  }
  function replay() {
    const path = paths[Number(pathSelect.value)], step = Number(hopStep.value);
    const nodeIds = new Set(path ? path.nodes.slice(0, step + 1) : current.selected_nodes || []);
    const edgeIds = new Set(path ? path.edges.slice(0, step) : current.selected_edges || []);
    nodes.forEach(node => {
      node.egpotSelected = nodeIds.has(node.id);
      node.egpotSeed = (current.seeds || []).includes(node.id) && (!path || nodeIds.has(node.id));
    });
    links.forEach(link => { link.egpotSelected = edgeIds.has(link.id); });
    el('hopLabel').textContent = path ? `Replay: hop ${step} of ${path.edges.length}` : 'Replay hops';
    el('pathDescription').textContent = path ? path.nodes.slice(0, step + 1).map(name).join(' → ') : paths.length ? 'Choose a trajectory, then drag the slider to follow each hop.' : 'This older trace stores the selected subgraph but no ordered paths.';
    render(false); fit();
  }
  runSelect.addEventListener('change', chooseRun);
  pathSelect.addEventListener('change', choosePath);
  hopStep.addEventListener('input', replay);
  egpotOnly = true;
  egpotOnlyButton.textContent = 'All';
  chooseRun();
})();
