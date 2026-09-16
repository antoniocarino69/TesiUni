"""Adaptive ensemble scheduler for the DP-KSA edge/cloud pipeline.

The scheduler is intentionally conservative: local inference is modeled as a
sequential workload, the cloud phase consumes a fixed latency estimate, and
the resulting ensemble size is clamped to the range supported by the thesis
experiments. Privacy allocation is independent from the latency decision and
is accounted for with the same RDP orders used by :mod:`core.privacy`.

External dependencies:
    Only the Python standard library and :mod:`core.privacy` are required.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .privacy import DEFAULT_DELTA, deriva_sigma_da_budget, probabilita_passaggio_ptr

__all__ = [
    "AdaptiveScheduler",
    "DecisioneScheduler",
    "PrivacyBudgetExhaustedError",
]

N_MIN = 5
N_MAX = 40
DEFAULT_TEMPO_CLOUD_MS = 150.0
DEFAULT_RTT_MS = 50.0
DEFAULT_LATENZA_MASSIMA_MS = 1500.0
DEFAULT_TOK_PER_SEC_PREFILL = 250.0
DEFAULT_TOK_PER_SEC_GENERAZIONE = 50.0
DEFAULT_MAX_TOKENS = 30
DEFAULT_EPSILON_SPLIT = 0.5
MIN_EPSILON_REQUIRED = 1e-6
PTR_REPRESENTATIVE_GAP = 3.0
DEFAULT_SFORAMENTO_K = 0.0


@dataclass(frozen=True, slots=True)
class DecisioneScheduler:
    """Decisione prodotta dallo scheduler.

    Args:
        n_ensemble: Number of local inferences to execute.
        sigma: Gaussian scale passed to TopKWithPTR.
        epsilon_find_best_k: Epsilon allocation for FindBestK.
        epsilon_top_k_ptr: Epsilon allocation reserved for TopKWithPTR.
        tempo_stimato_ms: End-to-end latency estimate.
        ptr_pass_rate_attesa: Heuristic PTR pass-rate estimate.
        motivazione: Human-readable explanation of the decision.
        sla_fattibile: Whether the estimate fits within the SLA.
        modalita: "ensemble" or "zero_shot".
        sforamento_previsto_ms: Expected SLA overrun in ms (>= 0) for the
            plan that will actually be executed.
        sforamento_accettato: Whether the overrun was accepted per k policy.
        k_sforamento: The k coefficient used for tolerance calculation.
        sforamento_piano_minimo_ms: Overrun the N_MIN plan would cause; the
            quantity the tolerance policy compares with ``k * E2E_cloud``.
        tolleranza_sforamento_ms: ``k_sforamento * (latenza_rete + tempo_cloud)``.
    """

    n_ensemble: int
    sigma: float
    epsilon_find_best_k: float
    epsilon_top_k_ptr: float
    tempo_stimato_ms: float
    ptr_pass_rate_attesa: float
    motivazione: str
    sla_fattibile: bool = True
    modalita: str = "ensemble"
    sforamento_previsto_ms: float = 0.0
    sforamento_accettato: bool = False
    k_sforamento: float = 0.0
    sforamento_piano_minimo_ms: float = 0.0
    tolleranza_sforamento_ms: float = 0.0


class PrivacyBudgetExhaustedError(ValueError):
    """Raised when no valid DP allocation can be derived from epsilon.

    Args:
        epsilon_rimasto: Epsilon available when the decision was requested.
        min_epsilon_richiesto: Minimum operational epsilon required by the
            configured RDP conversion grid.
    """

    def __init__(self, epsilon_rimasto: float, min_epsilon_richiesto: float) -> None:
        self.epsilon_rimasto = epsilon_rimasto
        self.min_epsilon_richiesto = min_epsilon_richiesto
        super().__init__(
            "Budget privacy insufficiente: "
            f"epsilon rimasto={epsilon_rimasto:.6g}, "
            f"minimo richiesto={min_epsilon_richiesto:.6g}"
        )


def _validate_finite_non_negative(value: float, name: str) -> None:
    """Validate a finite non-negative latency or token value."""

    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} deve essere finito e non negativo")


class AdaptiveScheduler:
    """Choose the ensemble size under latency and privacy constraints.

    Invariants:
        * ``n_ensemble == 0`` or ``N_MIN <= n_ensemble <= N_MAX``.
        * The two epsilon allocations sum to at most the requested budget.
        * ``sigma`` is derived from the composed RDP budget and is positive.

    Args:
        n_min: Minimum ensemble size required for useful aggregation.
        n_max: Maximum ensemble size allowed by the deployment policy.
        max_tokens: Maximum completion tokens used in the local-time model.
        epsilon_split: Fraction of epsilon allocated to FindBestK.
    """

    N_MIN = N_MIN
    N_MAX = N_MAX

    def __init__(
        self,
        n_min: int = N_MIN,
        n_max: int = N_MAX,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        epsilon_split: float = DEFAULT_EPSILON_SPLIT,
    ) -> None:
        if n_min < 1 or n_max < n_min:
            raise ValueError("i limiti N devono soddisfare 1 <= n_min <= n_max")
        if max_tokens < 1:
            raise ValueError("max_tokens deve essere positivo")
        if not math.isfinite(epsilon_split) or not 0.0 < epsilon_split < 1.0:
            raise ValueError("epsilon_split deve essere strettamente tra 0 e 1")
        self.n_min = n_min
        self.n_max = n_max
        self.max_tokens = max_tokens
        self.epsilon_split = epsilon_split

    @staticmethod
    def _stima_tempi_locali(
        token_per_documento: Sequence[int],
        tok_per_sec_prefill: float,
        tok_per_sec_generazione: float,
        max_tokens: int,
    ) -> list[float]:
        """Estimate sequential local inference times in milliseconds."""

        if tok_per_sec_prefill <= 0 or not math.isfinite(tok_per_sec_prefill):
            raise ValueError("tok_per_sec_prefill deve essere positivo e finito")
        if tok_per_sec_generazione <= 0 or not math.isfinite(tok_per_sec_generazione):
            raise ValueError("tok_per_sec_generazione deve essere positivo e finito")
        if max_tokens < 1:
            raise ValueError("max_tokens deve essere positivo")
        tempi: list[float] = []
        for token in token_per_documento:
            if not isinstance(token, int) or token < 0:
                raise ValueError("token_per_documento deve contenere interi non negativi")
            tempo_prefill_ms = token / tok_per_sec_prefill * 1000.0
            tempo_generazione_ms = max_tokens / tok_per_sec_generazione * 1000.0
            tempi.append(tempo_prefill_ms + tempo_generazione_ms)
        return tempi

    @staticmethod
    def _stima_ptr_pass_rate(epsilon_top_k_ptr: float, sigma: float, delta: float) -> float:
        """Estimate PTR success using a documented representative gap.

        The scheduler does not see the private histogram yet, so it cannot
        evaluate the actual ``d_k``. A gap of three is used as the smallest
        stable gap above the release boundary. This is the conditional
        probability from Algorithm 2, not a corpus prediction or a function
        of N. The legacy field name is retained for API compatibility.
        """

        return probabilita_passaggio_ptr(PTR_REPRESENTATIVE_GAP, sigma, delta)

    def schedule(
        self,
        token_per_documento: Sequence[int],
        epsilon_budget: float,
        delta: float = DEFAULT_DELTA,
        latenza_rete_ms: float = DEFAULT_RTT_MS,
        latenza_massima_ms: float = DEFAULT_LATENZA_MASSIMA_MS,
        tempo_cloud_ms: float = DEFAULT_TEMPO_CLOUD_MS,
        tok_per_sec_prefill: float = DEFAULT_TOK_PER_SEC_PREFILL,
        tok_per_sec_generazione: float = DEFAULT_TOK_PER_SEC_GENERAZIONE,
        fixed_n: int | None = None,
        k_sforamento: float = DEFAULT_SFORAMENTO_K,
    ) -> DecisioneScheduler:
        """Compute an adaptive ensemble decision.

        Args:
            token_per_documento: PUBLIC configured prompt caps, not lengths measured
                from private documents. Supply a fixed number of public slots.
            epsilon_budget: Total epsilon available for DP-KSA.
            delta: PTR failure probability.
            latenza_rete_ms: Estimated cloud round-trip latency.
            latenza_massima_ms: User-facing end-to-end latency SLA.
            tempo_cloud_ms: Estimated remote generation latency.
            tok_per_sec_prefill: Measured local prompt-processing throughput.
            tok_per_sec_generazione: Measured local generation throughput.
            fixed_n: Experimental baseline; forces this N. ``0`` forces
                zero-shot and is the ``--force-zero-shot`` path.
            k_sforamento: Tolerance coefficient. ``0`` keeps the conservative
                behaviour (SLA incompatible with N_MIN yields N=0). With
                ``k > 0`` the N_MIN plan is adopted when its expected overrun
                stays within ``k * (latenza_rete_ms + tempo_cloud_ms)``.

        Returns:
            A :class:`DecisioneScheduler` with the selected N and privacy
            parameters.

        Raises:
            PrivacyBudgetExhaustedError: If epsilon cannot support a valid
                RDP allocation.
            ValueError: If public inputs are invalid.
        """

        if not token_per_documento:
            raise ValueError("token_per_documento non può essere vuoto")
        if not math.isfinite(epsilon_budget) or epsilon_budget <= 0.0:
            raise PrivacyBudgetExhaustedError(
                epsilon_budget, MIN_EPSILON_REQUIRED
            )
        _validate_finite_non_negative(latenza_rete_ms, "latenza_rete_ms")
        _validate_finite_non_negative(latenza_massima_ms, "latenza_massima_ms")
        _validate_finite_non_negative(tempo_cloud_ms, "tempo_cloud_ms")
        _validate_finite_non_negative(delta, "delta")
        _validate_finite_non_negative(k_sforamento, "k_sforamento")
        if not 0.0 < delta < 0.5:
            raise ValueError("delta PTR deve essere tra 0 e 0.5 (delta totale = 2*delta)")

        numero_documenti = len(token_per_documento)
        if numero_documenti < self.n_min:
            raise ValueError(
                f"Servono almeno {self.n_min} slot pubblici per pianificare un ensemble "
                f"significativo; ne sono stati forniti {numero_documenti}."
            )
        n_massimo_disponibile = min(self.n_max, numero_documenti)
        # fixed_n == 0 is the explicit zero-shot path; any other value must be
        # a realizable ensemble size.
        if fixed_n is not None and fixed_n != 0:
            if not self.n_min <= fixed_n <= n_massimo_disponibile:
                raise ValueError("fixed_n deve essere tra n_min e i candidati pubblici disponibili")

        tempi_locali = self._stima_tempi_locali(
            token_per_documento,
            tok_per_sec_prefill,
            tok_per_sec_generazione,
            self.max_tokens,
        )
        tempo_residuo = latenza_massima_ms - latenza_rete_ms - tempo_cloud_ms
        capacita_temporale = 0
        tempo_locale_capacita = 0.0
        if tempo_residuo > 0.0:
            for tempo_documento in tempi_locali[:n_massimo_disponibile]:
                if tempo_locale_capacita + tempo_documento > tempo_residuo:
                    break
                tempo_locale_capacita += tempo_documento
                capacita_temporale += 1

        n_ensemble = min(n_massimo_disponibile, capacita_temporale)
        if n_ensemble < self.n_min:
            n_ensemble = 0
        # The fixed baseline intentionally runs even when its estimate exceeds
        # SLA; this is explicit in sla_fattibile and used for experiments only.
        if fixed_n is not None:
            n_ensemble = fixed_n
        tempo_locale_scelto = sum(tempi_locali[:n_ensemble])
        tempo_stimato = latenza_rete_ms + tempo_cloud_ms + tempo_locale_scelto

        # Tolerance policy (A2): the minimum plan is evaluated against a
        # tolerance proportional to the cloud round trip, so an SLA that is
        # slightly too tight still buys local work instead of dropping it.
        # ``tolleranza_ms`` is an estimate, not a guaranteed deadline.
        e2e_cloud_ms = latenza_rete_ms + tempo_cloud_ms
        tolleranza_ms = k_sforamento * e2e_cloud_ms
        tempo_locale_n_min = sum(tempi_locali[:self.n_min])
        tempo_stimato_n_min = e2e_cloud_ms + tempo_locale_n_min
        sforamento_piano_minimo_ms = max(0.0, tempo_stimato_n_min - latenza_massima_ms)
        sforamento_accettato = False
        if fixed_n is None and n_ensemble == 0 and k_sforamento > 0.0:
            if sforamento_piano_minimo_ms <= tolleranza_ms:
                n_ensemble = self.n_min
                tempo_locale_scelto = tempo_locale_n_min
                tempo_stimato = tempo_stimato_n_min
                sforamento_accettato = True
        # ``sforamento_previsto_ms`` always describes the plan that will be
        # executed, so it stays comparable with the measured overrun.
        sforamento_previsto_ms = max(0.0, tempo_stimato - latenza_massima_ms)

        epsilon_find = epsilon_budget * self.epsilon_split
        epsilon_top = epsilon_budget - epsilon_find
        try:
            sigma = deriva_sigma_da_budget(
                epsilon_budget,
                epsilon_find,
                epsilon_top,
                delta,
            )
        except ValueError as exc:
            raise PrivacyBudgetExhaustedError(
                epsilon_budget, max(MIN_EPSILON_REQUIRED, epsilon_budget)
            ) from exc

        ptr_pass_rate = self._stima_ptr_pass_rate(epsilon_top, sigma, delta)
        if fixed_n == 0:
            motivo_tempo = "Zero-shot forzato dall'utente; i documenti non vengono consultati."
        elif fixed_n is not None:
            motivo_tempo = f"Baseline fissa N={n_ensemble}."
        elif sforamento_accettato:
            motivo_tempo = (
                f"SLA stimato incompatibile con {self.n_min} inferenze; "
                f"sforamento previsto {sforamento_previsto_ms:.1f} ms entro la tolleranza "
                f"k={k_sforamento:.2f}×E2E_cloud ({tolleranza_ms:.1f} ms); "
                f"pianifico N_MIN={self.n_min}. La tolleranza è una stima, non una scadenza garantita."
            )
        elif n_ensemble == 0 and k_sforamento > 0.0:
            motivo_tempo = (
                f"SLA stimato incompatibile con {self.n_min} inferenze; "
                f"sforamento previsto {sforamento_piano_minimo_ms:.1f} ms oltre la tolleranza "
                f"k={k_sforamento:.2f}×E2E_cloud ({tolleranza_ms:.1f} ms); "
                "fallback zero-shot senza consultare i documenti."
            )
        elif n_ensemble == 0:
            motivo_tempo = (
                f"SLA stimato incompatibile con {self.n_min} inferenze; "
                f"sforamento previsto {sforamento_piano_minimo_ms:.1f} ms, "
                "tolleranza disattivata (k=0); "
                "fallback zero-shot senza consultare i documenti."
            )
        else:
            motivo_tempo = f"La latenza residua stimata consente N={n_ensemble}."
        if tempo_stimato > latenza_massima_ms and not sforamento_accettato:
            motivo_tempo += " SLA non fattibile secondo le stime configurate."
        motivazione = (
            f"{motivo_tempo} RTT={latenza_rete_ms:.1f} ms, "
            f"cloud={tempo_cloud_ms:.1f} ms, "
            f"tempo stimato={tempo_stimato:.1f} ms. "
            f"Budget epsilon partizionato "
            f"{self.epsilon_split:.0%}/{1.0 - self.epsilon_split:.0%}: "
            f"FindBestK={epsilon_find:.4f}, TopKWithPTR={epsilon_top:.4f}; "
            f"P(PTR | gap pubblico di riferimento=3)={ptr_pass_rate:.6%}; "
            "non è una previsione del rilascio sul corpus."
        )
        return DecisioneScheduler(
            n_ensemble=n_ensemble,
            sigma=sigma,
            epsilon_find_best_k=epsilon_find,
            epsilon_top_k_ptr=epsilon_top,
            tempo_stimato_ms=tempo_stimato,
            ptr_pass_rate_attesa=ptr_pass_rate,
            motivazione=motivazione,
            sla_fattibile=tempo_stimato <= latenza_massima_ms,
            modalita="ensemble" if n_ensemble else "zero_shot",
            sforamento_previsto_ms=sforamento_previsto_ms,
            sforamento_accettato=sforamento_accettato,
            k_sforamento=k_sforamento,
            sforamento_piano_minimo_ms=sforamento_piano_minimo_ms,
            tolleranza_sforamento_ms=tolleranza_ms,
        )

    # Italian aliases keep the public API consistent with the rest of the PoC
    # without duplicating the scheduling implementation.
    decidi = schedule
    pianifica = schedule
