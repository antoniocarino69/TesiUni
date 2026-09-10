#!/usr/bin/env python3
"""Interroga un corpus locale con DP-KSA in modalità interattiva.

Ogni domanda segue la stessa pipeline di ``run_pipeline.py``: retrieval locale,
ensemble di bozze, rilascio DP delle keyword e generazione cloud (reale o
simulata). A differenza della CLI singola, la sessione mantiene un unico
account privacy cumulativo per tutte le domande: il budget epsilon di sessione
è ``epsilon_per_domanda * max_domande`` e il budget delta cumulativo è
esplicitamente ``2 * delta * max_domande``. Quando l'account si esaurisce, le
domande successive ricevono il fallback zero-shot senza consultare i documenti
e senza alcun addebito, finché non si riavvia la sessione.
"""
from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from core.cloud import CloudGenerator
from core.documents import DocumentCorpus
from core.engine import LocalNeuralEngine, ModelDownloadError
from core.model_config import DEFAULT_LOCAL_MODEL_CONFIG
from core.pipeline import RequestConfig, run_request
from core.privacy import DP_KSA_Filter, DPBudgetExhaustedError
from core.scheduler import AdaptiveScheduler, PrivacyBudgetExhaustedError
from core.telemetry import LangfuseTracer

CONSOLE = Console()
DEFAULT_DOCUMENTS = Path('docs/ticket_demo/documenti')
DEFAULT_MAX_QUERIES = 10


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Il valore deve essere positivo')
    return number


def _non_negative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError('Il valore deve essere finito e non negativo')
    return number


class ReplSession:
    """Sessione interattiva con account privacy cumulativo condiviso.

    Il filtro DP viene costruito una sola volta con i parametri della singola
    domanda (sigma e quote epsilon del piano dello scheduler) ma con budget
    totali di sessione, così ogni domanda applica lo stesso meccanismo e la
    composizione RDP resta tracciata in un unico account.
    """

    def __init__(
        self,
        corpus: DocumentCorpus,
        config: RequestConfig,
        cloud: CloudGenerator,
        *,
        max_queries: int = DEFAULT_MAX_QUERIES,
        engine: Any = None,
        engine_options: dict[str, Any] | None = None,
        tracer: Any = None,
    ) -> None:
        decisione = AdaptiveScheduler(max_tokens=config.max_tokens).schedule(
            [config.prompt_token_budget] * config.candidates,
            config.epsilon, delta=config.delta,
            latenza_rete_ms=config.rtt_ms, latenza_massima_ms=config.sla_ms,
            tempo_cloud_ms=config.cloud_ms, tok_per_sec_prefill=config.prefill_tps,
            tok_per_sec_generazione=config.generation_tps, fixed_n=config.fixed_n,
        )
        delta_sessione = 2.0 * config.delta * max_queries
        if not 0.0 < delta_sessione < 0.5:
            raise ValueError('2 * delta * max_queries deve restare tra 0 e 0.5')
        self.filtro = DP_KSA_Filter(
            epsilon=config.epsilon * max_queries,
            delta=config.delta,
            sigma=decisione.sigma,
            epsilon_find_best_k=decisione.epsilon_find_best_k,
            epsilon_top_k_ptr=decisione.epsilon_top_k_ptr,
            delta_budget=delta_sessione,
            r_min_k=config.r_min_k,
            r_max_k=config.r_max_k,
        )
        self.corpus = corpus
        self.config = config
        self.cloud = cloud
        self.max_queries = max_queries
        self.engine = engine
        self.engine_options = engine_options
        self.tracer = tracer

    def _assicura_engine(self) -> None:
        if self.engine is None:
            CONSOLE.print('Caricamento del modello locale (primo utilizzo)...')
            self.engine = LocalNeuralEngine(**(self.engine_options or {}))

    def _esegui(self, query: str, config: RequestConfig, *, con_filtro: bool) -> dict[str, Any]:
        result = run_request(
            query, self.corpus, config, self.cloud,
            engine=self.engine, tracer=self.tracer,
            privacy_filter=self.filtro if con_filtro else None,
        )
        result['zero_shot_forzato'] = not con_filtro
        return result

    def rispondi(self, query: str) -> dict[str, Any]:
        """Esegue una domanda; a budget esaurito passa al fallback zero-shot."""
        if not query.strip():
            raise ValueError('La domanda non può essere vuota')
        decisione = AdaptiveScheduler(max_tokens=self.config.max_tokens).schedule(
            [self.config.prompt_token_budget] * self.config.candidates,
            self.config.epsilon, delta=self.config.delta,
            latenza_rete_ms=self.config.rtt_ms, latenza_massima_ms=self.config.sla_ms,
            tempo_cloud_ms=self.config.cloud_ms, tok_per_sec_prefill=self.config.prefill_tps,
            tok_per_sec_generazione=self.config.generation_tps, fixed_n=self.config.fixed_n,
        )
        if decisione.n_ensemble == 0:
            return self._esegui(query, self.config, con_filtro=True)
        self._assicura_engine()
        try:
            return self._esegui(query, self.config, con_filtro=True)
        except DPBudgetExhaustedError:
            config_zero = replace(self.config, sla_ms=0.0, fixed_n=None)
            return self._esegui(query, config_zero, con_filtro=False)

    def statistiche(self) -> dict[str, float]:
        """Stato pubblico dell'account privacy di sessione."""
        invocazioni = self.filtro.numero_invocazioni
        consumato_epsilon = self.filtro.account.epsilon_dp if invocazioni else 0.0
        consumato_delta = self.filtro.account.delta_total if invocazioni else 0.0
        return {
            'epsilon_sessione': self.filtro.epsilon,
            'epsilon_consumato': consumato_epsilon,
            'epsilon_rimasto': max(0.0, self.filtro.epsilon - consumato_epsilon),
            'delta_sessione': self.filtro.delta_budget,
            'delta_consumato': consumato_delta,
            'invocazioni': float(invocazioni),
            'max_domande': float(self.max_queries),
            'sigma': self.filtro.sigma,
        }

    def interpreta_comando(self, riga: str) -> tuple[str | None, bool]:
        """Interpreta un comando ``/...``; restituisce output e flag di uscita."""
        comando, _, _ = riga.partition(' ')
        comando = comando.lower()
        if comando in ('/exit', '/quit', '/q'):
            return 'Arrivederci.', True
        if comando == '/help':
            return (
                'Comandi: /help, /stats (budget privacy), /docs (corpus), '
                '/exit. Le altre righe sono domande per la pipeline.'
            ), False
        if comando == '/stats':
            stats = self.statistiche()
            return (
                f"Account di sessione: {stats['invocazioni']:.0f} invocazioni su "
                f"{stats['max_domande']:.0f} domande previste. "
                f"Epsilon consumato={stats['epsilon_consumato']:.6g} di "
                f"{stats['epsilon_sessione']:.6g} (rimasto {stats['epsilon_rimasto']:.6g}). "
                f"Delta consumato={stats['delta_consumato']:.6g} di "
                f"{stats['delta_sessione']:.6g}. Sigma PTR={stats['sigma']:.4f}."
            ), False
        if comando == '/docs':
            return f'Documenti nel corpus: {len(self.corpus.documents)}.', False
        return f'Comando sconosciuto: {comando}. Prova /help.', False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documents', type=Path, default=DEFAULT_DOCUMENTS,
                        help='File o directory locale TXT/MD/PDF testuali')
    parser.add_argument('--epsilon', type=float, default=1.0,
                        help='Budget epsilon per singola domanda (default 1.0)')
    parser.add_argument('--delta', type=float, default=1e-4,
                        help='Delta PTR; totale per domanda = 2*delta')
    parser.add_argument('--max-queries', type=_positive_int, default=DEFAULT_MAX_QUERIES,
                        help='Numero di domande coperte dall\'account di sessione')
    parser.add_argument('--ensemble-size', type=_positive_int, default=40,
                        help='Slot pubblici candidati (5..40)')
    parser.add_argument('--fixed-n', type=_positive_int,
                        help='Baseline sperimentale a N fisso')
    parser.add_argument('--r-min-k', type=_positive_int, default=1)
    parser.add_argument('--r-max-k', type=_positive_int, default=10)
    parser.add_argument('--max-latency-ms', type=_non_negative_float, default=60000.0,
                        help='SLA stimato della richiesta (default 60000 ms)')
    parser.add_argument('--rtt-ms', type=_non_negative_float, default=50.0)
    parser.add_argument('--tempo-cloud-ms', type=_non_negative_float, default=150.0)
    parser.add_argument('--tok-per-sec-prefill', type=float, default=250.0)
    parser.add_argument('--tok-per-sec-generazione', type=float, default=50.0)
    parser.add_argument('--prompt-token-budget', type=_positive_int, default=1000)
    parser.add_argument('--max-tokens', type=_positive_int,
                        default=DEFAULT_LOCAL_MODEL_CONFIG.max_tokens)
    parser.add_argument('--model-path')
    parser.add_argument('--model-url')
    parser.add_argument('--online', action='store_true',
                        help='Usa il provider cloud reale invece della simulazione offline')
    parser.add_argument('--telemetry', action='store_true',
                        help='Abilita i trace Langfuse (diagnostica sperimentale)')
    parser.add_argument('--langfuse-capture-sensitive', action='store_true', default=None)
    return parser


def _stampa_risultato(result: dict[str, Any]) -> None:
    CONSOLE.print(result['decision']['motivazione'], markup=False)
    if result.get('zero_shot_forzato'):
        CONSOLE.print('[yellow]Fallback zero-shot: budget di sessione esaurito, '
                      'documenti non consultati e nessun addebito.[/]')
    table = Table('Metrica', 'Valore')
    for label, value in [
        ('N pianificato / documenti effettivi',
         f"{result['decision']['n_ensemble']} / {result['local_diagnostics']['actual_documents']}"),
        ('Keyword rilasciate', ', '.join(result['released_keywords']) or '(nessuna)'),
        ('Epsilon / delta consumati',
         f"{result['epsilon_consumed']:.6g} / {result['delta_consumed']:.6g}"),
        ('Richiesta (esclusa ingestione)', f"{result['request_ms']:.1f} ms"),
        ('SLA richiesta superato', str(result['sla_violated'])),
        ('Cloud', 'SIMULATO' if result['cloud_simulated'] else 'provider reale'),
    ]:
        table.add_row(label, value)
    CONSOLE.print(table)
    CONSOLE.print(result['response'], markup=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 5 <= args.ensemble_size <= 40 or args.r_min_k > args.r_max_k:
        parser.error('Servono 5..40 slot e r_min_k <= r_max_k')
    if not 0.0 < 2.0 * args.delta * args.max_queries < 0.5:
        parser.error('2 * delta * max_queries deve restare tra 0 e 0.5')
    load_dotenv()
    try:
        corpus = DocumentCorpus.from_path(args.documents)
        config = RequestConfig(
            epsilon=args.epsilon, delta=args.delta, sla_ms=args.max_latency_ms,
            rtt_ms=args.rtt_ms, cloud_ms=args.tempo_cloud_ms,
            prefill_tps=args.tok_per_sec_prefill, generation_tps=args.tok_per_sec_generazione,
            prompt_token_budget=args.prompt_token_budget, max_tokens=args.max_tokens,
            candidates=args.ensemble_size, fixed_n=args.fixed_n,
            r_min_k=args.r_min_k, r_max_k=args.r_max_k,
        )
        cloud = CloudGenerator(offline=not args.online)
        tracer = LangfuseTracer(
            capture_sensitive=args.langfuse_capture_sensitive,
        ) if args.telemetry else None
        session = ReplSession(
            corpus, config, cloud,
            max_queries=args.max_queries,
            engine_options={'model_path': args.model_path, 'model_url': args.model_url},
            tracer=tracer,
        )
    except (ValueError, OSError) as exc:
        CONSOLE.print(f'Avvio non riuscito: {exc}', markup=False)
        return 3
    CONSOLE.print(
        f"Corpus: {args.documents} ({len(corpus.documents)} documenti). "
        f"Budget: epsilon={args.epsilon}/domanda, sessione per {args.max_queries} domande. "
        f"Cloud: {'provider reale' if not cloud.offline else 'simulato'}.",
    )
    CONSOLE.print('Scrivi una domanda oppure /help. /exit per uscire.')
    while True:
        try:
            riga = CONSOLE.input('[bold cyan]domanda> [/]')
        except (EOFError, KeyboardInterrupt):
            CONSOLE.print()
            break
        riga = riga.strip()
        if not riga:
            continue
        if riga.startswith('/'):
            output, esci = session.interpreta_comando(riga)
            CONSOLE.print(output, markup=False)
            if esci:
                break
            continue
        try:
            result = session.rispondi(riga)
        except PrivacyBudgetExhaustedError as exc:
            CONSOLE.print(f'Budget insufficiente per la domanda: {exc}', markup=False)
            continue
        except (ValueError, OSError, ModelDownloadError) as exc:
            CONSOLE.print(f'Domanda non completata: {exc}', markup=False)
            continue
        _stampa_risultato(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
