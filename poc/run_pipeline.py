#!/usr/bin/env python3
"""Run the adaptive DP-KSA edge-to-cloud pipeline.

The executable flow is:

1. Load a local SQuAD-derived benchmark and sample candidate documents.
2. Ask :class:`core.scheduler.AdaptiveScheduler` for the effective ensemble
   size under the latency SLA.
3. Generate one local draft per selected document.
4. Run formal DP-KSA keyword extraction with RDP accounting.
5. Send only released keywords to the cloud adapter.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from core.cloud import CloudGenerator
from core.dataset import DatasetLoader
from core.engine import LocalNeuralEngine, ModelDownloadError
from core.privacy import DP_KSA_Filter
from core.scheduler import (
    AdaptiveScheduler,
    DecisioneScheduler,
    PrivacyBudgetExhaustedError,
)
from core.telemetry import LangfuseTracer

__all__ = ["build_parser", "main"]

load_dotenv()

CONSOLE = Console()
DEFAULT_ENSEMBLE_CANDIDATES = 40
DEFAULT_EPSILON = 1.0
DEFAULT_DELTA = 1e-4
DEFAULT_MAX_LATENCY_MS = 1500.0
DEFAULT_RTT_MS = 50.0
DEFAULT_CLOUD_LATENCY_MS = 150.0
DEFAULT_PREFILL_TOKENS_PER_SECOND = 250.0
DEFAULT_GENERATION_TOKENS_PER_SECOND = 50.0
DEFAULT_MAX_TOKENS = 30
DEFAULT_QUERY = None


def _positive_int(value: str) -> int:
    """Parse a strictly positive CLI integer."""

    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("il valore deve essere positivo")
    return parsed


def _non_negative_float(value: str) -> float:
    """Parse a finite non-negative CLI float."""

    parsed = float(value)
    if parsed < 0.0:
        raise argparse.ArgumentTypeError("il valore non può essere negativo")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the adaptive pipeline."""

    parser = argparse.ArgumentParser(
        description="Pipeline DP-KSA con scheduler adattivo e accounting RDP"
    )
    parser.add_argument(
        "--ensemble-size",
        type=_positive_int,
        default=DEFAULT_ENSEMBLE_CANDIDATES,
        help="Numero massimo di documenti candidati; N finale è deciso dallo scheduler",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=DEFAULT_EPSILON,
        help="Budget epsilon totale DP-KSA",
    )
    parser.add_argument(
        "--delta",
        type=float,
        default=DEFAULT_DELTA,
        help="Failure probability delta del test PTR",
    )
    parser.add_argument(
        "--max-latency-ms",
        type=_non_negative_float,
        default=DEFAULT_MAX_LATENCY_MS,
        help="SLA end-to-end percepito dall'utente in millisecondi",
    )
    parser.add_argument(
        "--rtt-ms",
        type=_non_negative_float,
        default=DEFAULT_RTT_MS,
        help="RTT stimato verso il provider cloud",
    )
    parser.add_argument(
        "--tempo-cloud-ms",
        type=_non_negative_float,
        default=DEFAULT_CLOUD_LATENCY_MS,
        help="Tempo stimato di inferenza cloud",
    )
    parser.add_argument(
        "--tok-per-sec-prefill",
        type=float,
        default=DEFAULT_PREFILL_TOKENS_PER_SECOND,
        help="Throughput locale prefill usato dallo scheduler",
    )
    parser.add_argument(
        "--tok-per-sec-generazione",
        type=float,
        default=DEFAULT_GENERATION_TOKENS_PER_SECOND,
        help="Throughput locale di generazione usato dallo scheduler",
    )
    parser.add_argument(
        "--max-tokens",
        type=_positive_int,
        default=DEFAULT_MAX_TOKENS,
        help="Massimo token generati per ogni bozza locale",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed opzionale per rendere riproducibile il campionamento",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=DEFAULT_QUERY,
        help="Query da usare; di default usa quella del primo documento campionato",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Chiave del provider OpenAI-compatible; senza endpoint o chiave viene usata la simulazione",
    )
    parser.add_argument(
        "--cloud-base-url",
        type=str,
        default=None,
        help="Endpoint OpenAI-compatible opzionale, altrimenti CLOUD_BASE_URL",
    )
    parser.add_argument(
        "--cloud-model",
        type=str,
        default=None,
        help="Identificativo modello cloud, altrimenti CLOUD_MODEL",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Percorso locale del modello GGUF; di default poc/models",
    )
    parser.add_argument(
        "--model-url",
        type=str,
        default=None,
        help="URL per scaricare il modello GGUF quando manca localmente",
    )
    parser.add_argument(
        "--langfuse-capture-sensitive",
        action="store_true",
        default=None,
        help="Abilita nei trace dati sensibili; usare solo con Langfuse fidato o locale",
    )
    return parser


def _stampa_decisione(decisione: DecisioneScheduler) -> None:
    """Render the scheduler decision without coupling the console to its class."""

    CONSOLE.print(
        Panel(
            "[bold]Decisione Scheduler Adattivo[/bold]\n"
            f"{decisione.motivazione}\n"
            f"N={decisione.n_ensemble} | sigma={decisione.sigma:.4f} | "
            f"PTR pass-rate attesa={decisione.ptr_pass_rate_attesa:.1%}",
            border_style="yellow",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the adaptive DP-KSA pipeline.

    Args:
        argv: Optional argument sequence. ``None`` reads the process command
            line, while a sequence makes the function easy to test.

    Returns:
        Process exit code, zero on success.
    """

    args = build_parser().parse_args(argv)
    CONSOLE.print(
        Panel.fit(
            "[bold cyan]Pipeline DP-KSA: Edge + Privacy + Cloud[/bold cyan]\n"
            "[dim]FindBestK + TopKWithPTR + Scheduler adattivo + RDP[/dim]",
            border_style="cyan",
        )
    )

    dataset = DatasetLoader()
    scheduler = AdaptiveScheduler(max_tokens=args.max_tokens)
    numero_candidati = min(
        max(args.ensemble_size, scheduler.n_min),
        scheduler.n_max,
        len(dataset.documenti),
    )
    documenti_candidati = dataset.ottieni_campione_ensemble(
        numero_candidati, seed=args.seed
    )
    domanda_target = args.query or documenti_candidati[0].domanda

    try:
        decisione = scheduler.schedule(
            [documento.token_stimati for documento in documenti_candidati],
            epsilon_budget=args.epsilon,
            delta=args.delta,
            latenza_rete_ms=args.rtt_ms,
            latenza_massima_ms=args.max_latency_ms,
            tempo_cloud_ms=args.tempo_cloud_ms,
            tok_per_sec_prefill=args.tok_per_sec_prefill,
            tok_per_sec_generazione=args.tok_per_sec_generazione,
        )
    except PrivacyBudgetExhaustedError as exc:
        CONSOLE.print(f"[red]Budget privacy non sufficiente: {exc}[/red]")
        return 2

    documenti_ensemble = documenti_candidati[: decisione.n_ensemble]
    argomento = documenti_ensemble[0].argomento
    _stampa_decisione(decisione)
    CONSOLE.print(f"[bold yellow]Argomento campione:[/bold yellow] {argomento}")
    CONSOLE.print(f"[bold yellow]Domanda:[/bold yellow] [italic]{domanda_target}[/italic]\n")

    document_table = Table(
        title=f"Documenti candidati selezionati (N={len(documenti_ensemble)})",
        show_header=True,
    )
    document_table.add_column("Doc ID", style="dim", width=14)
    document_table.add_column("Token stimati", justify="right")
    document_table.add_column("Estratto contesto locale")
    for documento in documenti_ensemble:
        preview = documento.contesto[:120].replace("\n", " ") + "..."
        document_table.add_row(
            documento.id,
            str(documento.token_stimati),
            preview,
        )
    CONSOLE.print(document_table)

    tracer = LangfuseTracer(capture_sensitive=args.langfuse_capture_sensitive)
    tracer.avvia_richiesta(
        domanda_target,
        metadata={
            "ensemble_size": decisione.n_ensemble,
            "epsilon": args.epsilon,
            "delta": args.delta,
            "rtt_ms": args.rtt_ms,
            "max_latency_ms": args.max_latency_ms,
        },
    )
    tracer.registra_decisione_scheduler(decisione)

    CONSOLE.print(
        Panel(
            "[bold]Fase 1: inferenza locale sull'ensemble[/bold]",
            border_style="blue",
        )
    )
    try:
        engine = LocalNeuralEngine(
            model_path=args.model_path,
            model_url=args.model_url,
        )
    except ModelDownloadError as exc:
        CONSOLE.print(f"[red]Impossibile predisporre il modello: {exc}[/red]")
        return 3

    bozze: list[str] = []
    tempi_totali: list[float] = []
    totale_tokens_generati = 0
    draft_table = Table(title="Bozze locali", show_header=True)
    draft_table.add_column("Doc ID", style="dim", width=14)
    draft_table.add_column("Input token", justify="right")
    draft_table.add_column("Output")
    draft_table.add_column("Prefill stimato (ms)", justify="right")
    draft_table.add_column("Totale (ms)", justify="right")
    draft_table.add_column("Velocità", justify="right")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=CONSOLE,
    ) as progress:
        task = progress.add_task(
            "Esecuzione inferenza locale...", total=len(documenti_ensemble)
        )
        for documento in documenti_ensemble:
            output = engine.genera_bozza(
                documento.contesto,
                domanda_target,
                max_tokens=args.max_tokens,
            )
            bozze.append(output.testo)
            tempi_totali.append(output.durata_totale_sec)
            totale_tokens_generati += output.completion_tokens
            draft_table.add_row(
                documento.id,
                str(output.prompt_tokens),
                f'[italic]"{output.testo}"[/italic]',
                f"{output.tempo_prefill_stimato_sec * 1000.0:.1f}",
                f"{output.durata_totale_sec * 1000.0:.1f}",
                f"{output.token_al_secondo:.1f} tok/s",
            )
            progress.advance(task)

    CONSOLE.print(draft_table)
    durata_locale_totale = sum(tempi_totali)
    velocita_media = (
        totale_tokens_generati / durata_locale_totale
        if durata_locale_totale > 0.0
        else 0.0
    )
    tracer.registra_fase_edge(
        len(documenti_ensemble),
        bozze,
        durata_locale_totale * 1000.0,
        velocita_media,
    )

    CONSOLE.print(
        Panel(
            "[bold]Fase 2: DP-KSA FindBestK + TopKWithPTR[/bold]",
            border_style="green",
        )
    )
    filtro_dp = DP_KSA_Filter(
        epsilon=args.epsilon,
        delta=args.delta,
        sigma=decisione.sigma,
        epsilon_find_best_k=decisione.epsilon_find_best_k,
        epsilon_top_k_ptr=decisione.epsilon_top_k_ptr,
    )
    esito_dp = filtro_dp.filtra(bozze)

    privacy_table = Table(show_header=True)
    privacy_table.add_column("Token", style="bold")
    privacy_table.add_column("Freq.", justify="right")
    privacy_table.add_column("Gap d_k", justify="right")
    privacy_table.add_column("Esito", justify="center")
    for indice, token in enumerate(esito_dp.token_ordinati[:8], start=1):
        gap = esito_dp.gap_per_k.get(indice, 0.0)
        released = token in esito_dp.parole_rilasciate
        result = "[bold green]RILASCIATO[/bold green]" if released else "[red]SCARTATO[/red]"
        privacy_table.add_row(
            token,
            str(esito_dp.conteggi_reali[token]),
            f"{gap:.1f}",
            result,
        )
    CONSOLE.print(privacy_table)
    CONSOLE.print(
        f"k_hat={esito_dp.k_hat}, gap PTR={esito_dp.gap_ptr}, "
        f"gap rumoroso={esito_dp.gap_ptr_rumoroso}, "
        f"passato={esito_dp.ptr_superato}"
    )
    CONSOLE.print(
        "[bold green]Keyword rilasciate:[/bold green] "
        f"{esito_dp.parole_rilasciate}\n"
        f"Epsilon consumato={esito_dp.budget_consumato_epsilon:.6f}; "
        f"epsilon rimasto={esito_dp.epsilon_rimasto:.6f}\n"
    )
    tracer.registra_fase_privacy(esito_dp)

    CONSOLE.print(
        Panel("[bold]Fase 3: generazione cloud[/bold]", border_style="magenta")
    )
    cloud = CloudGenerator(
        api_key=args.api_key,
        base_url=args.cloud_base_url,
        model=args.cloud_model,
    )
    risultato_cloud = cloud.genera(
        domanda_target,
        esito_dp.parole_rilasciate,
        [documento.contesto for documento in documenti_ensemble],
    )
    metrics_table = Table(show_header=True)
    metrics_table.add_column("Metrica", style="bold")
    metrics_table.add_column("Valore")
    metrics_table.add_row(
        "Traffico keyword",
        f"{risultato_cloud.byte_trasmessi_dp} byte "
        f"vs {risultato_cloud.byte_grezzi_rag} byte RAG grezzo "
        f"(-{risultato_cloud.risparmio_percentuale:.1f}%)",
    )
    metrics_table.add_row("Latenza locale", f"{durata_locale_totale * 1000.0:.1f} ms")
    metrics_table.add_row(
        "Latenza cloud",
        f"{risultato_cloud.latenza_rete_sec * 1000.0:.1f} ms",
    )
    metrics_table.add_row(
        "End-to-end misurato",
        f"{(durata_locale_totale + risultato_cloud.latenza_rete_sec) * 1000.0:.1f} ms",
    )
    CONSOLE.print(metrics_table)
    CONSOLE.print(
        Panel(
            f"[bold cyan]Risposta cloud:[/bold cyan]\n"
            f"{risultato_cloud.risposta_testuale}",
            border_style="green",
        )
    )
    trace_url = tracer.registra_fase_cloud(
        risultato_cloud.risposta_testuale,
        risultato_cloud.byte_trasmessi_dp,
        risultato_cloud.risparmio_percentuale,
        risultato_cloud.latenza_rete_sec,
        model=cloud.model,
    )
    if trace_url:
        CONSOLE.print(f"[green]Traccia Langfuse: {trace_url}[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
