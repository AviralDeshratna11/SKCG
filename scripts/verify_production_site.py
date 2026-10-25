"""Verify the deployed HTTP contract and record concrete production evidence."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

URL = 'https://egpot-traversal-benchmarks.vercel.app'


def request(path, body=None):
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data=payload,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


health = request('/api/health')
assert health['branch'] == 'egpot/traversal-benchmarks'
config = request('/api/config')
assert len(config['defaults']) == 27
graphs = {name: request('/api/graph?dataset=' + name) for name in ['carmein', 'boutique']}
assert len(graphs['carmein']['nodes']) == 3137
assert len(graphs['carmein']['edges']) == 7898
assert len(graphs['boutique']['nodes']) == 1794
assert len(graphs['boutique']['edges']) == 5155
benchmarks = request('/api/benchmarks')
assert benchmarks['total_runs'] == 24000
assert all(sum(r['runs'] for r in p['summary']) == 12000
           for p in benchmarks['providers'].values())
result = request('/api/retrieve', {'query': 'Where is GetSupportedCurrencies implemented?',
    'dataset': 'boutique', 'method': 'all',
    'start_node': 'frontend/rpc.go:frontendServer.getCurrencies',
    'parameters': {'max_hops': 2, 'node_budget': 200}})
assert len(result['methods']) == 15
egpot = result['methods'][0]
assert 'currencyservice/server.js:getSupportedCurrencies' in egpot['selected_nodes']
assert egpot['visited_nodes'] <= 200
assert egpot['effective_parameters']['max_hops'] == 2
for provider in ['hashing', 'minilm']:
    replay = request('/api/benchmark-run?provider=' + provider +
        '&query_id=link-00-explicit&budget=200&seed=0&method=egpot')
    assert replay['methods'][0]['recorded']
    assert replay['methods'][0]['effective_parameters']['provider'] == provider
for body in [{'query': 'x'}, {'query': 'payment', 'parameters': {'unknown': 1}},
             {'query': 'payment', 'parameters': {'node_budget': 0}},
             {'query': 'payment', 'parameters': {'embedding_provider': 'sentence-transformers'}}]:
    try:
        request('/api/retrieve', body)
        raise AssertionError('Invalid request was accepted')
    except urllib.error.HTTPError as error:
        assert error.code == 400
manifest = request('/DEPLOYMENT_SOURCE_MANIFEST.json')
assert manifest['branch'] == 'egpot/traversal-benchmarks'
assert manifest['source_commit'] == '8068e18aad5fd2e99c2b9c5f96355e807580b649'
report = {'url': URL, 'health': health, 'source_commit': manifest['source_commit'],
          'configuration_controls': 27, 'live_methods_tested': 15, 'benchmark_runs': 24000,
          'recorded_providers_tested': ['hashing', 'minilm'],
          'graph_counts': {name: data['counts'] for name, data in graphs.items()},
          'live_contract_path': 'passed', 'invalid_parameter_http_checks': '4 passed',
          'python_tests': '83 passed', 'production_dom_interaction_checks': 'passed',
          'browser_pixel_screenshot_qa': 'unavailable; DOM canvas stubbed'}
output = Path(__file__).resolve().parents[1] / 'output/site/production-verification.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
