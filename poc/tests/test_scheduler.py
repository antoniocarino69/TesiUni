"""Tests for the adaptive latency/privacy scheduler."""

from __future__ import annotations

import math

import pytest

from core.privacy import probabilita_passaggio_ptr
from core.scheduler import (
    AdaptiveScheduler,
    PrivacyBudgetExhaustedError,
)


def _documents(count: int = 40) -> list[int]:
    return [10] * count


def test_slow_network_clamps_to_minimum_ensemble() -> None:
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
    )
    assert decision.n_ensemble == 5
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


def test_intermediate_latency_uses_capacity_clamp() -> None:
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=50.0,
        latenza_massima_ms=3_000.0,
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
    empirical = 1.0 - math.exp(-decision.epsilon_top_k_ptr / 2.0)
    expected = analytical * 0.5 + empirical * 0.5
    assert decision.ptr_pass_rate_attesa == pytest.approx(expected)


def test_scheduler_validates_inputs() -> None:
    with pytest.raises(ValueError):
        AdaptiveScheduler(n_min=0)
    with pytest.raises(ValueError):
        AdaptiveScheduler(epsilon_split=0.0)
    scheduler = AdaptiveScheduler()
    with pytest.raises(ValueError):
        scheduler.schedule([], epsilon_budget=1.0)
    with pytest.raises(ValueError):
        scheduler.schedule([1, 2], epsilon_budget=1.0)
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, tok_per_sec_prefill=0.0)
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, tok_per_sec_generazione=0.0)
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, delta=0.0)
