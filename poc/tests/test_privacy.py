"""Unit tests for the formal DP-KSA mechanisms."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pytest

from core.privacy import (
    DEFAULT_RDP_ORDERS,
    DP_KSA_Filter,
    DPBudgetExhaustedError,
    calcola_account_rdp,
    calcola_gap,
    converti_rdp_in_dp,
    deriva_sigma_da_budget,
    epsilon_em_rdp,
    find_best_k,
    probabilita_passaggio_ptr,
    sample_gumbel_noise,
    top_k_with_ptr,
)


def test_gumbel_noise_is_centered_and_has_requested_scale() -> None:
    samples = sample_gumbel_noise(
        epsilon=1.0,
        size=10_000,
        rng=np.random.default_rng(1234),
    )
    assert isinstance(samples, np.ndarray)
    assert abs(float(np.mean(samples))) < 0.08
    estimated_scale = float(np.std(samples, ddof=1)) * math.sqrt(6.0) / math.pi
    assert estimated_scale == pytest.approx(2.0, abs=0.08)


def test_find_best_k_respects_regularizer_bounds() -> None:
    histogram = {f"token{index}": 30 - index for index in range(8)}
    selected = find_best_k(
        histogram,
        epsilon=2.0,
        r_min_k=2,
        r_max_k=4,
        rng=np.random.default_rng(7),
    )
    assert 2 <= selected <= 4


def test_top_k_ptr_passes_for_a_stable_gap() -> None:
    result = top_k_with_ptr(
        {"alpha": 20, "beta": 5, "gamma": 1},
        k=1,
        delta=1e-4,
        sigma=0.01,
        rng=np.random.default_rng(7),
    )
    assert result.gap > 2
    assert result.passed
    assert result.released_tokens == ("alpha",)


def test_top_k_ptr_uses_zero_shot_for_an_unstable_gap() -> None:
    result = top_k_with_ptr(
        {"alpha": 5, "beta": 5, "gamma": 1},
        k=1,
        delta=1e-4,
        sigma=0.01,
        rng=np.random.default_rng(7),
        strict_gap_guard=True,
    )
    assert result.gap <= 2
    assert not result.passed
    assert result.released_tokens == ()


def test_ptr_release_probability_matches_algorithm_2() -> None:
    sigma = 0.7
    delta = 0.01
    threshold = 2.0 * sigma * NormalDist().inv_cdf(1.0 - delta)
    expected = 1.0 - NormalDist().cdf((threshold + 2.0 - 3.0) / (2.0 * sigma))
    assert probabilita_passaggio_ptr(3.0, sigma, delta) == pytest.approx(expected)
    assert probabilita_passaggio_ptr(1.0, sigma, delta) == pytest.approx(delta)
    assert probabilita_passaggio_ptr(1.0, sigma, delta, strict_gap_guard=True) == 0.0


def test_zero_frequency_tokens_are_never_candidates() -> None:
    histogram = {"alpha": 20, "beta": 1, "zero": 0}
    assert calcola_gap(histogram) == {1: 19.0}
    result = top_k_with_ptr(
        histogram,
        k=1,
        sigma=0.01,
        rng=np.random.default_rng(1),
    )
    assert "zero" not in result.released_tokens


def test_rdp_formula_and_conversion_are_finite() -> None:
    rdp = epsilon_em_rdp(alpha=10.0, epsilon=0.5)
    assert rdp > 0.0
    epsilon, order = converti_rdp_in_dp({10.0: rdp}, delta=1e-4)
    assert epsilon > 0.0
    assert order == 10.0


def test_sigma_derivation_and_accounting_are_consistent() -> None:
    sigma = deriva_sigma_da_budget(1.0, 0.5, 0.5, delta=1e-4)
    account = calcola_account_rdp(0.5, sigma, delta_ptr=1e-4)
    assert sigma > 0.0
    assert account.epsilon_dp <= 1.0
    assert account.delta_total == pytest.approx(2e-4)


def test_filter_composes_remaining_epsilon_after_each_invocation() -> None:
    filtro = DP_KSA_Filter(
        epsilon=4.0,
        delta=1e-4,
        r_min_k=1,
        r_max_k=3,
        epsilon_find_best_k=0.2,
        epsilon_top_k_ptr=0.2,
        sigma=100.0,
        rng=np.random.default_rng(5),
    )
    previous_consumed = 0.0
    for invocation in range(1, 4):
        result = filtro.filtra(["alpha beta gamma"] * 8)
        assert result.budget_consumato_epsilon + result.epsilon_rimasto == pytest.approx(
            result.epsilon_budget
        )
        assert result.epsilon_rimasto >= 0.0
        assert result.numero_invocazione == invocation
        assert result.budget_consumato_delta == pytest.approx(
            invocation * 1e-4 + 1e-4
        )
        assert result.budget_consumato_epsilon > previous_consumed
        previous_consumed = result.budget_consumato_epsilon

    expected_by_order = {
        alpha: 3.0 * (epsilon_em_rdp(alpha, 0.2) + alpha / (2.0 * 100.0**2))
        + math.log(1.0 / 1e-4) / (alpha - 1.0)
        for alpha in DEFAULT_RDP_ORDERS
    }
    assert result.budget_consumato_epsilon == pytest.approx(min(expected_by_order.values()))


def test_filter_owns_a_persistent_rng_when_none_is_supplied() -> None:
    filtro = DP_KSA_Filter(
        epsilon=4.0,
        delta=1e-4,
        r_min_k=1,
        r_max_k=3,
        epsilon_find_best_k=0.2,
        epsilon_top_k_ptr=0.2,
        sigma=100.0,
        rng=None,
    )
    assert isinstance(filtro.rng, np.random.Generator)
    state_before = repr(filtro.rng.bit_generator.state)
    filtro.filtra(["alpha beta gamma"] * 8)
    assert repr(filtro.rng.bit_generator.state) != state_before


def test_filter_rejects_an_invocation_after_budget_exhaustion() -> None:
    filtro = DP_KSA_Filter(
        epsilon=1.0,
        delta=1e-4,
        r_min_k=1,
        r_max_k=3,
        rng=np.random.default_rng(9),
    )
    for _ in range(100):
        try:
            filtro.filtra(["alpha beta gamma"] * 8)
        except DPBudgetExhaustedError as exc:
            assert exc.epsilon_budget == pytest.approx(1.0)
            assert filtro.account.invocations >= 1
            break
    else:
        pytest.fail("il budget cumulativo non è stato esaurito")
