#!/usr/bin/env python3
"""
Pipeline DP-RAG Completa e Modulare con Dati Reali da Benchmark Accademico (SQuAD).
Architettura pulita orientata alle best practices di ingegneria del software:
- core.dataset: caricamento dataset accademico reale
- core.engine: inferenza neurale locale (Metal/CUDA) con telemetria token
- core.privacy: filtro di Privacy Differenziale PTR con rumore di Laplace
- core.cloud: generazione Cloud e calcolo risparmio di banda
- core.telemetry: tracciamento distribuito su Langfuse
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Carica credenziali da file .env se presente
load_dotenv()

from core.dataset import DatasetLoader
from core.engine import LocalNeuralEngine
from core.privacy import PrivacyFilterPTR
from core.cloud import CloudGenerator
from core.telemetry import LangfuseTracer

console = Console()

def main():
    parser = argparse.ArgumentParser(description="Pipeline DP-RAG con Benchmark Reale e Langfuse")
    parser.add_argument("--ensemble-size", type=int, default=5, help="Numero di documenti/bozze nell'ensemble locale")
    parser.add_argument("--epsilon", type=float, default=1.0, help="Budget di privacy differenziale")
    parser.add_argument("--tau", type=float, default=2.5, help="Soglia di rilascio PTR")
    parser.add_argument("--api-key", type=str, default=None, help="Chiave OpenAI (opzionale)")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]Pipeline Architetturale DP-RAG: Benchmark Reale & Osservabilità[/bold cyan]\n"
        "[dim]Esecuzione modulare: Dati SQuAD &bull; llama.cpp (Metal) &bull; DP-PTR &bull; Cloud &bull; Langfuse[/dim]",
        border_style="cyan"
    ))

    # 1. Caricamento Dataset Reale
    try:
        dataset = DatasetLoader()
        documenti_ensemble = dataset.ottieni_campione_ensemble(args.ensemble_size)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    domanda_target = documenti_ensemble[0].domanda
    argomento = documenti_ensemble[0].argomento
    
    console.print(f"[bold yellow]Argomento reale:[/bold yellow] [bold]{argomento}[/bold]")
    console.print(f"[bold yellow]Domanda di test:[/bold yellow] [italic]{domanda_target}[/italic]\n")

    # Tabella documenti reali
    t_docs = Table(title=f"Contesti Reali Ingestiti dal Database Locale (Ensemble N={len(documenti_ensemble)})", show_header=True)
    t_docs.add_column("Doc ID", style="dim", width=14)
    t_docs.add_column("Token Stimati", justify="right", width=14)
    t_docs.add_column("Estratto del Testo Reale")
    for doc in documenti_ensemble:
        anteprima = doc.contesto[:120].replace("\n", " ") + "..."
        t_docs.add_row(doc.id, str(doc.token_stimati), anteprima)
    console.print(t_docs)
    console.print()

    # 2. Inizializzazione Tracciamento
    tracer = LangfuseTracer()
    tracer.avvia_richiesta(domanda_target, metadata={
        "argomento": argomento,
        "ensemble_size": args.ensemble_size,
        "epsilon": args.epsilon,
        "tau": args.tau,
        "hardware": "Apple Silicon (Metal)"
    })

    # 3. Inferenza Locale Neurale
    console.print(Panel("[bold]Fase 1: Elaborazione Locale (Hardware M1 / Metal)[/bold]", border_style="blue"))
    try:
        engine = LocalNeuralEngine()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    bozze = []
    tempi_prefill = []
    tempi_totali = []
    totale_tokens_generati = 0

    t_bozze = Table(title="Bozze Generate dal Modello Compatto Locale", show_header=True)
    t_bozze.add_column("Doc ID", style="dim", width=14)
    t_bozze.add_column("Input Tok", justify="right")
    t_bozze.add_column("Output Neurale Estratto")
    t_bozze.add_column("Prefill (ms)", justify="right")
    t_bozze.add_column("Totale (ms)", justify="right")
    t_bozze.add_column("Velocità", justify="right")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Esecuzione inferenza neurale sull'hardware locale...", total=len(documenti_ensemble))
        for doc in documenti_ensemble:
            out = engine.genera_bozza(doc.contesto, domanda_target)
            bozze.append(out.testo)
            tempi_prefill.append(out.tempo_prefill_sec)
            tempi_totali.append(out.durata_totale_sec)
            totale_tokens_generati += out.completion_tokens

            t_bozze.add_row(
                doc.id,
                str(out.prompt_tokens),
                f"[italic]\"{out.testo}\"[/italic]",
                f"{out.tempo_prefill_sec * 1000:.1f}",
                f"{out.durata_totale_sec * 1000:.1f}",
                f"{out.token_al_secondo:.1f} tok/s"
            )
            progress.advance(task)

    console.print(t_bozze)
    durata_locale_totale = sum(tempi_totali)
    vel_media = totale_tokens_generati / durata_locale_totale if durata_locale_totale > 0 else 0
    tracer.registra_fase_edge(len(documenti_ensemble), bozze, durata_locale_totale * 1000, vel_media)
    console.print(f"[dim]Tempo totale computazione locale: {durata_locale_totale:.3f} s | Velocità media: {vel_media:.1f} tok/s[/dim]\n")

    # 4. Filtro di Privacy Differenziale
    console.print(Panel(
        f"[bold]Fase 2: Filtro DP-KSA Propose-Test-Release (Epsilon={args.epsilon}, Tau={args.tau})[/bold]",
        border_style="yellow"
    ))
    filtro_dp = PrivacyFilterPTR(epsilon=args.epsilon, soglia_tau=args.tau)
    esito_dp = filtro_dp.filtra(bozze)

    t_ptr = Table(show_header=True)
    t_ptr.add_column("Termine", style="bold")
    t_ptr.add_column("Freq. Reale", justify="right")
    t_ptr.add_column("Rumore Laplace", justify="right")
    t_ptr.add_column("Conteggio Rumoroso", justify="right")
    t_ptr.add_column("Esito Soglia", justify="center")

    tutti_termini = sorted(esito_dp.conteggi_reali.keys(), key=lambda x: esito_dp.conteggi_rumorosi[x], reverse=True)
    for t in tutti_termini[:8]:
        superato = t in esito_dp.parole_rilasciate
        colore = "[bold green]RILASCIATO[/bold green]" if superato else "[red]SCARTATO[/red]"
        t_ptr.add_row(
            t,
            str(esito_dp.conteggi_reali[t]),
            f"{esito_dp.rumore_applicato[t]:+.2f}",
            f"{esito_dp.conteggi_rumorosi[t]:.2f}",
            colore
        )
    console.print(t_ptr)
    console.print(f"[bold green]Parole chiave purificate autorizzate alla trasmissione:[/bold green] {esito_dp.parole_rilasciate}\n")
    tracer.registra_fase_privacy(args.epsilon, args.tau, esito_dp.conteggi_reali, esito_dp.parole_rilasciate, esito_dp.parole_scartate)

    # 5. Generazione Cloud
    console.print(Panel("[bold]Fase 3: Trasmissione di Rete e Inferenza Cloud[/bold]", border_style="magenta"))
    cloud = CloudGenerator(api_key=args.api_key)
    testi_grezzi = [d.contesto for d in documenti_ensemble]
    res_cloud = cloud.genera(domanda_target, esito_dp.parole_rilasciate, testi_grezzi)

    t_metrics = Table(show_header=True)
    t_metrics.add_column("Metrica di Sistema", style="bold")
    t_metrics.add_column("Valore Misurato")
    t_metrics.add_row("Traffico inviato in rete", f"{res_cloud.byte_trasmessi_dp} byte (vs {res_cloud.byte_grezzi_rag} byte RAG grezzo: [bold green]-{res_cloud.risparmio_percentuale:.1f}%[/bold green])")
    t_metrics.add_row("Latenza calcolo locale (M1)", f"{durata_locale_totale * 1000:.1f} ms")
    t_metrics.add_row("Latenza rete + Cloud", f"{res_cloud.latenza_rete_sec * 1000:.1f} ms")
    t_metrics.add_row("Tempo totale percepito (End-to-End)", f"{(durata_locale_totale + res_cloud.latenza_rete_sec) * 1000:.1f} ms")
    console.print(t_metrics)

    console.print(Panel(
        f"[bold cyan]Risposta Finale Ricevuta dal Cloud:[/bold cyan]\n{res_cloud.risposta_testuale}",
        border_style="green"
    ))

    # Chiusura Traccia Langfuse
    url_traccia = tracer.registra_fase_cloud(
        res_cloud.risposta_testuale,
        res_cloud.byte_trasmessi_dp,
        res_cloud.risparmio_percentuale,
        res_cloud.latenza_rete_sec
    )
    if url_traccia:
        console.print(Panel(
            f"[bold green]Traccia distribuita registrata su Langfuse:[/bold green]\n"
            f"[link={url_traccia}]{url_traccia}[/link]",
            border_style="cyan"
        ))

if __name__ == "__main__":
    main()
