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
