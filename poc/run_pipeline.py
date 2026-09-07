#!/usr/bin/env python3
"""Run local document retrieval, DP keyword release and optional cloud generation."""
from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from core.cloud import CloudGenerator
from core.dataset import DatasetLoader
from core.documents import DocumentCorpus
from core.engine import ModelDownloadError
from core.model_config import DEFAULT_LOCAL_MODEL_CONFIG
from core.pipeline import RequestConfig, run_request
from core.scheduler import AdaptiveScheduler, PrivacyBudgetExhaustedError
from core.telemetry import LangfuseTracer

CONSOLE = Console()
DEFAULT_QUERY = 'Who won Super Bowl 50?'


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--documents', type=Path, help='File o directory locale TXT/MD/PDF testuali')
    source.add_argument('--dataset', type=Path, help='JSON benchmark SQuAD normalizzato')
    parser.add_argument('--query', help='Query pubblica; obbligatoria con documenti reali')
    parser.add_argument('--ensemble-size', type=_positive_int, default=40,
                        help='Slot pubblici candidati (5..40), indipendenti dal corpus')
    parser.add_argument('--fixed-n', type=_positive_int, help='Baseline sperimentale a N fisso')
    parser.add_argument('--epsilon', type=float, default=1.0)
    parser.add_argument('--delta', type=float, default=1e-4, help='Delta PTR; totale default = 2*delta')
    parser.add_argument('--r-min-k', type=_positive_int, default=1)
    parser.add_argument('--r-max-k', type=_positive_int, default=10)
    parser.add_argument('--max-latency-ms', type=_non_negative_float, default=1500.0)
    parser.add_argument('--rtt-ms', type=_non_negative_float, default=50.0)
    parser.add_argument('--tempo-cloud-ms', type=_non_negative_float, default=150.0)
    parser.add_argument('--tok-per-sec-prefill', type=float, default=250.0)
    parser.add_argument('--tok-per-sec-generazione', type=float, default=50.0)
    parser.add_argument('--prompt-token-budget', type=_positive_int, default=1000,
                        help='Cap pubblico del prompt completo, incluso query/template')
    parser.add_argument('--max-tokens', type=_positive_int,
                        default=DEFAULT_LOCAL_MODEL_CONFIG.max_tokens)
    parser.add_argument('--seed', type=int, help='Compatibilità: retrieval deterministico, seed non usato')
    for option in ['api-key', 'cloud-base-url', 'cloud-model', 'model-path', 'model-url']:
        parser.add_argument('--' + option)
    parser.add_argument('--offline-cloud', action='store_true',
                        help='Forza simulazione cloud anche se esistono credenziali')
    parser.add_argument('--no-telemetry', action='store_true')
    parser.add_argument('--langfuse-capture-sensitive', action='store_true', default=None,
                        help='Diagnostica sperimentale completa su un endpoint fidato')
    parser.add_argument('--dry-run', action='store_true',
                        help='Verifica corpus, retrieval e piano senza modello/provider/telemetria')
    parser.add_argument('--output', type=Path, help='Report JSON locale; contiene diagnostica non DP')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.documents and not args.query:
        parser.error('--query è obbligatoria con --documents')
    load_dotenv()
    started = time.perf_counter()
    try:
        corpus = (DocumentCorpus.from_path(args.documents) if args.documents
                  else DatasetLoader(args.dataset).as_corpus())
        query = args.query or DEFAULT_QUERY
        config = RequestConfig(
            epsilon=args.epsilon, delta=args.delta, sla_ms=args.max_latency_ms,
            rtt_ms=args.rtt_ms, cloud_ms=args.tempo_cloud_ms,
            prefill_tps=args.tok_per_sec_prefill, generation_tps=args.tok_per_sec_generazione,
            prompt_token_budget=args.prompt_token_budget, max_tokens=args.max_tokens,
            candidates=args.ensemble_size, fixed_n=args.fixed_n,
            r_min_k=args.r_min_k, r_max_k=args.r_max_k,
        )
        if not 5 <= config.candidates <= 40 or config.r_min_k > config.r_max_k:
            raise ValueError('Servono 5..40 slot e r_min_k <= r_max_k')
        if args.dry_run:
            decision = AdaptiveScheduler(max_tokens=config.max_tokens).schedule(
                [config.prompt_token_budget] * config.candidates, config.epsilon,
                delta=config.delta, latenza_massima_ms=config.sla_ms,
                latenza_rete_ms=config.rtt_ms, tempo_cloud_ms=config.cloud_ms,
                tok_per_sec_prefill=config.prefill_tps,
                tok_per_sec_generazione=config.generation_tps, fixed_n=config.fixed_n,
            )
            preview = corpus.retrieve(query, config.candidates)
            CONSOLE.print(f'Documenti unici: {len(corpus.documents)}; '
                          f'slot vuoti: {sum(doc.is_padding for doc in preview)}')
            CONSOLE.print(decision.motivazione)
            return 0
        cloud = CloudGenerator(api_key=args.api_key, base_url=args.cloud_base_url,
                               model=args.cloud_model, offline=args.offline_cloud)
        tracer = None if args.no_telemetry else LangfuseTracer(
            capture_sensitive=args.langfuse_capture_sensitive,
        )
        result = run_request(query, corpus, config, cloud, tracer=tracer,
                             engine_options={'model_path': args.model_path,
                                             'model_url': args.model_url})
        result['cli_total_ms'] = (time.perf_counter() - started) * 1000
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    except PrivacyBudgetExhaustedError as exc:
        CONSOLE.print(f'Budget insufficiente: {exc}', markup=False)
        return 2
    except (ValueError, OSError, ModelDownloadError) as exc:
        CONSOLE.print(f'Richiesta non completata: {exc}', markup=False)
        return 3
    CONSOLE.print(result['decision']['motivazione'], markup=False)
    table = Table('Metrica', 'Valore')
    for label, value in [
        ('N pianificato / documenti effettivi',
         f"{result['decision']['n_ensemble']} / {result['local_diagnostics']['actual_documents']}"),
        ('Keyword rilasciate', ', '.join(result['released_keywords'])),
        ('Epsilon / delta consumati', f"{result['epsilon_consumed']:.6g} / {result['delta_consumed']:.6g}"),
        ('Richiesta misurata incl. setup modello, escl. ingestione/flush', f"{result['request_ms']:.1f} ms"),
        ('Totale CLI incl. ingestione e flush', f"{result['cli_total_ms']:.1f} ms"),
        ('SLA richiesta superato', str(result['sla_violated'])),
        ('Prefill stimato (non TTFT)', f"{result['prefill_estimated_ms']:.1f} ms"),
        ('Volume testo prompt / estratti (non traffico di rete)',
         f"{result['prompt_text_bytes']} / {result['context_text_bytes']} byte"),
        ('Cloud', 'SIMULATO: nessuna misura provider' if result['cloud_simulated'] else 'provider reale'),
    ]:
        table.add_row(label, value)
    CONSOLE.print(table)
    CONSOLE.print(result['response'], markup=False)
    return 4 if result['provider_error'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
