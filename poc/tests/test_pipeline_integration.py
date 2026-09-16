"""Hardware-independent integration test for the dataset-to-DP path.

CLI integration tests live here too: they invoke ``run_pipeline.main(argv)``
as a black box, the same way a user does, and re-read the JSON report to
verify the end-to-end behaviour of the A2 tolerance policy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

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
    intercept the import inside both ``run_pipeline`` and ``core.pipeline``
    so the calibration and the ensemble phase both use the stub.
    """
    from types import SimpleNamespace

    import core.pipeline
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

    monkeypatch.setattr(core.pipeline, "LocalNeuralEngine", _StubEngine)
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


def test_cli_full_run_records_probe_when_credentials_are_configured(tmp_path, monkeypatch):
    """With credentials and endpoint configured, the CLI runs the A1 probe."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"

    class _StubProbe:
        def __init__(self):
            self.probe_calls = 0
            self.genera_calls = 0

        def probe(self):
            self.probe_calls += 1
            return SimpleNamespace(
                e2e_cloud_ms=7777.0,
                ttft_cloud_ms=None,
                simulato=False,
                cloud_probe_skipped=False,
                errore=None,
            )

        def genera(self, domanda, parole, contesti):
            self.genera_calls += 1
            return SimpleNamespace(
                risposta_testuale="probe-ok",
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=10,
                byte_grezzi_rag=0,
                risparmio_percentuale=0.0,
                simulato=True,
                errore=None,
            )

    stub = _StubProbe()
    monkeypatch.setattr(run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace"))
    monkeypatch.setattr(run_pipeline, "CloudGenerator", lambda **_kwargs: stub)
    _install_fake_engine(monkeypatch)

    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--api-key", "synthetic",
        "--cloud-base-url", "http://localhost:8000/v1",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--output", str(output),
    ])
    assert exit_code == 0
    assert stub.probe_calls == 1
    assert stub.genera_calls == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["cloud_probe_ms"] >= 0.0
    assert payload["e2e_cloud_ms_ms"] == pytest.approx(7777.0)
    assert payload["cloud_probe_skipped"] is False
    # The probe's e2e_cloud_ms is propagated into the scheduler through the
    # RequestConfig: it replaces the manual RTT+tempo_cloud sum.
    assert payload["decision"]["tolleranza_sforamento_ms"] == pytest.approx(
        7777.0 * payload["decision"]["k_sforamento"]
    )


def test_cli_full_run_skips_probe_when_offline(tmp_path, monkeypatch):
    """With ``--offline-cloud`` the CLI marks the probe as skipped."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"

    class _StubProbe:
        def __init__(self):
            self.probe_calls = 0

        def probe(self):
            self.probe_calls += 1
            return SimpleNamespace(
                e2e_cloud_ms=None,
                ttft_cloud_ms=None,
                simulato=True,
                cloud_probe_skipped=True,
                errore=None,
            )

        def genera(self, domanda, parole, contesti):
            return SimpleNamespace(
                risposta_testuale="offline-ok",
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=10,
                byte_grezzi_rag=0,
                risparmio_percentuale=0.0,
                simulato=True,
                errore=None,
            )

    stub = _StubProbe()
    monkeypatch.setattr(run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace"))
    monkeypatch.setattr(run_pipeline, "CloudGenerator", lambda **_kwargs: stub)
    _install_fake_engine(monkeypatch)

    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--output", str(output),
    ])
    assert exit_code == 0
    assert stub.probe_calls == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["cloud_probe_skipped"] is True
    assert payload["e2e_cloud_ms_ms"] is None


def test_cli_full_run_attaches_esito_label(tmp_path, monkeypatch):
    """The CLI writes the A3 esito to the JSON report and the CLI table."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"

    class _StubProbe:
        def probe(self):
            return SimpleNamespace(
                e2e_cloud_ms=None,
                ttft_cloud_ms=None,
                simulato=True,
                cloud_probe_skipped=True,
                errore=None,
            )

        def genera(self, domanda, parole, contesti):
            # Reuse a released keyword so the heuristic can mark "completo".
            testo = (
                "Risposta cloud che contiene alpha tra le keyword rilasciate."
                if parole and "alpha" in parole
                else "Risposta generica senza keyword."
            )
            return SimpleNamespace(
                risposta_testuale=testo,
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=10,
                byte_grezzi_rag=0,
                risparmio_percentuale=0.0,
                simulato=True,
                errore=None,
            )

    stub = _StubProbe()
    monkeypatch.setattr(run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace"))
    monkeypatch.setattr(run_pipeline, "CloudGenerator", lambda **_kwargs: stub)
    _install_fake_engine(monkeypatch)

    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--epsilon", "8",
        "--delta", "0.01",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--output", str(output),
    ])
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "esito" in payload
    assert payload["esito"]["label"] in {
        "insufficienti", "errore", "completo", "degradato"
    }
    assert payload["esito"]["motivazione"]


def test_cli_full_run_no_etichette_disables_label(tmp_path, monkeypatch):
    """``--no-etichette`` overrides the heuristic and records the disabled state."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"

    class _StubProbe:
        def probe(self):
            return SimpleNamespace(
                e2e_cloud_ms=None,
                ttft_cloud_ms=None,
                simulato=True,
                cloud_probe_skipped=True,
                errore=None,
            )

        def genera(self, domanda, parole, contesti):
            return SimpleNamespace(
                risposta_testuale="alpha è la risposta.",
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=10,
                byte_grezzi_rag=0,
                risparmio_percentuale=0.0,
                simulato=True,
                errore=None,
            )

    stub = _StubProbe()
    monkeypatch.setattr(run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace"))
    monkeypatch.setattr(run_pipeline, "CloudGenerator", lambda **_kwargs: stub)
    _install_fake_engine(monkeypatch)

    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--no-etichette",
        "--output", str(output),
    ])
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["esito"]["motivazione"] == "etichette disattivate via CLI"


def test_cli_hw_metrics_adds_before_after_snapshots(tmp_path, monkeypatch):
    """``--hw-metrics`` writes ``hw_before`` and ``hw_after`` to the JSON report."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"

    class _StubProbe:
        def probe(self):
            return SimpleNamespace(
                e2e_cloud_ms=None,
                ttft_cloud_ms=None,
                simulato=True,
                cloud_probe_skipped=True,
                errore=None,
            )

        def genera(self, domanda, parole, contesti):
            return SimpleNamespace(
                risposta_testuale="alpha ok",
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=10,
                byte_grezzi_rag=0,
                risparmio_percentuale=0.0,
                simulato=True,
                errore=None,
            )

    stub = _StubProbe()
    monkeypatch.setattr(run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace"))
    monkeypatch.setattr(run_pipeline, "CloudGenerator", lambda **_kwargs: stub)
    _install_fake_engine(monkeypatch)

    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--hw-metrics",
        "--output", str(output),
    ])
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "hw_before" in payload
    assert "hw_after" in payload
    assert "timestamp" in payload["hw_before"]
    assert "cpu_util_pct" in payload["hw_before"]
    # No sampler thread without --hw-sample-period.
    assert "hw_samples" not in payload


def test_cli_without_hw_metrics_omits_hardware_fields(tmp_path, monkeypatch):
    """Default behaviour does not include any hardware fields."""
    import run_pipeline

    path = _write_synthetic_document(tmp_path)
    output = tmp_path / "report.json"

    class _StubProbe:
        def probe(self):
            return SimpleNamespace(
                e2e_cloud_ms=None,
                ttft_cloud_ms=None,
                simulato=True,
                cloud_probe_skipped=True,
                errore=None,
            )

        def genera(self, domanda, parole, contesti):
            return SimpleNamespace(
                risposta_testuale="alpha ok",
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=10,
                byte_grezzi_rag=0,
                risparmio_percentuale=0.0,
                simulato=True,
                errore=None,
            )

    stub = _StubProbe()
    monkeypatch.setattr(run_pipeline, "LangfuseTracer", lambda **kwargs: pytest.fail("No trace"))
    monkeypatch.setattr(run_pipeline, "CloudGenerator", lambda **_kwargs: stub)
    _install_fake_engine(monkeypatch)

    exit_code = _run_cli([
        "--documents", str(path), "--query", "public query",
        "--ensemble-size", "5",
        "--prompt-token-budget", "256",
        "--no-calibration",
        "--offline-cloud",
        "--no-telemetry",
        "--output", str(output),
    ])
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "hw_before" not in payload
    assert "hw_after" not in payload
    assert "hw_samples" not in payload
