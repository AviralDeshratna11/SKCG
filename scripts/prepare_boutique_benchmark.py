"""Materialize exact gold IDs from reviewed service labels, never retrieval output."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


TARGETS = {
    'GetSupportedCurrencies': 'currencyservice/server.js:getSupportedCurrencies',
    'Convert': 'currencyservice/server.js:convert',
    'ListProducts': 'productcatalogservice/product_catalog.go:productCatalog.ListProducts',
    'GetProduct': 'productcatalogservice/product_catalog.go:productCatalog.GetProduct',
    'GetQuote': 'shippingservice/main.go:server.GetQuote',
    'ListRecommendations': 'recommendationservice/recommendation_server.py:RecommendationService.ListRecommendations',
    'PlaceOrder': 'checkoutservice/main.go:checkoutService.PlaceOrder',
    'Charge': 'paymentservice/server.js:HipsterShopServer.ChargeServiceHandler',
    'SendOrderConfirmation': 'emailservice/email_server.py:EmailService.SendOrderConfirmation',
    'ShipOrder': 'shippingservice/main.go:server.ShipOrder',
}
INDIRECT = {
    'GetSupportedCurrencies': 'Which service supplies the available currency choices for display?',
    'Convert': 'Which implementation exchanges a money amount into another currency?',
    'ListProducts': 'Where is the available merchandise catalog supplied?',
    'GetProduct': 'Where are the details for a single merchandise item fetched?',
    'GetQuote': 'Which service calculates the delivery price before an order is sent?',
    'ListRecommendations': 'Where are suggested merchandise items chosen?',
    'PlaceOrder': 'Where is a shopper purchase finalized across the backend services?',
    'Charge': 'Where is the customer credit card charged during checkout?',
    'SendOrderConfirmation': 'Where is the purchase receipt notification sent to the customer?',
    'ShipOrder': 'Where is a purchased order dispatched and assigned tracking?',
}


def main() -> None:
    graph_path = Path('.reference-sckg-build/online_boutique_graph.json')
    labels_path = Path('.reference-sckg-build/bench/labels/online_boutique_contracts.json')
    source_root = Path('tmp/online-boutique')
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    nodes = {n['id']: n for n in graph['nodes']}
    labels = json.loads(labels_path.read_text(encoding='utf-8'))
    rows = []
    evidence = {}
    for i, label in enumerate(c for c in labels['consumers'] if c['service'] not in {'CartService', 'AdService'}):
        start = label['consumer'].removeprefix('src/')
        rpc = label['rpc']
        target = TARGETS[rpc]
        contract = f"contract::{label['service']}.{rpc}"
        for node_id in [start, target]:
            n = nodes[node_id]  # Missing exact IDs fail; no substring target matching.
            source = source_root / 'src' / n['file']
            lines = source.read_text(encoding='utf-8').splitlines()
            name = node_id.split(':')[-1].split('.')[-1]
            # Evidence is recorded for review, never used to route search.
            matches = [j + 1 for j, line in enumerate(lines) if name in line]
            if not matches:
                raise ValueError(f'No source evidence for {node_id}')
            evidence[node_id] = {'source': str(source), 'graph_line': n['line'],
                                 'source_occurrence_lines': matches}
        for kind in ['explicit', 'indirect']:
            query = (f"In Online Boutique, where is {rpc} implemented for {start.split(':')[-1]}?"
                     if kind == 'explicit' else INDIRECT[rpc])
            rows.append({'id': f'link-{i:02d}-{kind}', 'query': query, 'kind': kind,
                         # Split by link; paired phrasings never straddle dev/test.
                         'split': 'dev' if i < 5 else 'test', 'start': start,
                         'target': target, 'path': [start, contract, target]})
    output = Path('benchmarks/online-boutique.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({
        'description': '30 source-checked queries, 15 links, 10 producer handlers. Fixed split; no tuning performed.',
        'label_source': str(labels_path), 'graph_source': str(graph_path),
        'source_commit': subprocess.check_output(['git', '-C', str(source_root), 'rev-parse', 'HEAD'], text=True).strip(),
        'limitation': 'Existing graph export and current source may differ in line locations; graph not rebuilt. Expected contract paths can contain missing graph edges; these are graph gaps, not injected edges.',
        'evidence': evidence, 'queries': rows}, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
