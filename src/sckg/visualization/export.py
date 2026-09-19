from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path

from sckg.ir.models import Relation, Symbol


@dataclass(frozen=True)
class GraphVisualization:
    nodes: list[dict[str, object]]
    links: list[dict[str, object]]


KIND_COLORS = {
    "file": "#5b8def",
    "class": "#f59e0b",
    "function": "#10b981",
    "method": "#14b8a6",
    "import": "#8b5cf6",
    "variable": "#ef4444",
    "parameter": "#ec4899",
    "field": "#f97316",
    "repository": "#64748b",
    "code_chunk": "#6b7280",
}


def graph_to_visualization(
    symbols: list[Symbol],
    relations: list[Relation],
    egpot_trace: dict[str, object] | None = None,
) -> GraphVisualization:
    symbol_by_id = {symbol.id: symbol for symbol in symbols}
    selected_nodes = set(_trace_ids(egpot_trace, "selected_nodes"))
    seed_nodes = set(_trace_ids(egpot_trace, "seeds"))
    selected_edges = set(_trace_ids(egpot_trace, "selected_edges"))
    objective_scores = egpot_trace.get("objective_scores", {}) if egpot_trace else {}
    if not isinstance(objective_scores, dict):
        objective_scores = {}
    nodes = [
        {
            "id": symbol.id,
            "label": symbol.name,
            "qualifiedName": symbol.qualified_name,
            "kind": symbol.kind.value,
            "file": symbol.file_path,
            "line": symbol.start_line,
            "sourceText": symbol.source_text or "",
            "color": KIND_COLORS.get(symbol.kind.value, "#475569"),
            "egpotSelected": symbol.id in selected_nodes,
            "egpotSeed": symbol.id in seed_nodes,
            "egpotObjectives": objective_scores.get(symbol.id, []),
        }
        for symbol in symbols
    ]
    links = [
        {
            "id": relation.id,
            "source": relation.source_symbol_id,
            "target": relation.target_symbol_id,
            "type": relation.relation_type.value,
            "confidence": relation.confidence,
            "provenance": relation.provenance.value,
            "egpotSelected": relation.id in selected_edges,
        }
        for relation in relations
        if relation.source_symbol_id in symbol_by_id and relation.target_symbol_id in symbol_by_id
    ]
    return GraphVisualization(nodes=nodes, links=links)


def write_graph_html(
    output_path: Path,
    symbols: list[Symbol],
    relations: list[Relation],
    title: str = "SCKG Graph",
    egpot_trace: dict[str, object] | None = None,
    comparison_traces: dict[str, dict[str, object]] | None = None,
) -> Path:
    visualization = graph_to_visualization(symbols, relations, egpot_trace)
    payload = json.dumps(
        {
            "nodes": visualization.nodes,
            "links": visualization.links,
            "egpot": {
                "enabled": egpot_trace is not None,
                "runs": {"Current run": egpot_trace, **(comparison_traces or {})}
                        if egpot_trace is not None else {},
                "query": egpot_trace.get("query", "") if egpot_trace else "",
                "stopReason": egpot_trace.get("stop_reason", "") if egpot_trace else "",
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload = payload.replace("</", "<\\/")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html_document(title, payload), encoding="utf-8")
    return output_path


def _trace_ids(egpot_trace: dict[str, object] | None, key: str) -> list[str]:
    if not egpot_trace:
        return []
    values = egpot_trace.get(key, [])
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def _html_document(title: str, payload: str) -> str:
    escaped_title = html.escape(title)
    trace_panel = Path(__file__).with_name("trace_panel.js").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8fafc;
      --panel: #ffffff;
      --ink: #0f172a;
      --muted: #64748b;
      --line: #dbe3ee;
      --accent: #2563eb;
      --edge: #94a3b8;
      --egpot: #dc2626;
      --egpot-seed: #0891b2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      overflow: hidden;
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    .app {{
      display: grid;
      grid-template-columns: minmax(280px, 340px) 1fr;
      height: 100vh;
    }}
    aside {{
      border-right: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
      overflow: auto;
    }}
    main {{
      position: relative;
      min-width: 0;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 20px;
      font-weight: 700;
    }}
    .stats {{
      color: var(--muted);
      margin-bottom: 18px;
    }}
    label {{
      display: block;
      margin: 14px 0 6px;
      font-weight: 650;
      color: #334155;
    }}
    input, select {{
      width: 100%;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: #fff;
      color: var(--ink);
    }}
    .legend {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px 12px;
      margin-top: 18px;
    }}
    .egpot-summary {{
      display: none;
      margin: 14px 0 0;
      padding: 10px;
      border: 1px solid #fecaca;
      border-radius: 6px;
      background: #fff7f7;
      color: #7f1d1d;
    }}
    .egpot-summary.active {{
      display: block;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      color: #334155;
    }}
    .swatch {{
      width: 11px;
      height: 11px;
      border-radius: 50%;
      flex: 0 0 auto;
    }}
    .details {{
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
      color: #334155;
      word-break: break-word;
    }}
    .details strong {{
      display: block;
      color: var(--ink);
      margin-bottom: 6px;
    }}
    .details-row {{
      margin: 3px 0;
    }}
    .details-code {{
      max-height: 220px;
      overflow: auto;
      margin: 10px 0 0;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #0f172a;
      color: #e2e8f0;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre;
    }}
    .related-block {{
      margin-top: 12px;
    }}
    .related-title {{
      margin-bottom: 6px;
      font-weight: 700;
      color: var(--ink);
    }}
    .related-list {{
      display: grid;
      gap: 6px;
    }}
    .related-item {{
      width: 100%;
      height: auto;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #fff;
      text-align: left;
      cursor: pointer;
    }}
    .related-item:hover {{
      border-color: var(--accent);
      background: #eff6ff;
    }}
    .relation-chip {{
      display: inline-block;
      margin-right: 6px;
      color: #1d4ed8;
      font-size: 12px;
      font-weight: 700;
    }}
    .inspect-section {{
      margin-top: 18px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }}
    .inspect-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
      color: #334155;
      font-weight: 700;
    }}
    .count {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }}
    .item-list {{
      display: grid;
      gap: 6px;
      max-height: 210px;
      overflow: auto;
      padding-right: 2px;
    }}
    .list-item {{
      width: 100%;
      height: auto;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      background: #fff;
      color: #1e293b;
      text-align: left;
      cursor: pointer;
    }}
    .list-item:hover, .list-item.active {{
      border-color: var(--accent);
      background: #eff6ff;
    }}
    .item-name {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 650;
    }}
    .item-meta {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--muted);
      font-size: 12px;
    }}
    svg {{
      display: block;
      width: 100%;
      height: 100vh;
      cursor: grab;
      touch-action: none;
      background:
        linear-gradient(#e2e8f0 1px, transparent 1px),
        linear-gradient(90deg, #e2e8f0 1px, transparent 1px);
      background-size: 32px 32px;
    }}
    svg.dragging {{
      cursor: grabbing;
    }}
    .link {{
      stroke: var(--edge);
      stroke-opacity: 0.42;
    }}
    .link-hit {{
      stroke: transparent;
      stroke-width: 10px;
      cursor: pointer;
    }}
    .link.selected {{
      stroke: var(--accent);
      stroke-opacity: 1;
    }}
    .link.egpot {{
      stroke: var(--egpot);
      stroke-opacity: 0.95;
    }}
    .node circle {{
      stroke: #fff;
      stroke-width: 0.9px;
      opacity: 0.88;
      cursor: pointer;
    }}
    .node .hit-circle {{
      fill: transparent;
      stroke: transparent;
      cursor: pointer;
    }}
    .node.selected circle:not(.hit-circle) {{
      stroke: var(--accent);
      stroke-width: 1.8px;
      opacity: 1;
    }}
    .node.egpot circle:not(.hit-circle) {{
      stroke: var(--egpot);
      stroke-width: 2.4px;
      opacity: 1;
    }}
    .node.egpot-seed circle:not(.hit-circle) {{
      stroke: var(--egpot-seed);
      stroke-width: 2.4px;
    }}
    .node text {{
      pointer-events: none;
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 3px;
      fill: #0f172a;
      font-size: 11px;
    }}
    .edge-label {{
      fill: #64748b;
      font-size: 9px;
      pointer-events: none;
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 3px;
    }}
    .toolbar {{
      position: absolute;
      right: 16px;
      top: 16px;
      display: flex;
      gap: 8px;
    }}
    button {{
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      background: #fff;
      color: #1e293b;
      cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); }}
    @media (max-width: 760px) {{
      .app {{ grid-template-columns: 1fr; grid-template-rows: auto 1fr; }}
      aside {{ max-height: 42vh; border-right: 0; border-bottom: 1px solid var(--line); }}
      svg {{ height: 58vh; }}
      .toolbar {{ top: auto; bottom: 12px; right: 12px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>{escaped_title}</h1>
      <div class="stats" id="stats"></div>
      <div class="egpot-summary" id="egpotSummary"></div>

      <label for="search">Search symbols</label>
      <input id="search" type="search" placeholder="Qualified name, file, kind">

      <label for="relation">Relation filter</label>
      <select id="relation">
        <option value="">All relations</option>
      </select>

      <div class="legend" id="legend"></div>
      <div class="details" id="details">Select a node or edge to inspect it.</div>
      <div class="inspect-section">
        <div class="inspect-title">Nodes <span class="count" id="nodeCount"></span></div>
        <div class="item-list" id="nodeList"></div>
      </div>
      <div class="inspect-section">
        <div class="inspect-title">Edges <span class="count" id="edgeCount"></span></div>
        <div class="item-list" id="edgeList"></div>
      </div>
    </aside>
    <main>
      <div class="toolbar">
        <button id="zoomIn" title="Zoom in">+</button>
        <button id="zoomOut" title="Zoom out">-</button>
        <button id="fit" title="Fit graph to view">Fit</button>
        <button id="labels" title="Toggle labels">Labels</button>
        <button id="egpotOnly" title="Show only EG-POT-selected nodes and edges">EG-POT</button>
      </div>
      <svg id="graph" role="img" aria-label="Interactive semantic code graph"></svg>
    </main>
  </div>
  <script>
    const graph = {payload};
    const svg = document.getElementById("graph");
    const search = document.getElementById("search");
    const relation = document.getElementById("relation");
    const details = document.getElementById("details");
    const stats = document.getElementById("stats");
    const nodeList = document.getElementById("nodeList");
    const edgeList = document.getElementById("edgeList");
    const nodeCount = document.getElementById("nodeCount");
    const edgeCount = document.getElementById("edgeCount");
    const labelsButton = document.getElementById("labels");
    const egpotOnlyButton = document.getElementById("egpotOnly");
    const egpotSummary = document.getElementById("egpotSummary");
    const fitButton = document.getElementById("fit");
    const zoomInButton = document.getElementById("zoomIn");
    const zoomOutButton = document.getElementById("zoomOut");
    const width = () => svg.clientWidth || 900;
    const height = () => svg.clientHeight || 700;
    let showLabels = true;
    let transform = {{x: 0, y: 0, k: 1}};
    let selectedNodeId = "";
    let selectedLinkId = "";
    let egpotOnly = false;
    let viewport = null;
    let latestActive = null;
    let nodes = graph.nodes.map((node, index) => ({{
      ...node,
      x: width() / 2 + Math.cos(index) * 220,
      y: height() / 2 + Math.sin(index) * 220,
      vx: 0,
      vy: 0
    }}));
    let links = graph.links;
    const nodeById = new Map(nodes.map(node => [node.id, node]));
    const relationTypes = [...new Set(links.map(link => link.type))].sort();
    for (const type of relationTypes) {{
      const option = document.createElement("option");
      option.value = type;
      option.textContent = type;
      relation.appendChild(option);
    }}
    const kinds = [...new Map(nodes.map(node => [node.kind, node.color])).entries()].sort();
    document.getElementById("legend").innerHTML = kinds.map(([kind, color]) =>
      `<div class="legend-item"><span class="swatch" style="background:${{color}}"></span><span>${{kind}}</span></div>`
    ).join("") + (graph.egpot.enabled ? `
      <div class="legend-item"><span class="swatch" style="background:var(--egpot)"></span><span>EG-POT selected</span></div>
      <div class="legend-item"><span class="swatch" style="background:var(--egpot-seed)"></span><span>EG-POT seed</span></div>
    ` : "");
    if (graph.egpot.enabled) {{
      const selectedCount = nodes.filter(node => node.egpotSelected).length;
      const seedCount = nodes.filter(node => node.egpotSeed).length;
      const edgeCount = links.filter(link => link.egpotSelected).length;
      egpotSummary.classList.add("active");
      egpotSummary.innerHTML = `<strong>EG-POT trace loaded</strong><br>${{escapeHtml(graph.egpot.query)}}<br>${{selectedCount}} selected nodes, ${{edgeCount}} selected edges, ${{seedCount}} seeds<br>Stop: ${{escapeHtml(graph.egpot.stopReason)}}`;
    }} else {{
      egpotOnlyButton.disabled = true;
      egpotOnlyButton.title = "Regenerate with --egpot-trace to enable this overlay";
    }}

    function filtered() {{
      const q = search.value.trim().toLowerCase();
      const rel = relation.value;
      const visibleNodes = new Set(nodes.filter(node => !q ||
        `${{node.label}} ${{node.qualifiedName}} ${{node.file}} ${{node.kind}}`.toLowerCase().includes(q)
      ).filter(node => !egpotOnly || node.egpotSelected || node.egpotSeed).map(node => node.id));
      const visibleLinks = links.filter(link =>
        (!rel || link.type === rel) &&
        (!egpotOnly || link.egpotSelected) &&
        visibleNodes.has(link.source) &&
        visibleNodes.has(link.target)
      );
      for (const link of visibleLinks) {{
        visibleNodes.add(link.source);
        visibleNodes.add(link.target);
      }}
      return {{
        nodes: nodes.filter(node => visibleNodes.has(node.id)),
        links: visibleLinks
      }};
    }}

    function tick(activeNodes, activeLinks) {{
      const centerX = width() / 2;
      const centerY = height() / 2;
      const iterations = activeNodes.length > 260 ? 2 : 18;
      const useRepulsion = activeNodes.length <= 260;
      for (let i = 0; i < iterations; i++) {{
        for (const node of activeNodes) {{
          node.vx += (centerX - node.x) * 0.0009;
          node.vy += (centerY - node.y) * 0.0009;
        }}
        if (useRepulsion) {{
          for (let a = 0; a < activeNodes.length; a++) {{
            for (let b = a + 1; b < activeNodes.length; b++) {{
              const left = activeNodes[a];
              const right = activeNodes[b];
              const dx = left.x - right.x || 0.1;
              const dy = left.y - right.y || 0.1;
              const d2 = Math.max(80, dx * dx + dy * dy);
              const force = 260 / d2;
              left.vx += dx * force;
              left.vy += dy * force;
              right.vx -= dx * force;
              right.vy -= dy * force;
            }}
          }}
        }}
        for (const link of activeLinks) {{
          const source = nodeById.get(link.source);
          const target = nodeById.get(link.target);
          if (!source || !target) continue;
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const distance = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (distance - 140) * 0.004;
          source.vx += dx / distance * force;
          source.vy += dy / distance * force;
          target.vx -= dx / distance * force;
          target.vy -= dy / distance * force;
        }}
        for (const node of activeNodes) {{
          node.vx *= 0.72;
          node.vy *= 0.72;
          node.x += node.vx;
          node.y += node.vy;
        }}
      }}
    }}

    function render(runLayout = true) {{
      const active = filtered();
      latestActive = active;
      stats.textContent = `${{active.nodes.length}} of ${{nodes.length}} nodes, ${{active.links.length}} of ${{links.length}} relations`;
      if (runLayout) tick(active.nodes, active.links);
      renderLists(active);
      svg.innerHTML = "";
      viewport = document.createElementNS("http://www.w3.org/2000/svg", "g");
      applyViewport();
      svg.appendChild(viewport);

      for (const link of active.links) {{
        const source = nodeById.get(link.source);
        const target = nodeById.get(link.target);
        if (!source || !target) continue;
        const hit = document.createElementNS("http://www.w3.org/2000/svg", "line");
        hit.setAttribute("class", "link-hit");
        hit.setAttribute("x1", source.x);
        hit.setAttribute("y1", source.y);
        hit.setAttribute("x2", target.x);
        hit.setAttribute("y2", target.y);
        hit.addEventListener("pointerdown", event => event.stopPropagation());
        hit.addEventListener("click", event => {{
          event.stopPropagation();
          showEdge(link);
        }});
        viewport.appendChild(hit);
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("class", `link${{link.egpotSelected ? " egpot" : ""}}${{link.id === selectedLinkId ? " selected" : ""}}`);
        line.setAttribute("x1", source.x);
        line.setAttribute("y1", source.y);
        line.setAttribute("x2", target.x);
        line.setAttribute("y2", target.y);
        line.setAttribute("stroke-width", link.id === selectedLinkId ? 2.2 : link.egpotSelected ? 2.6 : Math.max(0.45, link.confidence * 0.95));
        line.addEventListener("pointerdown", event => event.stopPropagation());
        line.addEventListener("click", event => {{
          event.stopPropagation();
          showEdge(link);
        }});
        viewport.appendChild(line);
        if (showLabels && active.links.length < 180) {{
          const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
          label.setAttribute("class", "edge-label");
          label.setAttribute("x", (source.x + target.x) / 2);
          label.setAttribute("y", (source.y + target.y) / 2);
          label.textContent = link.type;
          viewport.appendChild(label);
        }}
      }}

      for (const node of active.nodes) {{
        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        group.setAttribute("class", `node${{node.egpotSelected ? " egpot" : ""}}${{node.egpotSeed ? " egpot-seed" : ""}}${{node.id === selectedNodeId ? " selected" : ""}}`);
        group.setAttribute("transform", `translate(${{node.x}} ${{node.y}})`);
        group.addEventListener("pointerdown", event => event.stopPropagation());
        group.addEventListener("click", event => {{
          event.stopPropagation();
          showNode(node);
        }});
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("r", radius(node));
        circle.setAttribute("fill", node.color);
        group.appendChild(circle);
        const hitCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        hitCircle.setAttribute("class", "hit-circle");
        hitCircle.setAttribute("r", radius(node) + 8);
        group.appendChild(hitCircle);
        if (showLabels && active.nodes.length < 260) {{
          const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
          text.setAttribute("x", radius(node) + 4);
          text.setAttribute("y", 4);
          text.textContent = node.label;
          group.appendChild(text);
        }}
        viewport.appendChild(group);
      }}
    }}

    function applyViewport() {{
      if (!viewport) return;
      viewport.setAttribute("transform", `translate(${{transform.x}} ${{transform.y}}) scale(${{transform.k}})`);
    }}

    function radius(node) {{
      if (node.kind === "file") return 4.4;
      if (node.kind === "class") return 4.1;
      if (node.kind === "method" || node.kind === "function") return 3.8;
      return 3.2;
    }}

    function showNode(node) {{
      selectedNodeId = node.id;
      selectedLinkId = "";
      const incoming = links.filter(link => link.target === node.id);
      const outgoing = links.filter(link => link.source === node.id);
      details.innerHTML = `
        <strong>${{escapeHtml(node.qualifiedName)}}</strong>
        <div class="details-row">Kind: ${{escapeHtml(node.kind)}}</div>
        <div class="details-row">File: ${{escapeHtml(node.file)}}:${{escapeHtml(node.line)}}</div>
        ${{node.egpotSeed ? `<div class="details-row">EG-POT: seed node</div>` : ""}}
        ${{node.egpotSelected ? `<div class="details-row">EG-POT: selected context node</div>` : ""}}
        ${{node.egpotObjectives?.length ? `<div class="details-row">Objectives: sem=${{Number(node.egpotObjectives[0]).toFixed(3)}}, hop=${{Number(node.egpotObjectives[1]).toFixed(3)}}, contract=${{Number(node.egpotObjectives[2]).toFixed(3)}}, info=${{Number(node.egpotObjectives[3]).toFixed(3)}}</div>` : ""}}
        <div class="details-row">Related: ${{incoming.length}} incoming, ${{outgoing.length}} outgoing</div>
        ${{node.sourceText ? `<pre class="details-code">${{escapeHtml(node.sourceText)}}</pre>` : ""}}
        ${{relatedBlock("Outgoing", outgoing, "target")}}
        ${{relatedBlock("Incoming", incoming, "source")}}
      `;
      bindRelatedButtons();
      render(false);
    }}

    function showEdge(link) {{
      selectedLinkId = link.id;
      selectedNodeId = "";
      const source = nodeById.get(link.source);
      const target = nodeById.get(link.target);
      details.innerHTML = `<strong>${{link.type}}</strong>
        <div>${{source?.qualifiedName || link.source}}</div>
        <div>to ${{target?.qualifiedName || link.target}}</div>
        <div>Confidence: ${{Number(link.confidence).toFixed(2)}}</div>
        <div>Provenance: ${{link.provenance}}</div>
        <div>EG-POT selected: ${{link.egpotSelected ? "yes" : "no"}}</div>`;
      render(false);
    }}

    function relatedBlock(title, relatedLinks, oppositeKey) {{
      if (!relatedLinks.length) return "";
      return `
        <div class="related-block">
          <div class="related-title">${{escapeHtml(title)}}</div>
          <div class="related-list">
            ${{relatedLinks.slice(0, 20).map(link => {{
              const related = nodeById.get(link[oppositeKey]);
              return `
                <button class="related-item" data-related-node="${{escapeAttr(related?.id || "")}}">
                  <span class="relation-chip">${{escapeHtml(link.type)}}</span>
                  <span>${{escapeHtml(related?.qualifiedName || link[oppositeKey])}}</span>
                </button>
              `;
            }}).join("")}}
          </div>
        </div>
      `;
    }}

    function bindRelatedButtons() {{
      for (const button of details.querySelectorAll("[data-related-node]")) {{
        button.addEventListener("click", () => {{
          const node = nodeById.get(button.getAttribute("data-related-node"));
          if (node) {{
            centerOn(node);
            showNode(node);
          }}
        }});
      }}
    }}

    function renderLists(active) {{
      nodeCount.textContent = `${{active.nodes.length}} visible`;
      edgeCount.textContent = `${{active.links.length}} visible`;
      nodeList.innerHTML = active.nodes.slice(0, 120).map(node => `
        <button class="list-item${{node.id === selectedNodeId ? " active" : ""}}" data-node="${{escapeAttr(node.id)}}">
          <span class="item-name">${{escapeHtml(node.label)}}</span>
          <span class="item-meta">${{escapeHtml(node.kind)}} · ${{escapeHtml(node.qualifiedName)}}</span>
        </button>
      `).join("");
      edgeList.innerHTML = active.links.slice(0, 120).map(link => {{
        const source = nodeById.get(link.source);
        const target = nodeById.get(link.target);
        return `
          <button class="list-item${{link.id === selectedLinkId ? " active" : ""}}" data-edge="${{escapeAttr(link.id)}}">
            <span class="item-name">${{escapeHtml(link.type)}}</span>
            <span class="item-meta">${{escapeHtml(source?.label || link.source)}} -> ${{escapeHtml(target?.label || link.target)}}</span>
          </button>
        `;
      }}).join("");
      for (const button of nodeList.querySelectorAll("[data-node]")) {{
        button.addEventListener("click", () => {{
          const node = nodeById.get(button.getAttribute("data-node"));
          if (node) {{
            centerOn(node);
            showNode(node);
          }}
        }});
      }}
      for (const button of edgeList.querySelectorAll("[data-edge]")) {{
        button.addEventListener("click", () => {{
          const link = links.find(item => item.id === button.getAttribute("data-edge"));
          if (link) {{
            const source = nodeById.get(link.source);
            const target = nodeById.get(link.target);
            if (source && target) centerOn({{x: (source.x + target.x) / 2, y: (source.y + target.y) / 2}});
            showEdge(link);
          }}
        }});
      }}
    }}

    function centerOn(point) {{
      transform.x = width() / 2 - point.x * transform.k;
      transform.y = height() / 2 - point.y * transform.k;
      applyViewport();
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, char => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\\"": "&quot;",
        "'": "&#39;"
      }}[char]));
    }}

    function escapeAttr(value) {{
      return escapeHtml(value);
    }}

    function fit() {{
      const active = filtered().nodes;
      if (!active.length) return;
      const xs = active.map(node => node.x);
      const ys = active.map(node => node.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      const minY = Math.min(...ys), maxY = Math.max(...ys);
      const graphWidth = Math.max(1, maxX - minX);
      const graphHeight = Math.max(1, maxY - minY);
      const k = Math.min(width() / graphWidth, height() / graphHeight, 1.4) * 0.82;
      transform = {{
        k,
        x: width() / 2 - (minX + graphWidth / 2) * k,
        y: height() / 2 - (minY + graphHeight / 2) * k
      }};
      render(false);
    }}

    function zoomAt(clientX, clientY, scaleFactor) {{
      const bounds = svg.getBoundingClientRect();
      const cursorX = clientX - bounds.left;
      const cursorY = clientY - bounds.top;
      const worldX = (cursorX - transform.x) / transform.k;
      const worldY = (cursorY - transform.y) / transform.k;
      const nextK = Math.max(0.18, Math.min(5.5, transform.k * scaleFactor));
      transform.x = cursorX - worldX * nextK;
      transform.y = cursorY - worldY * nextK;
      transform.k = nextK;
      applyViewport();
    }}

    function zoomAtCenter(scaleFactor) {{
      const bounds = svg.getBoundingClientRect();
      zoomAt(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2, scaleFactor);
    }}

    let dragging = null;
    svg.addEventListener("pointerdown", event => {{
      if (event.button !== 0) return;
      dragging = {{
        pointerX: event.clientX,
        pointerY: event.clientY,
        startX: transform.x,
        startY: transform.y
      }};
      svg.classList.add("dragging");
      svg.setPointerCapture(event.pointerId);
    }});
    svg.addEventListener("pointermove", event => {{
      if (!dragging) return;
      transform.x = dragging.startX + event.clientX - dragging.pointerX;
      transform.y = dragging.startY + event.clientY - dragging.pointerY;
      applyViewport();
    }});
    svg.addEventListener("pointerup", () => {{
      dragging = null;
      svg.classList.remove("dragging");
    }});
    svg.addEventListener("pointercancel", () => {{
      dragging = null;
      svg.classList.remove("dragging");
    }});
    svg.addEventListener("wheel", event => {{
      event.preventDefault();
      const scaleFactor = Math.exp(-event.deltaY * 0.0015);
      zoomAt(event.clientX, event.clientY, scaleFactor);
    }}, {{passive: false}});
    search.addEventListener("input", () => render(true));
    relation.addEventListener("change", () => render(true));
    labelsButton.addEventListener("click", () => {{
      showLabels = !showLabels;
      render(false);
    }});
    egpotOnlyButton.addEventListener("click", () => {{
      egpotOnly = !egpotOnly;
      egpotOnlyButton.textContent = egpotOnly ? "All" : "EG-POT";
      render(true);
      setTimeout(fit, 20);
    }});
    zoomInButton.addEventListener("click", () => zoomAtCenter(1.2));
    zoomOutButton.addEventListener("click", () => zoomAtCenter(1 / 1.2));
    fitButton.addEventListener("click", fit);
    window.addEventListener("resize", () => render(false));
    render();
    setTimeout(fit, 60);
    {trace_panel}
  </script>
</body>
</html>
"""
