"""Tests for automatic local throughput calibration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.calibration import (
    CALIBRATION_QUERY,
    ProvaCalibrazione,
    RisultatoCalibrazione,
    calibra,
    genera_testo_calibrazione,
)


class _FakeEngine:
    """Deterministic engine with controllable timing."""

    def __init__(
        self,
        prompt_tokens: int = 256,
        completion_tokens: int = 5,
        durata_sec: float = 1.0,
        prefill_stimato_sec: float = 0.8,
    ) -> None:
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._durata = durata_sec
        self._prefill = prefill_stimato_sec
        self.calls: list[tuple[str, str, int]] = []

    def genera_bozza(self, contesto: str, domanda: str, max_tokens: int = 30):
        self.calls.append((contesto, domanda, max_tokens))
        return SimpleNamespace(
            testo="probe output",
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            durata_totale_sec=self._durata,
            tempo_prefill_stimato_sec=self._prefill,
            token_al_secondo=self._completion_tokens / self._durata if self._durata > 0 else 0.0,
        )


def test_genera_testo_calibrazione_returns_non_empty_text():
    text = genera_testo_calibrazione(256)
    assert len(text) > 0
    assert isinstance(text, str)


def test_genera_testo_calibrazione_scales_with_target():
    short = genera_testo_calibrazione(64)
    long = genera_testo_calibrazione(1024)
    assert len(long) > len(short)


def test_genera_testo_calibrazione_rejects_zero():
    with pytest.raises(ValueError, match="positivo"):
        genera_testo_calibrazione(0)


def test_calibra_returns_valid_throughput():
    engine = _FakeEngine(
        prompt_tokens=256,
        completion_tokens=5,
        durata_sec=1.0,
        prefill_stimato_sec=0.8,
    )
    result = calibra(engine, target_lengths=[256], probes_per_length=1)
    assert isinstance(result, RisultatoCalibrazione)
    assert result.prove_eseguite == 1
    assert result.calibration_ms > 0.0
    assert result.prefill_tps == pytest.approx(256 / 0.8)
    assert result.generation_tps == pytest.approx(5 / 0.2)


def test_calibra_runs_one_probe_per_length():
    engine = _FakeEngine()
    result = calibra(engine, target_lengths=[256, 512, 1024], probes_per_length=1)
    assert result.prove_eseguite == 3
    assert len(result.dettagli) == 3
    targets = [d.target_tokens for d in result.dettagli]
    assert targets == [256, 512, 1024]


def test_calibra_runs_multiple_probes_per_length():
    engine = _FakeEngine()
    result = calibra(engine, target_lengths=[512], probes_per_length=3)
    assert result.prove_eseguite == 3
    assert len(engine.calls) == 3


def test_calibra_averages_throughput_across_probes():
    engine = _FakeEngine(
        prompt_tokens=512,
        completion_tokens=10,
        durata_sec=2.0,
        prefill_stimato_sec=1.0,
    )
    result = calibra(engine, target_lengths=[256, 1024], probes_per_length=1)
    assert result.prefill_tps == pytest.approx(512 / 1.0)
    assert result.generation_tps == pytest.approx(10 / 1.0)


def test_calibra_uses_calibration_query():
    engine = _FakeEngine()
    calibra(engine, target_lengths=[256], probes_per_length=1)
    _, query, _ = engine.calls[0]
    assert query == CALIBRATION_QUERY


def test_calibra_passes_max_tokens_to_engine():
    engine = _FakeEngine()
    calibra(engine, target_lengths=[256], probes_per_length=1, max_tokens=8)
    _, _, max_tok = engine.calls[0]
    assert max_tok == 8


def test_calibra_handles_zero_duration():
    engine = _FakeEngine(durata_sec=0.0, prefill_stimato_sec=0.0)
    result = calibra(engine, target_lengths=[256], probes_per_length=1)
    assert result.prefill_tps == 0.0
    assert result.generation_tps == 0.0
    assert result.prove_eseguite == 1


def test_calibra_rejects_empty_targets():
    engine = _FakeEngine()
    with pytest.raises(ValueError, match="vuoto"):
        calibra(engine, target_lengths=[])


def test_calibra_rejects_zero_probes():
    engine = _FakeEngine()
    with pytest.raises(ValueError, match="positivo"):
        calibra(engine, probes_per_length=0)


def test_calibra_rejects_zero_max_tokens():
    engine = _FakeEngine()
    with pytest.raises(ValueError, match="positivo"):
        calibra(engine, max_tokens=0)


def test_calibra_rejects_negative_target_length():
    engine = _FakeEngine()
    with pytest.raises(ValueError, match="positive"):
        calibra(engine, target_lengths=[-1])


def test_default_target_lengths_match_conception():
    from core.calibration import DEFAULT_TARGET_LENGTHS
    assert DEFAULT_TARGET_LENGTHS == (256, 512, 1024)


def test_dettagli_contain_per_probe_metrics():
    engine = _FakeEngine(
        prompt_tokens=300,
        completion_tokens=4,
        durata_sec=1.5,
        prefill_stimato_sec=1.0,
    )
    result = calibra(engine, target_lengths=[512], probes_per_length=1)
    detail = result.dettagli[0]
    assert isinstance(detail, ProvaCalibrazione)
    assert detail.target_tokens == 512
    assert detail.prompt_tokens == 300
    assert detail.completion_tokens == 4
    assert detail.durata_ms == pytest.approx(1500.0)
    assert detail.prefill_tps == pytest.approx(300 / 1.0)
    assert detail.generation_tps == pytest.approx(4 / 0.5)
