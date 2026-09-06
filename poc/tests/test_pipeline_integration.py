"""Hardware-independent integration test for the dataset-to-DP path."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.dataset import DatasetLoader
from core.privacy import DP_KSA_Filter
from core.scheduler import AdaptiveScheduler


def test_dataset_scheduler_and_filter_pipeline_without_model(
    tmp_path: Path,
) -> None:
    records = [
        {
            "id": f"doc-{index}",
            "argomento": "storia",
            "domanda": "Who won?",
            "contesto": f"Context {index}",
            "risposte_corrette": ["winner"],
            "token_stimati": 32 + index,
        }
        for index in range(5)
    ]
    dataset_path = tmp_path / "benchmark.json"
    dataset_path.write_text(json.dumps(records), encoding="utf-8")

    loader = DatasetLoader(dataset_path)
    candidates = loader.ottieni_campione_ensemble(n=5, seed=17)
    scheduler = AdaptiveScheduler(n_min=3, n_max=5, max_tokens=10)
    decision = scheduler.schedule(
        [documento.token_stimati for documento in candidates],
        epsilon_budget=2.0,
        latenza_massima_ms=10_000.0,
    )
    selected = candidates[: decision.n_ensemble]
    drafts = [
        "alpha beta context" if index < 3 else "alpha gamma context"
        for index, _documento in enumerate(selected)
    ]

    filtro = DP_KSA_Filter(
        epsilon=2.0,
        delta=1e-4,
        sigma=100.0,
        r_min_k=1,
        r_max_k=2,
        epsilon_find_best_k=0.2,
        epsilon_top_k_ptr=0.2,
        rng=np.random.default_rng(23),
    )
    result = filtro.filtra(drafts)

    assert 3 <= decision.n_ensemble <= 5
    assert result.numero_invocazione == 1
    assert set(result.conteggi_reali) == {"alpha", "beta", "context", "gamma"}
    assert result.k_hat in {1, 2}
    assert result.budget_consumato_epsilon <= result.epsilon_budget
    assert result.epsilon_rimasto >= 0.0
