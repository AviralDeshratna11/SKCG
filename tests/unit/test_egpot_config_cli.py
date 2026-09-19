from pathlib import Path

import pytest
from typer.testing import CliRunner

from sckg.cli.main import app
from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.pipeline import RetrievalPipeline
from sckg.graph.json_store import JsonGraphStore
from sckg.utils.config import load_yaml


def test_yaml_exposes_week_one_settings():
    config = EGPOTConfig.from_dict(load_yaml(Path('configs/egpot.yaml')))
    assert config.mcts_enabled
    assert config.simulation_budget == 64
    assert config.embedding_provider == 'sentence-transformers'
    assert config.hub_degree_threshold == 10
    assert EGPOTConfig.from_dict({'hub_suppression_enabled': False}).hub_suppression_enabled is False


@pytest.mark.parametrize('kwargs', [
    {'simulation_budget': 0}, {'beam_width': 0}, {'max_hops': -1},
    {'hub_degree_threshold': 0}, {'ucb_c': float('nan')},
    {'objective_weights': (1, 2)}, {'objective_weights': (0, 0, 0, 0)},
    {'objective_weights': (-1, 1, 1, 1)}, {'embedding_provider': 'typo'},
])
def test_invalid_search_config_rejected(kwargs):
    with pytest.raises(ValueError):
        EGPOTConfig(**kwargs)


def test_cli_config_and_overrides_reach_trace(tmp_path, monkeypatch):
    monkeypatch.setenv('SCKG_JSON_STORE', str(tmp_path / 'graph.json'))
    monkeypatch.setenv('SCKG_STORE', 'json')
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'auth.py').write_text('def validate(token):\n    return refresh(token)\n\ndef refresh(token):\n    return token\n')
    runner = CliRunner()
    assert runner.invoke(app, ['index', str(repo)]).exit_code == 0
    config = tmp_path / 'config.yaml'
    config.write_text('egpot:\n  simulation_budget: 7\n  embedding_provider: sentence-transformers\n')
    trace = tmp_path / 'trace.json'
    result = runner.invoke(app, ['retrieve', 'refresh token', '--repo', str(repo), '--strategy', 'egpot',
                                 '--config', str(config), '--use-hash-sim', '--suppress-hubs',
                                 '--hub-degree-threshold', '50', '--simulation-budget', '9',
                                 '--explain', '--trace', str(trace)])
    assert result.exit_code == 0, result.output
    assert 'Search: Beam-MCTS' in result.output
    assert 'Simulations: 9' in result.output
    import json
    payload = json.loads(trace.read_text())
    assert payload['search']['embedding_provider'] == 'hashing'
    assert payload['search']['simulations'] == 9
    legacy = runner.invoke(app, ['retrieve', 'refresh token', '--repo', str(repo),
                                 '--strategy', 'egpot', '--no-mcts', '--use-hash-sim', '--explain'])
    assert legacy.exit_code == 0, legacy.output
    assert 'Search: Pareto beam' in legacy.output


def test_pipeline_provider_selected_from_config(tmp_path):
    pipeline = RetrievalPipeline(JsonGraphStore(tmp_path / 'graph.json'), tmp_path,
                                  {'egpot': {'embedding_provider': 'hashing'}})
    assert pipeline.semantic.provider.__class__.__name__ == 'HashingEmbeddingProvider'
