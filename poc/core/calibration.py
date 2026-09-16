"""Automatic local inference throughput calibration on public texts.

Responsibilities:
    * Generate public calibration probes at representative prompt lengths.
    * Run a small number of trial inferences and measure real throughput.
    * Return calibrated values consumed by the adaptive scheduler.

The calibration texts are fixed public strings, never derived from the
user corpus. Throughput measurements are session-scoped: they reflect
the current machine, thermal state, and model version.

External dependencies:
    Only the Python standard library and :mod:`core.model_config`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "CALIBRATION_MAX_TOKENS",
    "CALIBRATION_QUERY",
    "DEFAULT_PROBES_PER_LENGTH",
    "DEFAULT_TARGET_LENGTHS",
    "ProvaCalibrazione",
    "RisultatoCalibrazione",
    "calibra",
    "genera_testo_calibrazione",
]

DEFAULT_TARGET_LENGTHS: tuple[int, ...] = (256, 512, 1024)
DEFAULT_PROBES_PER_LENGTH = 1
CALIBRATION_MAX_TOKENS = 5
CALIBRATION_QUERY = "calibration probe"
_PUBLIC_SENTENCE = "The calibration probe measures local throughput. "
_CHARS_PER_TOKEN_APPROX = 4


@dataclass(frozen=True, slots=True)
class ProvaCalibrazione:
    """One calibration inference at a specific target length."""

    target_tokens: int
    prompt_tokens: int
    completion_tokens: int
    prefill_tps: float
    generation_tps: float
    durata_ms: float


@dataclass(frozen=True, slots=True)
class RisultatoCalibrazione:
    """Aggregated calibration outcome for the session."""

    prefill_tps: float
    generation_tps: float
    calibration_ms: float
    prove_eseguite: int
    dettagli: tuple[ProvaCalibrazione, ...] = ()


def genera_testo_calibrazione(target_tokens: int) -> str:
    """Build a public text of approximately ``target_tokens`` tokens.

    Uses a rough character-to-token ratio; the real token count depends on
    the model tokenizer and is measured during the calibration inference.
    """

    if target_tokens < 1:
        raise ValueError("target_tokens deve essere positivo")
    target_chars = target_tokens * _CHARS_PER_TOKEN_APPROX
    repetitions = max(1, target_chars // len(_PUBLIC_SENTENCE) + 1)
    return (_PUBLIC_SENTENCE * repetitions)[:target_chars]


def _throughput_da_prova(
    prompt_tokens: int,
    completion_tokens: int,
    durata_sec: float,
    tempo_prefill_stimato_sec: float,
) -> tuple[float, float]:
    """Derive prefill and generation throughput from one inference."""

    if durata_sec <= 0.0:
        return 0.0, 0.0
    prefill_sec = max(tempo_prefill_stimato_sec, 0.0)
    generation_sec = max(durata_sec - prefill_sec, 0.0)
    prefill_tps = prompt_tokens / prefill_sec if prefill_sec > 0.0 else 0.0
    generation_tps = completion_tokens / generation_sec if generation_sec > 0.0 else 0.0
    return prefill_tps, generation_tps


def calibra(
    engine: object,
    target_lengths: Sequence[int] = DEFAULT_TARGET_LENGTHS,
    probes_per_length: int = DEFAULT_PROBES_PER_LENGTH,
    max_tokens: int = CALIBRATION_MAX_TOKENS,
) -> RisultatoCalibrazione:
    """Measure real inference throughput on public calibration texts.

    Args:
        engine: An object exposing ``genera_bozza(contesto, domanda, max_tokens)``
            compatible with :class:`core.engine.LocalNeuralEngine`.
        target_lengths: Prompt token lengths to probe.
        probes_per_length: Inferences per target length.
        max_tokens: Maximum completion tokens per calibration inference.

    Returns:
        A :class:`RisultatoCalibrazione` with averaged throughput values.

    Raises:
        ValueError: If inputs are invalid.
        RuntimeError: If the engine fails during calibration.
    """

    if not target_lengths:
        raise ValueError("target_lengths non può essere vuoto")
    if probes_per_length < 1:
        raise ValueError("probes_per_length deve essere positivo")
    if max_tokens < 1:
        raise ValueError("max_tokens deve essere positivo")
    for length in target_lengths:
        if length < 1:
            raise ValueError("tutte le target_lengths devono essere positive")

    t_start = time.perf_counter()
    prove: list[ProvaCalibrazione] = []

    for target in target_lengths:
        testo = genera_testo_calibrazione(target)
        for _ in range(probes_per_length):
            output = engine.genera_bozza(  # type: ignore[union-attr]
                testo, CALIBRATION_QUERY, max_tokens=max_tokens,
            )
            prefill_tps, generation_tps = _throughput_da_prova(
                output.prompt_tokens,
                output.completion_tokens,
                output.durata_totale_sec,
                output.tempo_prefill_stimato_sec,
            )
            prove.append(ProvaCalibrazione(
                target_tokens=target,
                prompt_tokens=output.prompt_tokens,
                completion_tokens=output.completion_tokens,
                prefill_tps=prefill_tps,
                generation_tps=generation_tps,
                durata_ms=output.durata_totale_sec * 1000.0,
            ))

    calibration_ms = (time.perf_counter() - t_start) * 1000.0

    prefill_values = [p.prefill_tps for p in prove if p.prefill_tps > 0.0]
    generation_values = [p.generation_tps for p in prove if p.generation_tps > 0.0]
    avg_prefill = sum(prefill_values) / len(prefill_values) if prefill_values else 0.0
    avg_generation = (
        sum(generation_values) / len(generation_values) if generation_values else 0.0
    )

    return RisultatoCalibrazione(
        prefill_tps=avg_prefill,
        generation_tps=avg_generation,
        calibration_ms=calibration_ms,
        prove_eseguite=len(prove),
        dettagli=tuple(prove),
    )
