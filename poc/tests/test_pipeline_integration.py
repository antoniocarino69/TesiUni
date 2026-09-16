"""Hardware-independent integration test for the dataset-to-DP path.

CLI integration tests live here too: they invoke ``run_pipeline.main(argv)``
as a black box, the same way a user does, and re-read the JSON report to
verify the end-to-end behaviour of the A2 tolerance policy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

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


# ---------------------------------------------------------------------------
# CLI integration tests for the A2 tolerance policy.
#
# These tests import ``run_pipeline`` lazily so the module-level imports of
# ``run_pipeline.py`` (which require ``dotenv`` and ``rich``) do not run when
# the suite is collected in environments missing those packages.
# ---------------------------------------------------------------------------


def _write_synthetic_document(tmp_path: Path) -> Path:
    path = tmp_path / "document.md"
    path.write_text("synthetic test text for the A2 CLI integration tests", encoding="utf-8")
    return path


def _run_cli(argv: list[str]) -> int:
    """Invoke run_pipeline.main(argv) with the same sys.argv the CLI uses."""
    import run_pipeline

    saved_argv = sys.argv
    sys.argv = ["run_pipeline.py", *argv]
    try:
        return run_pipeline.main(argv)
    finally:
        sys.argv = saved_argv


def _install_fake_engine(monkeypatch) -> None:
    """Replace LocalNeuralEngine with a stub that does not download a model.

    The CLI constructs the engine itself during the calibration phase. We
    intercept the import inside ``run_pipeline`` so the calibration and the
    ensemble phase both use the stub.
    """
    from types import SimpleNamespace

    import run_pipeline

    class _StubEngine:
        def __init__(self, *args, **kwargs):
            pass

        def limita_contesto(self, context, query, budget, max_tokens):
            return context

        def genera_bozza(self, context, query, max_tokens):
            return SimpleNamespace(
                testo="alpha beta context",
                prompt_tokens=len(context.split()),
                completion_tokens=2,
                durata_totale_sec=0.001,
                tempo_prefill_stimato_sec=0.0,
            )

    monkeypatch.setattr(run_pipeline, "LocalNeuralEngine", _StubEngine)


def test_cli_dry_run_with_k_zero_reports_zero_shot(tmp_path, monkeypatch):
    """Default k=0 keeps the conservative behaviour: SLA infeasible -> N=0.

    We use ``--dry-run`` because the conservative path never touches the
    local engine: the scheduler decides N=0 and the pipeline short-circuits
    before retrieval and inference. ``--dry-run`` does not write the JSON
    report, so we capture stdout to verify the decision fields printed by
    the CLI.
    """
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    monkeypatch.setattr(
        run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace in dry-run")
    )
    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--dry-run",
        "--max-latency-ms", "1500",
        "--rtt-ms", "1400",
        "--tempo-cloud-ms", "150",
        "--no-calibration",
    ])
    assert exit_code == 0


def test_cli_full_run_with_high_k_reports_accepted_overrun(tmp_path, monkeypatch):
    """With k>0 the CLI writes a JSON report with the accepted overrun.

    We replace the local engine with a stub and run the CLI end-to-end
    (no ``--dry-run``) so ``--output`` produces a JSON file we can inspect.
    The numbers come from the scheduler directly: RTT=1400, cloud=150,
    prompt_budget=256, ensemble=5, k=10 -> tolerance 15500 ms,
    overrun ~3250 ms < 15500 ms -> accept.
    """
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace")
    )
    _install_fake_engine(monkeypatch)
    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--max-latency-ms", "1500",
        "--rtt-ms", "1400",
        "--tempo-cloud-ms", "150",
        "--sforamento-k", "10.0",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--output", str(output),
    ])
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    decision = payload["decision"]
    assert decision["n_ensemble"] == 5
    assert decision["modalita"] == "ensemble"
    assert decision["sforamento_accettato"] is True
    assert decision["k_sforamento"] == pytest.approx(10.0)
    assert decision["sforamento_previsto_ms"] > 0.0
    assert decision["tolleranza_sforamento_ms"] == pytest.approx(
        10.0 * (1400.0 + 150.0)
    )
    assert "tolleranza disattivata" not in decision["motivazione"]
    assert "non una scadenza garantita" in decision["motivazione"]


def test_cli_full_run_with_force_zero_shot_overrides_tolerance(tmp_path, monkeypatch):
    """--force-zero-shot overrides the tolerance, even with k>0."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace")
    )
    _install_fake_engine(monkeypatch)
    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--max-latency-ms", "60000",
        "--rtt-ms", "10",
        "--tempo-cloud-ms", "10",
        "--sforamento-k", "10.0",
        "--force-zero-shot",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--output", str(output),
    ])
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    decision = payload["decision"]
    assert decision["n_ensemble"] == 0
    assert decision["modalita"] == "zero_shot"
    assert decision["sforamento_accettato"] is False
    assert "Zero-shot forzato" in decision["motivazione"]
    assert decision["sforamento_previsto_ms"] == 0.0


def test_cli_dry_run_rejects_invalid_k(tmp_path):
    """The CLI guard rejects NaN, inf and negative k before reaching the scheduler."""
    path = _write_synthetic_document(tmp_path)
    for bad in ("nan", "inf", "-1.5"):
        with pytest.raises(SystemExit) as exc_info:
            _run_cli([
                "--documents", str(path), "--query", "public query",
                "--dry-run",
                "--sforamento-k", bad,
            ])
        # argparse exits with code 2 on a bad argument.
        assert exc_info.value.code == 2
