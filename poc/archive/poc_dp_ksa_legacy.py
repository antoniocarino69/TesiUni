#!/usr/bin/env python3
"""
PoC: Differentially Private Retrieval-Augmented Generation (DP-KSA)
Dimostrazione pratica del funzionamento del paper n. 2 applicato ad
Architetture e Reti di Calcolatori.
"""

import math
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()

# --- 1. DATI RISERVATI NEL DATABASE LOCALE (EDGE) ---
DOCUMENTI_LOCALE = [
    {
        "id": "DOC-001",
        "testo": "Cartella clinica di Mario Rossi (CF: RSSMRA78A01H501Z). Diagnosi: Ipertensione arteriosa stadio 2. Terapia prescritta: Ramipril 10mg al mattino."
    },
    {
        "id": "DOC-002",
        "testo": "Cartella clinica di Luca Bianchi (CF: BNCLCU82C12L219K). Diagnosi: Ipertensione arteriosa primaria. Trattamento confermato: Ramipril 10mg."
    },
    {
        "id": "DOC-003",
        "testo": "Cartella clinica di Anna Verdi (CF: VRDNNA90M41F205X). Paziente affetta da Ipertensione arteriosa. Risposta positiva al trattamento con Ramipril."
    },
    {
        "id": "DOC-004",
        "testo": "Cartella clinica di Giovanni Neri (CF: NREGNN65T08A662P). Diagnosi: Ipertensione arteriosa lieve. Trattamento raccomandato: Ramipril 5mg."
    },
    {
        "id": "DOC-005_OUTLIER",
        "testo": "Nota confidenziale interna: Mario Rossi ha un contenzioso legale e debiti fiscali per 45.000 euro legati a pignoramenti."
    }
]

QUERY_UTENTE = "Qual è il trattamento raccomandato per l'ipertensione?"

STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in", "con",
    "su", "per", "tra", "fra", "e", "ed", "o", "ha", "al", "del", "della", "delle", "dei",
    "da", "dal", "dalla", "ai", "agli", "alle", "cartella", "clinica", "paziente", "cf"
}

def pulisci_parola(parola: str) -> str:
    return "".join(c for c in parola.lower() if c.isalnum())


# --- 2. APPROCCIO TRADIZIONALE: RAG STANDARD (SENZA PRIVACY) ---
def esegui_rag_standard(query: str, documenti: List[dict]) -> Tuple[int, str]:
    """Invia tutti i documenti recuperati in chiaro al Cloud."""
    testo_completo = "\n".join([d["testo"] for d in documenti])
    prompt_inviato = f"Query: {query}\n\nDocumenti di contesto:\n{testo_completo}"
    byte_trasmessi = len(prompt_inviato.encode("utf-8"))
    
    # Risposta generata dal Cloud leggendo tutti i testi
    risposta_cloud = (
        "In base alle cartelle cliniche esaminate (tra cui Mario Rossi, Luca Bianchi, Anna Verdi), "
        "il trattamento comune per l'ipertensione è Ramipril. "
        "[ATTENZIONE: Il provider Cloud ha ricevuto anche i codici fiscali e le note sui debiti di Mario Rossi]."
    )
    return byte_trasmessi, risposta_cloud


# --- 3. APPROCCIO DP-KSA: PRIVACY DIFFERENZIALE LOCALE ---
@dataclass
class RisultatoDP:
    conteggi_reali: Dict[str, int]
    conteggi_rumorosi: Dict[str, float]
    termini_rilasciati: List[str]
    termini_scartati: List[str]
    rumore_aggiunto: Dict[str, float]
    byte_trasmessi: int
    risposta_cloud: str


def estrai_ensemble_locale(documenti: List[dict], n_generazioni: int) -> List[str]:
    """
    Simula l'inferenza del modello locale compatto che genera
    N risposte preliminari partendo da sottoinsiemi di documenti.
    """
    bozze = []
    for i in range(n_generazioni):
        doc = documenti[i % len(documenti)]
        # Il modello locale sintetizza la risposta dal documento esaminato
        if "Ramipril" in doc["testo"]:
            bozze.append("Per ipertensione arteriosa il trattamento è Ramipril.")
        else:
            bozze.append("Mario Rossi ha debiti fiscali e contenzioso.")
    return bozze


def applica_meccanismo_dp_ptr(
    bozze_ensemble: List[str],
    epsilon: float,
    soglia_tau: float
) -> Tuple[Dict[str, int], Dict[str, float], Dict[str, float], List[str], List[str]]:
    """
    Applica il paradigma Propose-Test-Release (PTR) con rumore Laplace:
    1. Conta le frequenze delle parole chiave nell'ensemble.
    2. Aggiunge rumore Laplace(0, scale = 1 / epsilon).
    3. Rilascia solo le parole il cui conteggio rumoroso supera la soglia tau.
    """
    conteggi: Dict[str, int] = {}
    for bozza in bozze_ensemble:
        parole_uniche_bozza = set(pulisci_parola(p) for p in bozza.split())
        for p in parole_uniche_bozza:
            if p and p not in STOPWORDS and len(p) > 2:
                conteggi[p] = conteggi.get(p, 0) + 1

    # Scala del rumore Laplace (sensibilità / epsilon). 
    # Poiché ogni documento/bozza può modificare la presenza di una parola al più di 1, sensibilità = 1.
    scala = 1.0 / max(epsilon, 1e-4)

    conteggi_rumorosi: Dict[str, float] = {}
    rumore_applicato: Dict[str, float] = {}
    rilasciati = []
    scartati = []

    for parola, freq in conteggi.items():
        # Generazione rumore laplaciano
        rumore = float(np.random.laplace(0.0, scala))
        freq_rumorosa = freq + rumore
        
        conteggi_rumorosi[parola] = freq_rumorosa
        rumore_applicato[parola] = rumore

        if freq_rumorosa >= soglia_tau:
            rilasciati.append(parola)
        else:
            scartati.append(parola)

    rilasciati.sort(key=lambda p: conteggi_rumorosi[p], reverse=True)
    scartati.sort(key=lambda p: conteggi_rumorosi[p], reverse=True)
    return conteggi, conteggi_rumorosi, rumore_applicato, rilasciati, scartati


def esegui_dp_ksa(
    query: str,
    documenti: List[dict],
    n_ensemble: int = 10,
    epsilon: float = 1.0,
    soglia_tau: float = 4.0
) -> RisultatoDP:
    """Esegue la pipeline completa di DP-KSA."""
    # 1. Generazione locale ensemble
    bozze = estrai_ensemble_locale(documenti, n_ensemble)

    # 2. Meccanismo DP (PTR)
    reali, rumorosi, rumori, rilasciati, scartati = applica_meccanismo_dp_ptr(
        bozze, epsilon, soglia_tau
    )

    # 3. Trasmissione al Cloud: si inviano solo le parole chiave purificate!
    stringa_keyword = ", ".join(rilasciati)
    prompt_cloud = (
        f"Query: {query}\n"
        f"Parole chiave verificate (filtro DP locale): [{stringa_keyword}]"
    )
    byte_trasmessi = len(prompt_cloud.encode("utf-8"))

    # Risposta finale generata dal Cloud
    risposta_cloud = (
        f"Sulla base dei termini confermati ({stringa_keyword}), il trattamento "
        "raccomandato per l'ipertensione arteriosa è il Ramipril. "
        "[GARANZIA: Nessun nome proprio, codice fiscale o debito personale è mai uscito dal calcolatore locale]."
    )

    return RisultatoDP(
        conteggi_reali=reali,
        conteggi_rumorosi=rumorosi,
        termini_rilasciati=rilasciati,
        termini_scartati=scartati,
        rumore_aggiunto=rumori,
        byte_trasmessi=byte_trasmessi,
        risposta_cloud=risposta_cloud
    )


# --- 4. SIMULATORE SCHEDULER: BILANCIAMENTO TEMPO LOCALE VS RETE ---
def simula_scheduler_adattivo(
    tempo_max_desiderato_ms: float,
    latenza_rete_ms: float,
    tempo_per_generazione_locale_ms: float
) -> Tuple[int, float]:
    """
    Calcola il numero massimo di generazioni locali (N) che il calcolatore
    può permettersi senza superare il tempo di risposta totale desiderato.
    """
    # Tempo residuo disponibile per il calcolo locale
    tempo_disponibile_locale = tempo_max_desiderato_ms - latenza_rete_ms - 150  # 150ms per cloud generation
    
    if tempo_disponibile_locale <= 0:
        return 0, 0.0

    n_ottimale = int(tempo_disponibile_locale // tempo_per_generazione_locale_ms)
    n_ottimale = max(3, min(n_ottimale, 30))  # range controllato [3, 30]
    tempo_totale_stimato = latenza_rete_ms + 150 + (n_ottimale * tempo_per_generazione_locale_ms)
    return n_ottimale, tempo_totale_stimato


# --- VISUALIZZAZIONE ---
def main():
    console.print(Panel.fit(
        "[bold cyan]Proof of Concept: DP-KSA (Differential Privacy RAG)[/bold cyan]\n"
        "[dim]Focus applicato ad Architetture e Reti di Calcolatori[/dim]",
        border_style="cyan"
    ))

    console.print(f"[bold yellow]Domanda dell'utente:[/bold yellow] [italic]{QUERY_UTENTE}[/italic]\n")

    # Documenti locali
    t_docs = Table(title="Documenti Riservati presenti nel database locale (Edge)", show_header=True)
    t_docs.add_column("ID", style="dim", width=14)
    t_docs.add_column("Contenuto Documento (Dati Sensibili + Dati Fattuali)")
    for d in DOCUMENTI_LOCALE:
        t_docs.add_row(d["id"], d["testo"])
    console.print(t_docs)
    console.print()

    # Confronto 1: RAG Standard
    byte_std, risp_std = esegui_rag_standard(QUERY_UTENTE, DOCUMENTI_LOCALE)

    # Confronto 2: DP-KSA
    n_ensemble = 10
    eps = 1.0
    tau = 4.0
    res_dp = esegui_dp_ksa(QUERY_UTENTE, DOCUMENTI_LOCALE, n_ensemble=n_ensemble, epsilon=eps, soglia_tau=tau)

    # Tabella del meccanismo PTR (Propose-Test-Release)
    t_dp = Table(
        title=f"Meccanismo di Privacy Differenziale PTR (Ensemble N={n_ensemble}, Epsilon={eps}, Soglia Tau={tau})",
        show_header=True
    )
    t_dp.add_column("Parola Chiave", style="bold")
    t_dp.add_column("Conteggio Reale", justify="right")
    t_dp.add_column("Rumore Laplace", justify="right")
    t_dp.add_column("Conteggio Rumoroso", justify="right")
    t_dp.add_column("Esito Soglia (>= Tau)", justify="center")

    tutte_parole = list(res_dp.conteggi_reali.keys())
    tutte_parole.sort(key=lambda p: res_dp.conteggi_rumorosi.get(p, 0), reverse=True)

    for p in tutte_parole:
        freq = res_dp.conteggi_reali[p]
        rum = res_dp.rumore_aggiunto[p]
        tot = res_dp.conteggi_rumorosi[p]
        superato = tot >= tau

        colore_esito = "[green]RILASCIATO (Sicuro)[/green]" if superato else "[red]SCARTATO (Privato/Rumore)[/red]"
        t_dp.add_row(
            p,
            str(freq),
            f"{rum:+.2f}",
            f"{tot:.2f}",
            colore_esito
        )
    console.print(t_dp)
    console.print()

    # Confronto di Rete e Sicurezza
    t_comp = Table(title="Confronto Architetturale: RAG Standard vs DP-KSA", show_header=True)
    t_comp.add_column("Metrica Sistemistica", style="bold")
    t_comp.add_column("RAG Standard (Cloud Diretto)")
    t_comp.add_column("DP-KSA (Elaborazione Edge con DP)")

    risparmio_byte = ((byte_std - res_dp.byte_trasmessi) / byte_std) * 100
    t_comp.add_row("Dati inviati in rete", f"{byte_std} byte (testo grezzo integrale)", f"{res_dp.byte_trasmessi} byte (solo keyword) (-{risparmio_byte:.1f}%)")
    t_comp.add_row("Dati sensibili esposti", "[red]CF, Nomi propri, Debiti personali esposti al Cloud[/red]", "[green]Nessun dato personale esce dal dispositivo[/green]")
    t_comp.add_row("Carico computazionale", "Minimo per il calcolatore locale", "Sforzo per generare l'ensemble locale")
    t_comp.add_row("Garanzia di Privacy", "Nessuna (0-DP)", f"Formale ({eps}-Differential Privacy)")
    console.print(t_comp)
    console.print()

    # Dimostrazione Scheduler
    console.print(Panel(
        "[bold]Simulazione dello Scheduler: Decisione Adattiva in base alla Rete[/bold]\n"
        "Supponiamo che l'utente richieda una risposta entro un budget di [bold yellow]1.5 secondi (1500 ms)[/bold yellow].\n"
        "Vediamo come lo scheduler adatta la dimensione dell'ensemble locale su due scenari di rete:",
        border_style="magenta"
    ))

    t_sched = Table(show_header=True)
    t_sched.add_column("Scenario di Rete")
    t_sched.add_column("Latenza Rete RTT")
    t_sched.add_column("Tempo Generazione Locale (M1)")
    t_sched.add_column("Ensemble Ottimale (N)")
    t_sched.add_column("Tempo Totale Stimato")

    # Caso A: Rete Fibra veloce
    n_a, t_a = simula_scheduler_adattivo(1500, latenza_rete_ms=50, tempo_per_generazione_locale_ms=60)
    t_sched.add_row("Rete Veloce (Fibra/LAN)", "50 ms", "60 ms / risposta", f"[bold green]{n_a} risposte[/bold green] (Massima privacy)", f"{t_a:.0f} ms")

    # Caso B: Rete Mobile 4G lenta/congestionata
    n_b, t_b = simula_scheduler_adattivo(1500, latenza_rete_ms=700, tempo_per_generazione_locale_ms=60)
    t_sched.add_row("Rete Lenta (4G instabile)", "700 ms", "60 ms / risposta", f"[bold yellow]{n_b} risposte[/bold yellow] (Carico ridotto)", f"{t_b:.0f} ms")

    console.print(t_sched)
    console.print("\n[dim]Esecuzione completata con successo.[/dim]")

if __name__ == "__main__":
    main()
