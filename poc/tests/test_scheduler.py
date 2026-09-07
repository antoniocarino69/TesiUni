"""Tests for the adaptive latency/privacy scheduler."""

from __future__ import annotations

import pytest

from core.privacy import probabilita_passaggio_ptr
from core.scheduler import (
    AdaptiveScheduler,
    PrivacyBudgetExhaustedError,
)


def _documents(count: int = 40) -> list[int]:
    return [10] * count


def test_slow_network_returns_infeasible_zero_shot() -> None:
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
    )
    assert decision.n_ensemble == 0
    assert not decision.sla_fattibile
    assert decision.modalita == "zero_shot"
    assert decision.sigma > 0.0


def test_fast_network_uses_maximum_ensemble() -> None:
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1.0,
        latenza_massima_ms=30_000.0,
        tempo_cloud_ms=1.0,
    )
    assert decision.n_ensemble == 40


def test_intermediate_latency_uses_estimated_capacity() -> None:
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=50.0,
        latenza_massima_ms=6_000.0,
        tempo_cloud_ms=150.0,
    )
    assert 5 <= decision.n_ensemble < 40
    assert decision.tempo_stimato_ms > 0.0


def test_epsilon_exhaustion_is_explicit() -> None:
    with pytest.raises(PrivacyBudgetExhaustedError) as error:
        AdaptiveScheduler().schedule(_documents(), epsilon_budget=0.0)
    assert error.value.epsilon_rimasto == 0.0
    assert error.value.min_epsilon_richiesto > 0.0


def test_epsilon_allocations_and_pass_rate_are_valid() -> None:
    decision = AdaptiveScheduler().decidi(
        _documents(),
        epsilon_budget=2.0,
        delta=1e-4,
        latenza_massima_ms=30_000.0,
    )
    assert decision.epsilon_find_best_k + decision.epsilon_top_k_ptr <= 2.0
    assert 0.0 < decision.sigma
    assert 0.0 <= decision.ptr_pass_rate_attesa <= 1.0
    assert (
        AdaptiveScheduler()
        .pianifica(_documents(), 2.0, latenza_massima_ms=30_000.0)
        .n_ensemble
        == 40
    )


def test_ptr_pass_rate_uses_the_algorithm_2_gap_boundary() -> None:
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=2.0,
        delta=1e-4,
        latenza_massima_ms=30_000.0,
    )
    analytical = probabilita_passaggio_ptr(3.0, decision.sigma, 1e-4)
    expected = analytical
    assert decision.ptr_pass_rate_attesa == pytest.approx(expected)


def test_scheduler_validates_inputs() -> None:
    with pytest.raises(ValueError):
        AdaptiveScheduler(n_min=0)
    with pytest.raises(ValueError):
        AdaptiveScheduler(epsilon_split=0.0)
    scheduler = AdaptiveScheduler()
    with pytest.raises(ValueError):
        scheduler.schedule([], epsilon_budget=1.0)
    assert scheduler.schedule([1, 2], epsilon_budget=1.0).n_ensemble == 0
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, tok_per_sec_prefill=0.0)
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, tok_per_sec_generazione=0.0)
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, delta=0.0)


def test_impossible_edge_work_returns_zero_shot_with_feasible_cloud():
    result = AdaptiveScheduler().schedule([10] * 40, 1.0)
    assert result.n_ensemble == 0
    assert result.tempo_stimato_ms == 200
    assert result.sla_fattibile


def test_fixed_baseline_explicitly_reports_estimated_sla_violation():
    result = AdaptiveScheduler().schedule([10] * 40, 1.0, fixed_n=5)
    assert result.n_ensemble == 5
    assert result.tempo_stimato_ms == 3400
    assert not result.sla_fattibile


@pytest.mark.parametrize('kwargs', [
    {'delta': 0.7}, {'epsilon_budget': 0.00001}, {'fixed_n': 41},
    {'latenza_rete_ms': float('nan')}, {'tok_per_sec_prefill': float('inf')},
])
def test_invalid_or_unfundable_schedule(kwargs):
    with pytest.raises(ValueError):
        AdaptiveScheduler().schedule([10] * 40, **{'epsilon_budget': 1.0, **kwargs})
