"""Privacy mechanisms used by the DP-KSA pipeline.

The module contains the two randomized mechanisms from Tang et al. (2025):
``FindBestK`` (Algorithm 3) and ``TopKWithPTR`` (Algorithm 2).  The
histogram is built from set-valued responses, so each response contributes at
most one count to a token.  This is the sample-and-aggregate assumption used
by the privacy proof.

External dependencies:
    ``numpy`` supplies the random Gumbel and Gaussian samplers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

__all__ = [
    "DEFAULT_DELTA",
    "DEFAULT_EPSILON",
    "DEFAULT_R_MAX_K",
    "DEFAULT_R_MIN_K",
    "DEFAULT_RDP_ORDERS",
    "DEFAULT_SIGMA",
    "DPBudgetExhaustedError",
    "DP_KSA_Filter",
    "EsitoDP",
    "FindBestKResult",
    "PTRResult",
    "RDPAccount",
    "STOPWORDS_ITALIANO_INGLESE",
    "calcola_account_rdp",
    "calcola_gap",
    "converti_rdp_in_dp",
    "costruisci_istogramma",
    "deriva_sigma_da_budget",
    "epsilon_em_rdp",
    "find_best_k",
    "normalizza_e_tokenizza",
    "probabilita_passaggio_ptr",
    "sample_gumbel_noise",
    "top_k_with_ptr",
]

DEFAULT_DELTA = 1e-4
DEFAULT_EPSILON = 1.0
DEFAULT_R_MIN_K = 15
DEFAULT_R_MAX_K = 30
DEFAULT_SIGMA = 1.0
DEFAULT_RDP_ORDERS: tuple[float, ...] = (
    2.0,
    3.0,
    5.0,
    10.0,
    20.0,
    40.0,
    80.0,
    160.0,
    320.0,
    640.0,
    1024.0,
)
GLOBAL_GAP_SENSITIVITY = 2.0
EULER_MASCHERONI = 0.5772156649015329

STOPWORDS_ITALIANO_INGLESE = {
    "il",
    "lo",
    "la",
    "i",
    "gli",
    "le",
    "un",
    "uno",
    "una",
    "di",
    "a",
    "da",
    "in",
    "con",
    "su",
    "per",
    "tra",
    "fra",
    "e",
    "ed",
    "o",
    "ha",
    "al",
    "del",
    "della",
    "delle",
    "dei",
    "ai",
    "agli",
    "alle",
    "dal",
    "dalla",
    "dalle",
    "nel",
    "nella",
    "è",
    "era",
    "sono",
    "stato",
    "the",
    "of",
    "and",
    "to",
    "is",
    "you",
    "that",
    "it",
    "he",
    "was",
    "for",
    "on",
    "are",
    "as",
    "with",
    "his",
    "they",
    "at",
    "be",
    "this",
    "have",
    "from",
    "or",
    "one",
    "had",
    "by",
    "word",
    "but",
    "not",
    "what",
    "all",
    "were",
    "we",
    "when",
    "your",
    "can",
    "said",
    "there",
    "use",
    "an",
    "each",
    "which",
    "she",
    "do",
    "how",
    "their",
}


@dataclass(frozen=True, slots=True)
class FindBestKResult:
    """Diagnostic output from the exponential mechanism used by FindBestK.

    Args:
        k_hat: Selected number of keywords.
        scores: Noisy utility score for each admissible ``k``.
        gaps: Non-private histogram gap for each admissible ``k``.
        noise: Centered Gumbel noise sampled for each admissible ``k``.
    """

    k_hat: int
    scores: dict[int, float]
    gaps: dict[int, float]
    noise: dict[int, float]


@dataclass(frozen=True, slots=True)
class PTRResult:
    """Diagnostic output from the TopKWithPTR test."""

    gap: float
    noisy_gap: float
    gaussian_threshold: float
    passed: bool
    released_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RDPAccount:
    """Composed RDP account and its conversion to approximate DP.

    ``delta_ptr`` is the union-bound failure probability of all PTR calls
    represented by this account. The conversion theorem also needs a
    conversion delta; therefore ``delta_total`` is their sum.
    """

    epsilon_rdp_find_best_k: float
    epsilon_rdp_top_k_ptr: float
    epsilon_rdp_total: float
    epsilon_dp: float
    optimal_order: float
    delta_ptr: float
    delta_conversion: float
    delta_total: float
    invocations: int


class DPBudgetExhaustedError(RuntimeError):
    """Raised when another DP-KSA invocation would exceed the account.

    The filter composes repeated invocations in RDP before converting the
    cumulative account to approximate DP. This exception is raised before a
    new invocation consumes randomness when that composed account would no
    longer fit the configured epsilon or delta budget.
    """

    def __init__(
        self,
        epsilon_budget: float,
        epsilon_requested: float,
        delta_total: float,
    ) -> None:
        self.epsilon_budget = epsilon_budget
        self.epsilon_requested = epsilon_requested
        self.delta_total = delta_total
        super().__init__(
            "Budget DP cumulativo esaurito: "
            f"epsilon richiesto={epsilon_requested:.6f}, "
            f"disponibile={epsilon_budget:.6f}, "
            f"delta totale={delta_total:.6g}"
        )


@dataclass(frozen=True, slots=True)
class EsitoDP:
    """Result of one DP-KSA keyword extraction invocation.

    The ``epsilon_rimasto`` invariant is
    ``budget_consumato_epsilon + epsilon_rimasto == epsilon_budget`` up to
    floating-point rounding. The consumed fields are cumulative for the
    lifetime of the filter instance. ``parole_rilasciate`` is empty when the
    PTR test fails, which is the zero-shot branch of DP-KSA.
    """

    conteggi_reali: dict[str, int]
    token_ordinati: list[str]
    gap_per_k: dict[int, float]
    punteggi_find_best_k: dict[int, float]
    rumore_gumbel: dict[int, float]
    k_hat: int
    gap_ptr: float | None
    gap_ptr_rumoroso: float | None
    soglia_gaussiana_ptr: float | None
    ptr_superato: bool
    parole_rilasciate: list[str]
    parole_scartate: list[str]
    epsilon_budget: float
    delta: float
    sigma: float
    epsilon_find_best_k: float
    epsilon_top_k_ptr: float
    epsilon_rdp_find_best_k: float
    epsilon_rdp_top_k_ptr: float
    epsilon_rdp_totale: float
    ordine_rdp: float
    budget_consumato_epsilon: float
    budget_consumato_delta: float
    epsilon_rimasto: float
    numero_invocazione: int


def _validate_positive_finite(value: float, name: str) -> None:
    """Validate a finite strictly positive numeric parameter."""

    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} deve essere finito e maggiore di zero")


def _validate_delta(delta: float, name: str = "delta") -> None:
    """Validate a probability used by a DP mechanism."""

    if not math.isfinite(delta) or not 0 < delta < 1:
        raise ValueError(f"{name} deve essere compreso strettamente tra 0 e 1")


def _rng_or_default(rng: np.random.Generator | None) -> np.random.Generator:
    """Return the caller RNG or create an isolated cryptographically-seeded RNG."""

    return rng if rng is not None else np.random.default_rng()


def normalizza_e_tokenizza(testo: str) -> list[str]:
    """Normalize a generated response into candidate keyword tokens.

    Args:
        testo: Response generated by the local model.

    Returns:
        Lowercase alphanumeric tokens longer than two characters, excluding
        the bilingual stopword list.

    Raises:
        TypeError: If ``testo`` is not a string.
    """

    if not isinstance(testo, str):
        raise TypeError("testo deve essere una stringa")
    testo_pulito = testo.replace("'", " ").replace("’", " ").replace("-", " ")
    parole = "".join(
        carattere if carattere.isalnum() or carattere.isspace() else " "
        for carattere in testo_pulito.lower()
    ).split()
    return [
        parola
        for parola in parole
        if parola not in STOPWORDS_ITALIANO_INGLESE and len(parola) > 2
    ]


def costruisci_istogramma(bozze_ensemble: Sequence[str]) -> dict[str, int]:
    """Build the set-valued response histogram required by DP-KSA.

    Args:
        bozze_ensemble: Responses generated independently from retrieved
            documents. Each response contributes at most one count per token.

    Returns:
        Mapping from observed token to the number of responses containing it.
        Tokens with frequency zero are never materialized.

    Raises:
        TypeError: If an ensemble item is not a string.
    """

    conteggi: dict[str, int] = {}
    for bozza in bozze_ensemble:
        termini_unici = set(normalizza_e_tokenizza(bozza))
        for termine in termini_unici:
            conteggi[termine] = conteggi.get(termine, 0) + 1
    return conteggi


def _ordina_token(istogramma: Mapping[str, int]) -> list[str]:
    """Order observed tokens by descending count and deterministic tie-break."""

    return [
        token
        for token, _ in sorted(
            istogramma.items(), key=lambda item: (-item[1], item[0])
        )
        if istogramma[token] > 0
    ]


def calcola_gap(istogramma: Mapping[str, int]) -> dict[int, float]:
    """Compute ``d_k = H(k) - H(k+1)`` for all valid ``k``.

    Args:
        istogramma: Positive token counts produced by
            :func:`costruisci_istogramma`.

    Returns:
        One-indexed histogram gaps. An empty or single-token histogram has no
        valid gap and returns an empty mapping.

    Raises:
        ValueError: If a count is negative or non-integral.
    """

    if any(not isinstance(count, int) or count < 0 for count in istogramma.values()):
        raise ValueError("l'istogramma deve contenere conteggi interi non negativi")
    token_ordinati = _ordina_token(istogramma)
    return {
        k: float(istogramma[token_ordinati[k - 1]] - istogramma[token_ordinati[k]])
        for k in range(1, len(token_ordinati))
    }


def sample_gumbel_noise(
    epsilon: float,
    size: int | tuple[int, ...] | None = None,
    rng: np.random.Generator | None = None,
) -> float | np.ndarray:
    """Sample centered Gumbel noise used by FindBestK.

    The paper uses ``Gumbel(2 / epsilon)``.  The location is centered by
    subtracting the Euler-Mascheroni mean; this does not change the argmax
    distribution because the same constant is subtracted from every utility.

    Args:
        epsilon: Privacy parameter of the exponential mechanism.
        size: Number or shape of samples. ``None`` returns one scalar.
        rng: Optional NumPy generator for reproducible experiments.

    Returns:
        A centered Gumbel sample or NumPy array with scale ``2 / epsilon``.
    """

    _validate_positive_finite(epsilon, "epsilon")
    scale = GLOBAL_GAP_SENSITIVITY / epsilon
    samples = _rng_or_default(rng).gumbel(loc=0.0, scale=scale, size=size)
    centered = samples - EULER_MASCHERONI * scale
    if size is None:
        return float(centered)
    return np.asarray(centered)


def _find_best_k_details(
    istogramma: Mapping[str, int],
    epsilon: float,
    r_min_k: int,
    r_max_k: int,
    rng: np.random.Generator | None,
) -> FindBestKResult:
    """Run FindBestK and retain diagnostics for telemetry."""

    _validate_positive_finite(epsilon, "epsilon")
    if r_min_k < 1 or r_max_k < r_min_k:
        raise ValueError("i limiti del regolarizzatore devono soddisfare 1 <= min <= max")
    gaps = calcola_gap(istogramma)
    candidati = [k for k in gaps if r_min_k <= k <= r_max_k]
    if not candidati:
        return FindBestKResult(k_hat=0, scores={}, gaps={}, noise={})

    generator = _rng_or_default(rng)
    scores: dict[int, float] = {}
    noises: dict[int, float] = {}
    candidate_gaps = {k: gaps[k] for k in candidati}
    for k in candidati:
        noise = float(sample_gumbel_noise(epsilon, rng=generator))
        noises[k] = noise
        # r(k) is zero in the configured interval and -infinity outside it.
        scores[k] = candidate_gaps[k] + noise
    k_hat = max(candidati, key=lambda k: (scores[k], -k))
    return FindBestKResult(
        k_hat=k_hat,
        scores=scores,
        gaps=candidate_gaps,
        noise=noises,
    )


def find_best_k(
    istogramma: Mapping[str, int],
    epsilon: float,
    r_min_k: int = DEFAULT_R_MIN_K,
    r_max_k: int = DEFAULT_R_MAX_K,
    rng: np.random.Generator | None = None,
) -> int:
    """Select ``k_hat`` with the exponential mechanism from Algorithm 3.

    Sensitivity argument (Tang et al., 2025, Sec. 5): for adjacent datasets
    differing in one document, one response can change. One token can gain
    one count in ``H(k)`` while another loses one count in ``H(k+1)``, hence
    ``d_k`` has global sensitivity 2 and the Gumbel scale is ``2 / epsilon``.

    Args:
        istogramma: Positive histogram of response-token frequencies.
        epsilon: Privacy parameter allocated to FindBestK.
        r_min_k: Lowest admissible number of keywords.
        r_max_k: Highest admissible number of keywords.
        rng: Optional random generator.

    Returns:
        The selected number of keywords, or zero when no admissible gap
        exists.
    """

    return _find_best_k_details(istogramma, epsilon, r_min_k, r_max_k, rng).k_hat


def top_k_with_ptr(
    istogramma: Mapping[str, int],
    k: int,
    delta: float = DEFAULT_DELTA,
    sigma: float = DEFAULT_SIGMA,
    rng: np.random.Generator | None = None,
    strict_gap_guard: bool = False,
) -> PTRResult:
    """Apply the PTR test from Algorithm 2 and release exact top-k tokens.

    The Gaussian term has distribution ``N(0, 4 sigma^2)`` and the
    subtraction is the Gaussian quantile
    ``Phi(1-delta; 0, 2 sigma)``. Algorithm 2 releases when the resulting
    value is strictly greater than the sensitivity boundary ``2``. For a
    raw gap ``g <= 2``, ``max(2, g)`` makes the false-release probability
    exactly ``delta``; this is the failure event accounted for by Theorem
    A.10. ``strict_gap_guard`` is an optional operational mode that suppresses
    that failure event entirely, but it is not part of the paper's formal
    mechanism and is disabled by default.

    Args:
        istogramma: Positive histogram of response-token frequencies.
        k: Number of top tokens proposed by FindBestK.
        delta: PTR failure probability.
        sigma: Gaussian noise scale parameter from Theorem A.10.
        rng: Optional random generator.
        strict_gap_guard: Do not release when the raw gap is at most two.
            Enable only when the additional operational policy is intended.

    Returns:
        Diagnostic PTR result. ``released_tokens`` is empty on zero-shot.

    Raises:
        ValueError: If parameters are outside the algorithm's domain.
    """

    _validate_delta(delta)
    _validate_positive_finite(sigma, "sigma")
    if not isinstance(k, int) or k < 1:
        raise ValueError("k deve essere un intero positivo")
    token_ordinati = _ordina_token(istogramma)
    if k >= len(token_ordinati):
        raise ValueError("k deve essere minore del numero di token osservati")

    gap = float(
        istogramma[token_ordinati[k - 1]] - istogramma[token_ordinati[k]]
    )
    gaussian_threshold = 2.0 * sigma * NormalDist().inv_cdf(1.0 - delta)
    gaussian_noise = float(_rng_or_default(rng).normal(loc=0.0, scale=2.0 * sigma))
    noisy_gap = max(GLOBAL_GAP_SENSITIVITY, gap) + gaussian_noise - gaussian_threshold
    passed = noisy_gap > GLOBAL_GAP_SENSITIVITY and (
        not strict_gap_guard or gap > GLOBAL_GAP_SENSITIVITY
    )
    released_tokens = tuple(token_ordinati[:k]) if passed else ()
    return PTRResult(
        gap=gap,
        noisy_gap=noisy_gap,
        gaussian_threshold=gaussian_threshold,
        passed=passed,
        released_tokens=released_tokens,
    )


def probabilita_passaggio_ptr(
    gap: float,
    sigma: float,
    delta: float,
    strict_gap_guard: bool = False,
) -> float:
    """Return the analytical probability that Algorithm 2 releases.

    Let ``g`` be the raw gap, ``b = max(2, g)``, and
    ``tau = 2 sigma Phi^{-1}(1-delta)``. Since the Gaussian sample has
    standard deviation ``2 sigma``, the paper's release condition is

    ``b + Z - tau > 2``

    and therefore

    ``Pr[release] = 1 - Phi((tau + 2 - b) / (2 sigma))``.

    For ``g <= 2`` and ``strict_gap_guard=False`` this simplifies exactly to
    ``delta``. The optional guard changes that probability to zero for the
    unstable-gap branch and is deliberately excluded from the formal default.

    Args:
        gap: Non-negative raw histogram gap ``H(k) - H(k+1)``.
        sigma: Positive Gaussian scale parameter.
        delta: PTR failure probability in ``(0, 1)``.
        strict_gap_guard: Whether to suppress all releases for ``gap <= 2``.

    Returns:
        A probability in ``[0, 1]``.
    """

    if not math.isfinite(gap) or gap < 0.0:
        raise ValueError("gap deve essere finito e non negativo")
    _validate_positive_finite(sigma, "sigma")
    _validate_delta(delta)
    if strict_gap_guard and gap <= GLOBAL_GAP_SENSITIVITY:
        return 0.0

    gaussian_threshold = 2.0 * sigma * NormalDist().inv_cdf(1.0 - delta)
    effective_gap = max(GLOBAL_GAP_SENSITIVITY, gap)
    z_score = (
        gaussian_threshold + GLOBAL_GAP_SENSITIVITY - effective_gap
    ) / (2.0 * sigma)
    return max(0.0, min(1.0, 1.0 - NormalDist().cdf(z_score)))


def _log_cosh(value: float) -> float:
    """Compute log(cosh(value)) without overflow for large RDP orders."""

    absolute = abs(value)
    return absolute + math.log1p(math.exp(-2.0 * absolute)) - math.log(2.0)


def epsilon_em_rdp(alpha: float, epsilon: float) -> float:
    """Calculate Theorem A.9's RDP bound for the exponential mechanism.

    Args:
        alpha: Rényi order, strictly greater than one.
        epsilon: Pure-DP parameter of the exponential mechanism.

    Returns:
        ``epsilon_EM(alpha)`` from Tang et al., Theorem A.9.

    Raises:
        ValueError: If either parameter is outside its mathematical domain.
    """

    _validate_positive_finite(epsilon, "epsilon")
    if not math.isfinite(alpha) or alpha <= 1.0:
        raise ValueError("alpha deve essere finito e maggiore di uno")
    log_ratio = _log_cosh((2.0 * alpha - 1.0) * epsilon / 2.0) - _log_cosh(
        epsilon / 2.0
    )
    second_bound = max(0.0, log_ratio / (alpha - 1.0))
    return min(alpha * epsilon**2 / 2.0, second_bound)


def converti_rdp_in_dp(
    rdp_per_ordine: Mapping[float, float], delta: float
) -> tuple[float, float]:
    """Convert a set of RDP values to the tightest ``(epsilon, delta)-DP``.

    Args:
        rdp_per_ordine: Mapping from orders greater than one to RDP losses.
        delta: Conversion failure probability.

    Returns:
        Tuple ``(epsilon, optimal_order)`` using Theorem A.6.

    Raises:
        ValueError: If the mapping is empty or contains invalid orders/losses.
    """

    _validate_delta(delta, "delta di conversione")
    if not rdp_per_ordine:
        raise ValueError("serve almeno un ordine RDP")
    candidati: list[tuple[float, float]] = []
    for alpha, rdp in rdp_per_ordine.items():
        if not math.isfinite(alpha) or alpha <= 1.0:
            raise ValueError("ogni ordine RDP deve essere finito e maggiore di uno")
        if not math.isfinite(rdp) or rdp < 0.0:
            raise ValueError("ogni perdita RDP deve essere finita e non negativa")
        candidati.append((rdp + math.log(1.0 / delta) / (alpha - 1.0), alpha))
    return min(candidati, key=lambda item: item[0])


def _costruisci_account_rdp(
    rdp_find_by_order: Mapping[float, float],
    rdp_ptr_by_order: Mapping[float, float],
    delta_ptr: float,
    delta_conversion: float,
    invocations: int,
) -> RDPAccount:
    """Convert an already-composed RDP account into a result object."""

    if set(rdp_find_by_order) != set(rdp_ptr_by_order):
        raise ValueError("le componenti RDP devono usare gli stessi ordini")
    rdp_per_ordine = {
        alpha: rdp_find_by_order[alpha] + rdp_ptr_by_order[alpha]
        for alpha in rdp_find_by_order
    }
    _validate_delta(delta_ptr, "delta_ptr")
    _validate_delta(delta_conversion, "delta_conversion")
    if not isinstance(invocations, int) or invocations < 1:
        raise ValueError("invocations deve essere un intero positivo")
    delta_total = delta_ptr + delta_conversion
    if delta_total >= 1.0:
        raise ValueError("delta totale deve essere strettamente minore di uno")

    epsilon_dp, optimal_order = converti_rdp_in_dp(
        rdp_per_ordine, delta_conversion
    )
    epsilon_rdp_find = rdp_find_by_order[optimal_order]
    epsilon_rdp_ptr = rdp_ptr_by_order[optimal_order]
    # The two components are kept separate so telemetry and the thesis table
    # can audit composition at the selected order.
    return RDPAccount(
        epsilon_rdp_find_best_k=epsilon_rdp_find,
        epsilon_rdp_top_k_ptr=epsilon_rdp_ptr,
        epsilon_rdp_total=epsilon_rdp_find + epsilon_rdp_ptr,
        epsilon_dp=epsilon_dp,
        optimal_order=optimal_order,
        delta_ptr=delta_ptr,
        delta_conversion=delta_conversion,
        delta_total=delta_total,
        invocations=invocations,
    )


def deriva_sigma_da_budget(
    epsilon_budget: float,
    epsilon_find_best_k: float,
    epsilon_top_k_ptr: float,
    delta: float = DEFAULT_DELTA,
    ordini_rdp: Sequence[float] = DEFAULT_RDP_ORDERS,
) -> float:
    """Derive a PTR ``sigma`` that respects the composed epsilon budget.

    For every candidate order, the available PTR RDP budget is the smaller
    of the allocated PTR share and the remaining composed budget after the
    FindBestK RDP cost and the conversion term.  Theorem A.10 gives
    ``epsilon_ptr_rdp = alpha / (2 sigma^2)``, which is inverted directly.

    Args:
        epsilon_budget: Total epsilon allowed for both mechanisms.
        epsilon_find_best_k: Pure-DP allocation for FindBestK.
        epsilon_top_k_ptr: Allocation reserved for TopKWithPTR.
        delta: PTR and conversion failure probability.
        ordini_rdp: Candidate Rényi orders.

    Returns:
        A positive Gaussian scale compatible with the most permissive valid
        candidate order.

    Raises:
        ValueError: If the allocations cannot fit the total budget.
    """

    _validate_positive_finite(epsilon_budget, "epsilon_budget")
    _validate_positive_finite(epsilon_find_best_k, "epsilon_find_best_k")
    _validate_positive_finite(epsilon_top_k_ptr, "epsilon_top_k_ptr")
    _validate_delta(delta)
    if epsilon_find_best_k + epsilon_top_k_ptr > epsilon_budget + 1e-12:
        raise ValueError("le quote epsilon superano il budget totale")

    if not ordini_rdp:
        raise ValueError("serve almeno un ordine RDP")
    for alpha in ordini_rdp:
        if alpha <= 1.0 or not math.isfinite(alpha):
            raise ValueError("gli ordini RDP devono essere finiti e maggiori di uno")
    conversion_term_by_order = {
        alpha: math.log(1.0 / delta) / (alpha - 1.0) for alpha in ordini_rdp
    }
    sigma_candidates: list[float] = []
    for alpha in ordini_rdp:
        conversion_term = conversion_term_by_order[alpha]
        find_rdp = epsilon_em_rdp(alpha, epsilon_find_best_k)
        ptr_from_total = epsilon_budget - find_rdp - conversion_term
        ptr_from_share = epsilon_top_k_ptr - conversion_term
        ptr_rdp = min(ptr_from_total, ptr_from_share)
        if ptr_rdp > 0.0:
            sigma_candidates.append(math.sqrt(alpha / (2.0 * ptr_rdp)))
    if not sigma_candidates:
        raise ValueError("il budget epsilon non consente una sigma positiva")
    return min(sigma_candidates)


def calcola_account_rdp(
    epsilon_find_best_k: float,
    sigma: float,
    delta_ptr: float = DEFAULT_DELTA,
    delta_conversion: float | None = None,
    ordini_rdp: Sequence[float] = DEFAULT_RDP_ORDERS,
) -> RDPAccount:
    """Compose FindBestK and TopKWithPTR in RDP and convert to DP.

    Args:
        epsilon_find_best_k: Pure-DP parameter of FindBestK.
        sigma: PTR Gaussian scale.
        delta_ptr: Failure probability of the PTR test.
        delta_conversion: Delta used by Theorem A.6. Defaults to
            ``delta_ptr``.
        ordini_rdp: Candidate Rényi orders.

    Returns:
        Full RDP and converted approximate-DP accounting information.
    """

    _validate_positive_finite(epsilon_find_best_k, "epsilon_find_best_k")
    _validate_positive_finite(sigma, "sigma")
    _validate_delta(delta_ptr, "delta_ptr")
    conversion_delta = delta_ptr if delta_conversion is None else delta_conversion
    _validate_delta(conversion_delta, "delta_conversion")
    if not ordini_rdp:
        raise ValueError("serve almeno un ordine RDP")
    for alpha in ordini_rdp:
        if alpha <= 1.0 or not math.isfinite(alpha):
            raise ValueError("gli ordini RDP devono essere finiti e maggiori di uno")
    return _costruisci_account_rdp(
        rdp_find_by_order={
            alpha: epsilon_em_rdp(alpha, epsilon_find_best_k)
            for alpha in ordini_rdp
        },
        rdp_ptr_by_order={
            alpha: alpha / (2.0 * sigma**2) for alpha in ordini_rdp
        },
        delta_ptr=delta_ptr,
        delta_conversion=conversion_delta,
        invocations=1,
    )


class DP_KSA_Filter:
    """Implement the formal DP-KSA keyword extraction mechanism.

    Sensitivity argument (Tang et al., 2025, Sec. 5): for adjacent databases
    ``D`` and ``D'`` differing in one document, the retrieved sets differ in
    one response. Hence histograms ``H`` and ``H'`` differ in one response.
    The utility ``d_k = H(k) - H(k+1)`` has global sensitivity 2: one token
    may gain +1 in ``H(k)`` while the adjacent token loses 1 in ``H(k+1)``.

    Invariants:
        * The histogram contains only observed tokens and is set-valued per
          response.
        * ``d_k = H(k) - H(k+1)`` has global sensitivity 2.
        * The composed RDP account is converted once to approximate DP.
        * ``budget_consumato_epsilon + epsilon_rimasto`` equals the configured
          epsilon budget.

    Args:
        epsilon: Total epsilon budget for FindBestK and TopKWithPTR.
        delta: PTR failure probability. The same value is used as the
            conversion delta unless ``delta_conversion`` is supplied.
        sigma: PTR Gaussian scale. If omitted, it is derived from the
            allocated budget.
        r_min_k: Minimum admissible keyword count for FindBestK.
        r_max_k: Maximum admissible keyword count for FindBestK.
        epsilon_find_best_k: Optional explicit FindBestK allocation.
        epsilon_top_k_ptr: Optional explicit PTR allocation.
        delta_conversion: Optional delta used by RDP conversion.
        rng: Optional random generator for reproducible experiments.
        strict_gap_guard: Optional operational no-release guard for gaps at
            most two. Disabled by default because Algorithm 2 already
            accounts for the ``delta`` failure branch.

    Raises:
        ValueError: If parameters are invalid or the supplied sigma exceeds
            the configured one-invocation budget.
        DPBudgetExhaustedError: If a subsequent invocation would exceed the
            cumulative account.
    """

    def __init__(
        self,
        epsilon: float = DEFAULT_EPSILON,
        delta: float = DEFAULT_DELTA,
        sigma: float | None = None,
        r_min_k: int = DEFAULT_R_MIN_K,
        r_max_k: int = DEFAULT_R_MAX_K,
        epsilon_find_best_k: float | None = None,
        epsilon_top_k_ptr: float | None = None,
        delta_conversion: float | None = None,
        rng: np.random.Generator | None = None,
        strict_gap_guard: bool = False,
    ) -> None:
        _validate_positive_finite(epsilon, "epsilon")
        _validate_delta(delta)
        if delta_conversion is not None:
            _validate_delta(delta_conversion, "delta_conversion")
        if r_min_k < 1 or r_max_k < r_min_k:
            raise ValueError("i limiti del regolarizzatore devono soddisfare 1 <= min <= max")

        find_epsilon = epsilon / 2.0 if epsilon_find_best_k is None else epsilon_find_best_k
        top_epsilon = epsilon / 2.0 if epsilon_top_k_ptr is None else epsilon_top_k_ptr
        _validate_positive_finite(find_epsilon, "epsilon_find_best_k")
        _validate_positive_finite(top_epsilon, "epsilon_top_k_ptr")
        if find_epsilon + top_epsilon > epsilon + 1e-12:
            raise ValueError("le quote epsilon superano il budget totale")

        chosen_sigma = (
            deriva_sigma_da_budget(
                epsilon,
                find_epsilon,
                top_epsilon,
                delta,
            )
            if sigma is None
            else sigma
        )
        _validate_positive_finite(chosen_sigma, "sigma")
        account = calcola_account_rdp(
            find_epsilon,
            chosen_sigma,
            delta_ptr=delta,
            delta_conversion=delta if delta_conversion is None else delta_conversion,
        )
        if account.epsilon_dp > epsilon + 1e-9:
            raise ValueError(
                "sigma non compatibile con il budget epsilon composto: "
                f"richiesto {account.epsilon_dp:.6f}, disponibile {epsilon:.6f}"
            )

        self.epsilon = epsilon
        self.delta = delta
        self.sigma = chosen_sigma
        self.r_min_k = r_min_k
        self.r_max_k = r_max_k
        self.epsilon_find_best_k = find_epsilon
        self.epsilon_top_k_ptr = top_epsilon
        self.delta_conversion = delta if delta_conversion is None else delta_conversion
        # One generator belongs to one filter instance. With rng=None this
        # still gives independent instances a fresh stream while preserving
        # state across repeated calls on the same instance.
        self.rng = rng if rng is not None else np.random.default_rng()
        self.strict_gap_guard = strict_gap_guard
        self.account = account
        self._invocations = 0
        self._rdp_find_per_invocation = {
            alpha: epsilon_em_rdp(alpha, find_epsilon)
            for alpha in DEFAULT_RDP_ORDERS
        }
        self._rdp_ptr_per_invocation = {
            alpha: alpha / (2.0 * chosen_sigma**2)
            for alpha in DEFAULT_RDP_ORDERS
        }

    def _account_for_next_invocation(self) -> RDPAccount:
        """Compose one more invocation and reject an over-budget release."""

        invocation_count = self._invocations + 1
        try:
            candidate = _costruisci_account_rdp(
                rdp_find_by_order={
                    alpha: invocation_count * rdp
                    for alpha, rdp in self._rdp_find_per_invocation.items()
                },
                rdp_ptr_by_order={
                    alpha: invocation_count * rdp
                    for alpha, rdp in self._rdp_ptr_per_invocation.items()
                },
                delta_ptr=invocation_count * self.delta,
                delta_conversion=self.delta_conversion,
                invocations=invocation_count,
            )
        except ValueError as exc:
            raise DPBudgetExhaustedError(
                self.epsilon,
                float("inf"),
                invocation_count * self.delta + self.delta_conversion,
            ) from exc

        if candidate.epsilon_dp > self.epsilon + 1e-9:
            raise DPBudgetExhaustedError(
                self.epsilon,
                candidate.epsilon_dp,
                candidate.delta_total,
            )
        return candidate

    def filtra(self, bozze_ensemble: Sequence[str]) -> EsitoDP:
        """Run FindBestK followed by TopKWithPTR.

        Args:
            bozze_ensemble: Local model responses, one response per retrieved
                document.

        Returns:
            DP-KSA result including released keywords and cumulative privacy
            accounting. The first call has ``numero_invocazione == 1``.

        Raises:
            TypeError: If the ensemble contains non-string responses.
            DPBudgetExhaustedError: If the cumulative account cannot support
                another invocation.
        """

        istogramma = costruisci_istogramma(bozze_ensemble)
        candidate_account = self._account_for_next_invocation()
        token_ordinati = _ordina_token(istogramma)
        gap_per_k = calcola_gap(istogramma)
        find_result = _find_best_k_details(
            istogramma,
            self.epsilon_find_best_k,
            self.r_min_k,
            self.r_max_k,
            self.rng,
        )

        ptr_result: PTRResult | None = None
        if find_result.k_hat > 0:
            ptr_result = top_k_with_ptr(
                istogramma,
                find_result.k_hat,
                delta=self.delta,
                sigma=self.sigma,
                rng=self.rng,
                strict_gap_guard=self.strict_gap_guard,
            )

        released = list(ptr_result.released_tokens) if ptr_result else []
        released_set = set(released)
        discarded = [token for token in token_ordinati if token not in released_set]
        consumed = candidate_account.epsilon_dp
        remaining = self.epsilon - consumed
        if remaining < -1e-9:
            raise RuntimeError("invariante del budget epsilon violato")
        remaining = max(0.0, remaining)
        result = EsitoDP(
            conteggi_reali=dict(istogramma),
            token_ordinati=token_ordinati,
            gap_per_k=gap_per_k,
            punteggi_find_best_k=find_result.scores,
            rumore_gumbel=find_result.noise,
            k_hat=find_result.k_hat,
            gap_ptr=ptr_result.gap if ptr_result else None,
            gap_ptr_rumoroso=ptr_result.noisy_gap if ptr_result else None,
            soglia_gaussiana_ptr=ptr_result.gaussian_threshold if ptr_result else None,
            ptr_superato=ptr_result.passed if ptr_result else False,
            parole_rilasciate=released,
            parole_scartate=discarded,
            epsilon_budget=self.epsilon,
            delta=self.delta,
            sigma=self.sigma,
            epsilon_find_best_k=self.epsilon_find_best_k,
            epsilon_top_k_ptr=self.epsilon_top_k_ptr,
            epsilon_rdp_find_best_k=candidate_account.epsilon_rdp_find_best_k,
            epsilon_rdp_top_k_ptr=candidate_account.epsilon_rdp_top_k_ptr,
            epsilon_rdp_totale=candidate_account.epsilon_rdp_total,
            ordine_rdp=candidate_account.optimal_order,
            budget_consumato_epsilon=consumed,
            budget_consumato_delta=candidate_account.delta_total,
            epsilon_rimasto=remaining,
            numero_invocazione=candidate_account.invocations,
        )
        self._invocations = candidate_account.invocations
        self.account = candidate_account
        return result
