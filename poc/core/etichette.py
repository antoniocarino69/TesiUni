"""Experimental utility labels for the prototype (A3).

The labels are post-hoc, non-DP metadata attached to each pipeline run.
They do not change the prompt, the query, the sequence of calls or the
behaviour of the prototype. They are heuristics applied to the cloud
response and the DP release; they can produce false positives and false
negatives and must be presented as such.

The four labels defined in CONCEZIONE §4 are:

* ``insufficienti`` — the DP filter released no keywords.
* ``errore`` — the cloud provider failed or returned no text.
* ``completo`` — keywords were released and the cloud response reuses at
  least one of them, with no known abstention pattern. For the ticket
  scenario the heuristic is stricter: at least one expected procedural
  step appears in the response, and steps appear in the expected order.
* ``degradato`` — keywords were released and the response arrived, but
  neither ``completo`` heuristic is satisfied.

Priority order:

1. ``insufficienti`` when the release list is empty (zero-shot is also
   treated as a release observation; the prototype intentionally did not
   call the cloud with private content).
2. ``errore`` when the provider reports an error or returns empty text.
3. ``completo`` when the response reuses a released keyword (and, if
   references are provided, the procedural steps match).
4. ``degradato`` otherwise.

The module is intentionally small and dependency-free so it can be
unit-tested in isolation and reused in benchmarks.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "ASTENSIONE_PATTERN",
    "EsitoRisultato",
    "Label",
    "PatternRiferimento",
    "classifica_risultato",
]


Label = Literal["insufficienti", "errore", "completo", "degradato"]


# Patterns are intentionally conservative: we only flag an abstention
# when the response is short and the phrase is a clear refusal. The
# goal is to group runs for discussion, not to certify correctness.
ASTENSIONE_PATTERN: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnon\s+lo\s+so\b", re.IGNORECASE),
    re.compile(r"\bnon\s+è\s+possibile\s+rispondere\b", re.IGNORECASE),
    re.compile(r"\binformazioni\s+insufficienti\b", re.IGNORECASE),
    re.compile(r"\bmi\s+dispiace,?\s+non\s+posso\b", re.IGNORECASE),
    re.compile(r"\bnon\s+riesco\s+a\s+rispondere\b", re.IGNORECASE),
    re.compile(r"\bi\s+cannot\s+answer\b", re.IGNORECASE),
    re.compile(r"\bnot\s+enough\s+information\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class PatternRiferimento:
    """Reference procedural steps used by the strict ticket heuristic.

    Each step is a substring that must appear in the cloud response, in
    the order given. The label is ``completo`` only when every step is
    present in order; otherwise the response is ``degradato``.
    """

    passaggi: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "passaggi", tuple(self.passaggi))


@dataclass(frozen=True, slots=True)
class EsitoRisultato:
    """A single experimental label with a short diagnostic note.

    Attributes:
        label: One of ``insufficienti``, ``errore``, ``completo``,
            ``degradato``.
        motivazione: Short human-readable note explaining why the label
            was chosen; useful in traces and reports.
        riferimenti_usati: Whether the strict ticket heuristic was
            applied (i.e. at least one ``PatternRiferimento`` was
            supplied).
    """

    label: Label
    motivazione: str
    riferimenti_usati: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "motivazione": self.motivazione,
            "riferimenti_usati": self.riferimenti_usati,
        }


class _DecisioneLike:
    """Duck-typed protocol: any object exposing ``n_ensemble`` and ``modalita``."""

    n_ensemble: int
    modalita: str


class _DpLike:
    """Duck-typed protocol: any object exposing the DP release attributes."""

    parole_rilasciate: list[str]
    ptr_superato: bool
    k_hat: int


class _RispostaLike:
    """Duck-typed protocol: any object exposing the cloud response attributes."""

    risposta_testuale: str
    errore: str | None


def _contiene_astensione(testo: str) -> bool:
    return any(p.search(testo) for p in ASTENSIONE_PATTERN)


def _riusa_keyword(testo: str, parole: Iterable[str]) -> bool:
    testo_norm = testo.casefold()
    for parola in parole:
        if not parola:
            continue
        if parola.casefold() in testo_norm:
            return True
    return False


def _passaggi_in_ordine(
    testo: str, passaggi: tuple[str, ...]
) -> bool:
    """True when every step appears in ``testo`` in the given order.

    The check is substring-based: each step must occur after the
    previous one in the response. Case-insensitive.
    """
    posizione = -1
    testo_norm = testo.casefold()
    for passo in passaggi:
        idx = testo_norm.find(passo.casefold(), posizione + 1)
        if idx < 0:
            return False
        posizione = idx
    return True


def _verifica_ticket(
    testo: str,
    riferimenti: tuple[PatternRiferimento, ...],
) -> tuple[bool, str]:
    """Apply the strict ticket heuristic.

    Returns ``(completo, motivazione)``. If more than one reference is
    supplied we evaluate each in turn and accept the response when at
    least one matches in full; the first match wins.
    """
    for idx, riferimento in enumerate(riferimenti):
        if not riferimento.passaggi:
            continue
        if _passaggi_in_ordine(testo, riferimento.passaggi):
            return (
                True,
                f"riferimento #{idx + 1}: {len(riferimento.passaggi)} passaggi in ordine",
            )
    totale = sum(len(r.passaggi) for r in riferimenti)
    if totale == 0:
        return False, ""
    return (
        False,
        f"riferimenti non soddisfatti ({totale} passaggi attesi totali)",
    )


def classifica_risultato(
    *,
    decisione: Any,
    dp: Any | None,
    risposta: Any | None,
    riferimenti: Iterable[PatternRiferimento] = (),
) -> EsitoRisultato:
    """Classify a single run with one of the four experimental labels.

    Args:
        decisione: The scheduler decision. ``n_ensemble == 0`` triggers
            the ``insufficienti`` branch (zero-shot is treated as a
            release observation regardless of the cloud response).
        dp: The DP filter result, with the released keywords. ``None``
            is treated as ``parole_rilasciate == []`` for robustness.
        risposta: The cloud response. ``None`` is treated as an error.
        riferimenti: Optional ticket-style references for the strict
            heuristic.

    Returns:
        A :class:`EsitoRisultato` with the chosen label, a short
        motivation, and a flag indicating whether the strict heuristic
        was applied.
    """
    parole = list(dp.parole_rilasciate) if dp is not None else []
    riferimenti_tuple = tuple(riferimenti)
    riferimenti_usati = bool(riferimenti_tuple)

    # 1. Release observation (highest priority: zero-shot is intentional).
    if decisione.n_ensemble == 0 or not parole:
        motivo = (
            "zero-shot: nessuna inferenza locale pianificata"
            if decisione.n_ensemble == 0
            else "filtro DP-KSA non ha rilasciato keyword"
        )
        return EsitoRisultato(
            label="insufficienti",
            motivazione=motivo,
            riferimenti_usati=riferimenti_usati,
        )

    # 2. Provider observation.
    if risposta is None or risposta.errore is not None:
        return EsitoRisultato(
            label="errore",
            motivazione=f"provider error: {risposta.errore if risposta else 'no response'}",
            riferimenti_usati=riferimenti_usati,
        )
    testo = risposta.risposta_testuale or ""
    if not testo.strip():
        return EsitoRisultato(
            label="errore",
            motivazione="risposta cloud vuota",
            riferimenti_usati=riferimenti_usati,
        )

    # 3. Completeness heuristics (keyword reuse + ticket references).
    if _contiene_astensione(testo):
        return EsitoRisultato(
            label="degradato",
            motivazione="risposta cloud contiene pattern di astensione",
            riferimenti_usati=riferimenti_usati,
        )

    if riferimenti_usati:
        ok, motivo = _verifica_ticket(testo, riferimenti_tuple)
        return EsitoRisultato(
            label="completo" if ok else "degradato",
            motivazione=motivo,
            riferimenti_usati=True,
        )

    if _riusa_keyword(testo, parole):
        return EsitoRisultato(
            label="completo",
            motivazione="almeno una keyword rilasciata ripresa nella risposta",
            riferimenti_usati=False,
        )

    return EsitoRisultato(
        label="degradato",
        motivazione="keyword rilasciate ma non riprese nella risposta cloud",
        riferimenti_usati=False,
    )
