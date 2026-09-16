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
    with pytest.raises(ValueError):
        scheduler.schedule([1, 2], epsilon_budget=1.0)
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


def test_sforamento_k_zero_reproduces_conservative_behavior():
    """With k=0 (default), SLA incompatible with N_MIN falls back to zero-shot."""
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        k_sforamento=0.0,
    )
    assert decision.n_ensemble == 0
    assert decision.sforamento_accettato is False
    assert decision.k_sforamento == 0.0


def test_sforamento_k_positive_accepts_small_overrun():
    """With k>0, SLA slightly below N_MIN plan accepts overrun and plans N_MIN."""
    # SLA = 1500ms, RTT=1400ms, cloud=150ms → residual = -50ms
    # N_MIN=5 would add ~3200ms local → overrun ~3200ms
    # E2E_cloud = 1400+150 = 1550ms
    # With k=0.5, tolerance = 775ms → still not enough
    # With k=3.0, tolerance = 4650ms → accepts
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        k_sforamento=3.0,
    )
    assert decision.n_ensemble == 5
    assert decision.sforamento_accettato is True
    assert decision.k_sforamento == 3.0
    assert decision.sforamento_previsto_ms > 0
    assert decision.modalita == "ensemble"


def test_sforamento_k_positive_but_insufficient_still_zero_shot():
    """With k>0 but overrun exceeds tolerance, still falls back to zero-shot."""
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        k_sforamento=0.1,  # tolerance = 155ms, overrun ~3200ms
    )
    assert decision.n_ensemble == 0
    assert decision.sforamento_accettato is False
    assert decision.k_sforamento == 0.1


def test_fixed_baseline_does_not_apply_sforamento_policy():
    """Fixed N baseline never applies the k policy, even if it would accept."""
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        fixed_n=5,
        k_sforamento=3.0,
    )
    assert decision.n_ensemble == 5
    assert decision.sforamento_accettato is False
    assert decision.k_sforamento == 3.0


def test_sforamento_previsto_describes_the_executed_plan():
    """sforamento_previsto_ms is comparable with the measured overrun."""
    # Rejected tolerance: N=0 runs, so the executed plan does not overrun,
    # while the N_MIN candidate overrun is reported separately.
    rejected = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        k_sforamento=0.1,
    )
    assert rejected.n_ensemble == 0
    assert rejected.tempo_stimato_ms == 1_550.0
    assert rejected.sforamento_previsto_ms == pytest.approx(50.0)
    assert rejected.sforamento_piano_minimo_ms == pytest.approx(3_250.0)
    assert rejected.tolleranza_sforamento_ms == pytest.approx(155.0)
    # Fixed baseline: the executed plan is the fixed one, not N_MIN.
    fixed = AdaptiveScheduler().schedule([10] * 40, 1.0, fixed_n=5)
    assert fixed.sforamento_previsto_ms == pytest.approx(3_400.0 - 1_500.0)
    assert fixed.sforamento_accettato is False


def test_force_zero_shot_is_explicit_and_bypasses_tolerance():
    """fixed_n=0 is the --force-zero-shot path: no documents, no policy."""
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1.0,
        latenza_massima_ms=30_000.0,
        tempo_cloud_ms=1.0,
        fixed_n=0,
        k_sforamento=3.0,
    )
    assert decision.n_ensemble == 0
    assert decision.modalita == "zero_shot"
    assert decision.sforamento_accettato is False
    assert decision.sforamento_previsto_ms == 0.0
    assert decision.sla_fattibile
    assert "Zero-shot forzato" in decision.motivazione


def test_accepted_overrun_is_declared_as_an_estimate():
    """An accepted overrun must not be presented as a guaranteed deadline."""
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        k_sforamento=3.0,
    )
    assert decision.sforamento_accettato is True
    assert not decision.sla_fattibile
    assert "non una scadenza garantita" in decision.motivazione
    assert decision.tolleranza_sforamento_ms == pytest.approx(3.0 * 1_550.0)
    assert decision.sforamento_previsto_ms == decision.sforamento_piano_minimo_ms


def test_tolerance_does_not_change_a_plan_that_already_fits():
    """k only matters when the minimum plan does not fit the SLA."""
    common = dict(
        epsilon_budget=1.0,
        latenza_rete_ms=1.0,
        latenza_massima_ms=30_000.0,
        tempo_cloud_ms=1.0,
    )
    prudent = AdaptiveScheduler().schedule(_documents(), **common)
    tolerant = AdaptiveScheduler().schedule(_documents(), k_sforamento=5.0, **common)
    assert prudent.n_ensemble == tolerant.n_ensemble == 40
    assert tolerant.sforamento_accettato is False
    assert prudent.sforamento_previsto_ms == tolerant.sforamento_previsto_ms == 0.0


def test_k_sforamento_is_validated():
    scheduler = AdaptiveScheduler()
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, k_sforamento=-1.0)
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, k_sforamento=float("nan"))
    with pytest.raises(ValueError):
        scheduler.schedule(_documents(), epsilon_budget=1.0, k_sforamento=float("inf"))


def test_tolerance_requires_enough_candidates():
    """The library refuses to plan N_MIN when fewer than N_MIN slots exist.

    The CLI guarantees 5..40 slots, but the library is general-purpose and
    must not invent ensemble members that the corpus cannot supply.
    """
    scheduler = AdaptiveScheduler()
    with pytest.raises(ValueError):
        scheduler.schedule(
            [100, 100, 100],  # only 3 slots, n_min=5
            epsilon_budget=1.0,
            latenza_rete_ms=10_000.0,
            latenza_massima_ms=10_500.0,
            tempo_cloud_ms=100.0,
            k_sforamento=10.0,
        )


def test_accepted_overrun_message_does_not_claim_infeasibility():
    """An accepted overrun must not be followed by 'SLA non fattibile'."""
    decision = AdaptiveScheduler().schedule(
        _documents(),
        epsilon_budget=1.0,
        latenza_rete_ms=1_400.0,
        latenza_massima_ms=1_500.0,
        tempo_cloud_ms=150.0,
        k_sforamento=3.0,
    )
    assert decision.sforamento_accettato is True
    assert "SLA non fattibile secondo le stime configurate" not in decision.motivazione
    assert "non una scadenza garantita" in decision.motivazione
