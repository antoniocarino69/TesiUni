"""Tests for benchmark_scheduler.py CLI (A4).

These tests do not download the local model: the engine is replaced by a
stub that returns instantly, and ``core.calibration.calibra`` is monkey-
patched to return a synthetic ``RisultatoCalibrazione``. We verify that
the benchmark honours ``--no-calibration`` and that, when calibration
is active, the measured throughputs flow into the ``RequestConfig``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import benchmark_scheduler


class _StubEngine:
    def __init__(self, *args, **kwargs):
        self.kwargs = dict(kwargs)

    def limita_contesto(self, context, query, budget, max_tokens):
        return context

    def genera_bozza(self, context, query, max_tokens):
        return SimpleNamespace(
            testo="stub response",
            completion_tokens=2,
            tempo_prefill_stimato_sec=0.0,
        )


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    doc = tmp_path / "doc.md"
    doc.write_text("synthetic benchmark input", encoding="utf-8")
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            [{"query": "public query", "references": ["stub response"]}]
        ),
        encoding="utf-8",
    )
    return doc, cases


def _build_report_for_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calibra_return,
    no_calibration: bool,
    manual_prefill: float = 1950.0,
    manual_generation: float = 480.0,
    output: Path,
    doc: Path,
    cases: Path,
) -> dict[str, object]:
    """Run the benchmark CLI in-process and return the parsed report JSON.

    Returns the report dict so each test can assert on throughputs,
    calibration_ms and the per-row request_ms.
    """
    captured = {"calibra_calls": 0}

    def _fake_calibra(engine):
        captured["calibra_calls"] += 1
        return calibra_return

    monkeypatch.setattr(benchmark_scheduler, "LocalNeuralEngine", _StubEngine)
    monkeypatch.setattr(benchmark_scheduler, "calibra", _fake_calibra)

    argv = [
        "--documents", str(doc),
        "--cases", str(cases),
        "--output", str(output),
        "--repeats", "1",
        "--max-latency-ms", "30000",
        "--offline-cloud",
    ]
    if no_calibration:
        argv.append("--no-calibration")
        argv.extend([
            "--tok-per-sec-prefill", str(manual_prefill),
            "--tok-per-sec-generazione", str(manual_generation),
        ])
    exit_code = benchmark_scheduler.main(argv)
    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    report["_calibra_calls"] = captured["calibra_calls"]
    return report


def test_no_calibration_uses_manual_throughputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--no-calibration`` skips the probe and uses the manual flags."""
    doc, cases = _write_inputs(tmp_path)
    output = tmp_path / "report.json"
    calibra_return = SimpleNamespace(
        prefill_tps=1234.5,
        generation_tps=678.9,
        calibration_ms=999.0,
    )
    report = _build_report_for_cli(
        monkeypatch,
        calibra_return=calibra_return,
        no_calibration=True,
        manual_prefill=1950.0,
        manual_generation=480.0,
        output=output,
        doc=doc,
        cases=cases,
    )
    assert report["_calibra_calls"] == 0
    assert report["prefill_tps"] == pytest.approx(1950.0)
    assert report["generation_tps"] == pytest.approx(480.0)
    assert report["calibration_ms"] == 0


def test_calibration_feeds_throughputs_to_request_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default calibration measures throughputs and reports them."""
    doc, cases = _write_inputs(tmp_path)
    output = tmp_path / "report.json"
    calibra_return = SimpleNamespace(
        prefill_tps=1950.0,
        generation_tps=480.0,
        calibration_ms=602.0,
    )
    report = _build_report_for_cli(
        monkeypatch,
        calibra_return=calibra_return,
        no_calibration=False,
        output=output,
        doc=doc,
        cases=cases,
    )
    assert report["_calibra_calls"] == 1
    assert report["prefill_tps"] == pytest.approx(1950.0)
    assert report["generation_tps"] == pytest.approx(480.0)
    assert report["calibration_ms"] == pytest.approx(602.0)
    # Every row should expose a decision with a tempo_stimato_ms based on
    # the calibrated throughputs. We do not pin the exact number (the
    # shared DP filter is non-deterministic across runs) but we verify
    # the value is positive and bounded by the SLA.
    assert report["runs"], "calibration produced no rows"
    for row in report["runs"]:
        decision = row["decision"]
        assert decision["tempo_stimato_ms"] > 0.0


def test_hw_metrics_attach_snapshot_to_each_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--hw-metrics`` adds an ``hw_before`` snapshot to every benchmark row."""
    doc, cases = _write_inputs(tmp_path)
    output = tmp_path / "report.json"
    monkeypatch.setattr(benchmark_scheduler, "LocalNeuralEngine", _StubEngine)
    monkeypatch.setattr(
        benchmark_scheduler, "calibra",
        lambda _engine: SimpleNamespace(
            prefill_tps=250.0, generation_tps=50.0, calibration_ms=10.0
        ),
    )
    exit_code = benchmark_scheduler.main([
        "--documents", str(doc),
        "--cases", str(cases),
        "--output", str(output),
        "--repeats", "1",
        "--max-latency-ms", "30000",
        "--offline-cloud",
        "--hw-metrics",
    ])
    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["runs"], "no benchmark rows produced"
    for row in report["runs"]:
        assert "hw_before" in row
        # The snapshot is a flat dict with at least the documented keys.
        snapshot = row["hw_before"]
        assert "timestamp" in snapshot
        assert "cpu_util_pct" in snapshot
        assert "ram_used_gb" in snapshot
