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
    assert abs(float(np.mean(samples))) < 0.16
    estimated_scale = float(np.std(samples, ddof=1)) * math.sqrt(6.0) / math.pi
    assert estimated_scale == pytest.approx(4.0, abs=0.16)


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
    assert calcola_gap(histogram) == {1: 19.0, 2: 1.0}
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
        delta_budget=0.01,
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
        delta_budget=0.01,
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


def test_public_domain_includes_unobserved_counts_and_last_observed_gap() -> None:
    from core.privacy import _find_best_k_details
    common = ' '.join(f'term{i}' for i in range(15))
    from core.privacy import costruisci_istogramma
    hist_a = costruisci_istogramma([common] * 40)
    hist_b = costruisci_istogramma([common] * 39 + [common + ' novel'])
    a = _find_best_k_details(hist_a, 0.5, 15, 30, np.random.default_rng(7))
    b = _find_best_k_details(hist_b, 0.5, 15, 30, np.random.default_rng(7))
    assert set(a.scores) == set(b.scores) == set(range(15, 31))
    assert a.gaps[15] == 40 and b.gaps[15] == 39
    assert find_best_k({}, 1.0) in range(1, 11)


def test_short_concordant_answers_can_release_all_five_keywords() -> None:
    result = DP_KSA_Filter(epsilon=20.0, rng=np.random.default_rng(13)).filtra(
        ['Denver Broncos defeated Carolina Panthers'] * 40,
    )
    assert result.ptr_superato
    assert result.parole_rilasciate == ['broncos', 'carolina', 'defeated', 'denver', 'panthers']


def test_release_order_is_independent_of_private_rank() -> None:
    a = top_k_with_ptr({'alpha': 40, 'beta': 39, 'gamma': 1}, 2, sigma=1,
                       rng=np.random.default_rng(7))
    b = top_k_with_ptr({'alpha': 39, 'beta': 40, 'gamma': 1}, 2, sigma=1,
                       rng=np.random.default_rng(7))
    assert a.passed and b.passed
    assert a.released_tokens == b.released_tokens == ('alpha', 'beta')


def test_implicit_zero_tokens_do_not_appear_even_in_failure_event() -> None:
    class ExtremeNoise:
        def normal(self, **kwargs):
            return 1000.0
    result = top_k_with_ptr({'alpha': 1, 'zero': 0}, 10, rng=ExtremeNoise())
    assert result.passed
    assert result.released_tokens == ('alpha',)


def test_find_best_k_matches_standard_exponential_distribution() -> None:
    # Utilities 8 and 2; sensitivity 2 => exp(epsilon * utility / 4).
    rng = np.random.default_rng(99)
    samples = [find_best_k({'alpha': 10, 'beta': 2}, 1.0, 1, 2, rng) for _ in range(6000)]
    expected = 1 / (1 + math.exp((2 - 8) / 4))
    assert samples.count(1) / len(samples) == pytest.approx(expected, abs=0.02)


def test_delta_budget_exhaustion_is_checked_independently_of_epsilon() -> None:
    f = DP_KSA_Filter(epsilon=100, epsilon_find_best_k=0.1, epsilon_top_k_ptr=0.1,
                      sigma=100, delta=1e-4)
    f.filtra(['alpha beta'])
    with pytest.raises(DPBudgetExhaustedError):
        f.filtra(['alpha beta'])
