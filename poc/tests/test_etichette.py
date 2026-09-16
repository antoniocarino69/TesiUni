"""Tests for the experimental utility labels (A3).

The labels are heuristic, post-hoc, non-DP metadata. They do not change
behaviour or privacy guarantees; they help group runs in the report JSON
and in the Langfuse traces. False positives and false negatives are
expected and documented in CONCEZIONE §4.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.etichette import (
    ASTENSIONE_PATTERN,
    PatternRiferimento,
    classifica_risultato,
)


def _dp(*parole: str, ptr_superato: bool = True, k_hat: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        parole_rilasciate=list(parole),
        ptr_superato=ptr_superato,
        k_hat=k_hat,
    )


def _risposta(testo: str | None = None, errore: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        risposta_testuale=testo or "",
        errore=errore,
        simulato=False,
    )


def test_insufficienti_quando_il_filtro_non_rilascia_parole() -> None:
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp(),
        risposta=_risposta("Una risposta qualunque basata sulla conoscenza generale."),
    )
    assert esito.label == "insufficienti"
    assert esito.motivazione  # non vuota, utile per debug


def test_errore_quando_il_provider_fallisce() -> None:
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha"),
        risposta=_risposta(errore="provider_error"),
    )
    assert esito.label == "errore"


def test_errore_quando_la_risposta_e_vuota() -> None:
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha"),
        risposta=_risposta(""),
    )
    assert esito.label == "errore"


def test_completo_quando_la_risposta_riusa_le_keyword() -> None:
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha", "beta"),
        risposta=_risposta(
            "La procedura richiede alpha come primo passo e beta come verifica finale."
        ),
    )
    assert esito.label == "completo"


def test_completo_non_scattato_da_pattern_di_astensione() -> None:
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha"),
        risposta=_risposta(
            "Con queste informazioni non è possibile rispondere in modo utile."
        ),
    )
    assert esito.label == "degradato"


@pytest.mark.parametrize(
    "testo",
    [
        "Non lo so con certezza.",
        "non è possibile rispondere con queste informazioni",
        "Informazioni insufficienti per rispondere.",
        "Mi dispiace, non posso aiutarti.",
        "I cannot answer with the available information.",
    ],
)
def test_pattern_astensione_noti(testo: str) -> None:
    assert any(p.search(testo) for p in ASTENSIONE_PATTERN), testo


def test_degradato_quando_rilascio_non_riusato() -> None:
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha", "beta"),
        risposta=_risposta(
            "La capitale è Roma, una città con una storia millenaria."
        ),
    )
    assert esito.label == "degradato"


def test_ticket_completo_con_passaggi_in_ordine() -> None:
    riferimenti = [
        PatternRiferimento(passaggi=["accedi al portale", "verifica credenziali", "conferma"]),
    ]
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("portale", "credenziali", "conferma"),
        risposta=_risposta(
            "Per procedere: accedi al portale, poi verifica credenziali e infine conferma."
        ),
        riferimenti=riferimenti,
    )
    assert esito.label == "completo"


def test_ticket_degradato_se_passaggi_mancano() -> None:
    riferimenti = [
        PatternRiferimento(passaggi=["accedi al portale", "verifica credenziali", "conferma"]),
    ]
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("portale", "credenziali"),
        risposta=_risposta(
            "La procedura richiede solo di accedere al portale."
        ),
        riferimenti=riferimenti,
    )
    assert esito.label == "degradato"


def test_ticket_degradato_se_ordine_sbagliato() -> None:
    riferimenti = [
        PatternRiferimento(passaggi=["primo passo", "secondo passo", "terzo passo"]),
    ]
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("primo", "secondo", "terzo"),
        risposta=_risposta(
            "Devi eseguire il secondo passo, poi il primo passo e infine il terzo passo."
        ),
        riferimenti=riferimenti,
    )
    assert esito.label == "degradato"


def test_insufficienti_ha_priorita_su_errore_per_il_caso_zero_shot() -> None:
    """Zero-shot means the filter released nothing: it dominates provider errors.

    The CONCEZIONE §4 hierarchy lists ``insufficienti`` as the release
    observation, ``errore`` as the provider observation. When the
    scheduler falls back to zero-shot we want the release observation,
    not the provider result, because the prototype intentionally did not
    call the cloud with private content.
    """
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=0, modalita="zero_shot"),
        dp=_dp(),
        risposta=_risposta("Risposta basata sulla conoscenza generale."),
    )
    assert esito.label == "insufficienti"


def test_esito_e_serializzabile_in_json() -> None:
    import json

    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha"),
        risposta=_risposta("alpha è la risposta."),
    )
    # EsitoRisultato must be a dataclass convertible to dict and back via
    # the existing pipeline helpers.
    payload = json.dumps({"esito": esito.to_dict()}, ensure_ascii=False)
    assert "\"label\": \"completo\"" in payload


def test_riferimento_vuoto_non_alza_il_livello_di_rigor() -> None:
    """Without an explicit reference list, only the generic heuristic runs."""
    esito = classifica_risultato(
        decisione=SimpleNamespace(n_ensemble=5, modalita="ensemble"),
        dp=_dp("alpha"),
        risposta=_risposta("alpha è la risposta corretta."),
        riferimenti=[],
    )
    assert esito.label == "completo"
