"""Tests for random and seeded benchmark sampling."""

from __future__ import annotations

from core.dataset import DatasetLoader


def test_unseeded_ensemble_samples_are_not_constant() -> None:
    loader = DatasetLoader()
    same_sample_count = 0
    for _ in range(1_000):
        first = tuple(document.id for document in loader.ottieni_campione_ensemble(5))
        second = tuple(document.id for document in loader.ottieni_campione_ensemble(5))
        same_sample_count += first == second
    assert same_sample_count / 1_000 < 0.01


def test_seeded_ensemble_sampling_is_reproducible() -> None:
    loader = DatasetLoader()
    first = loader.ottieni_campione_ensemble(5, seed=42)
    second = loader.ottieni_campione_ensemble(5, seed=42)
    assert first == second


def test_repeated_question_rows_are_one_original_document(tmp_path):
    import json
    base = {'id': 'one', 'argomento': 'topic', 'domanda': 'query',
            'contesto': 'same original document', 'risposte_corrette': ['answer'], 'token_stimati': 3}
    path = tmp_path / 'benchmark.json'
    path.write_text(json.dumps([base, {**base, 'id': 'two', 'domanda': 'another query'}]))
    loader = DatasetLoader(path)
    assert len(loader.documenti) == 1
    assert loader.duplicates_removed == 1


def test_fetched_dataset_samples_unique_contexts_not_question_rows(monkeypatch):
    from types import SimpleNamespace

    import requests

    from scripts.fetch_real_dataset import fetch_squad_samples
    payload = {'data': [{'title': 'topic', 'paragraphs': [
        {'context': f'context {i}', 'qas': [{'id': str(i), 'question': 'query',
                                           'answers': [{'text': 'answer'}]}]}
        for i in [0, 0, 1, 2, 3, 4]
    ]}]}
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: payload))
    result = fetch_squad_samples(5)
    assert len(result) == len({row['contesto'] for row in result}) == 5
