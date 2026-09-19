import math
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sckg.retrieval.embeddings import SentenceTransformerEmbeddingProvider
from sckg.retrieval.semantic import HashingEmbeddingProvider, cosine, make_embedding_provider


@pytest.mark.parametrize('name', ['hashing', 'sentence-transformers'])
def test_provider_contract_and_lazy_cache(name, monkeypatch):
    calls = []
    class Model:
        def __init__(self, *args, **kwargs):
            calls.append('load')
        def encode(self, text, **kwargs):
            calls.append(text)
            return [0.6, 0.8]
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=Model))
    provider = make_embedding_provider(name)
    assert not calls
    vector = provider.embed('function token')
    assert all(math.isfinite(v) for v in vector)
    assert sum(v*v for v in vector) == pytest.approx(1)
    assert cosine(vector, vector) == pytest.approx(1)
    assert provider.embed('function token') == vector
    if name == 'sentence-transformers':
        assert calls == ['load', 'function token']


def test_hashing_reproducible_across_processes():
    command = [sys.executable, '-c', 'from sckg.retrieval.semantic import HashingEmbeddingProvider; print(HashingEmbeddingProvider().embed("auth token refresh"))']
    outputs = [subprocess.check_output(command, env={**os.environ, 'PYTHONPATH': 'src', 'PYTHONHASHSEED': seed})
               for seed in ['1', '987']]
    assert outputs[0] == outputs[1]


def test_cosine_handles_unnormalized_and_empty_vectors():
    assert cosine([3, 4], [6, 8]) == pytest.approx(1)
    assert cosine([0, 0], [1, 1]) == 0
    assert cosine([], []) == 0
    with pytest.raises(ValueError):
        cosine([1], [1, 2])


def test_missing_model_has_actionable_offline_fallback(monkeypatch):
    def missing(*args, **kwargs):
        raise OSError('missing local model')
    monkeypatch.setitem(sys.modules, 'sentence_transformers', SimpleNamespace(SentenceTransformer=missing))
    with pytest.raises(RuntimeError, match='--use-hash-sim'):
        SentenceTransformerEmbeddingProvider(local_files_only=True).embed('q')
    assert HashingEmbeddingProvider().embed('q')


@pytest.mark.skipif(os.getenv('SCKG_TEST_REAL_EMBEDDINGS') != '1', reason='opt-in cached model integration')
def test_real_model_ranks_similar_code_above_unrelated():
    provider = SentenceTransformerEmbeddingProvider(local_files_only=True)
    query = provider.embed('def add(a, b): return a + b')
    similar = provider.embed('def sum_numbers(x, y): return x + y')
    unrelated = provider.embed('def delete_file(path): os.remove(path)')
    assert cosine(query, similar) > cosine(query, unrelated)
