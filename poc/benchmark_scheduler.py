#!/usr/bin/env python3
"""Local experiment: adaptive versus fixed ensembles with one cumulative DP account.

The report contains non-private experimental diagnostics. Do not publish it as
DP output. Real cloud responses compose in the shared session account; offline
cloud simulation never produces a quality score.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from core.cloud import CloudGenerator
from core.documents import DocumentCorpus
from core.engine import LocalNeuralEngine
from core.pipeline import RequestConfig, run_request
from core.privacy import DP_KSA_Filter, DPBudgetExhaustedError, deriva_sigma_da_budget


def answer_scores(answer: str, references: list[str]) -> dict[str, float]:
    """Best normalized exact match and token F1 across accepted references."""
    def tokens(text: str) -> list[str]:
        return re.findall(r'\w+', text.casefold())
    predicted = tokens(answer)
    scores = []
    for reference in references:
        expected = tokens(reference)
        overlap = sum((Counter(predicted) & Counter(expected)).values())
        f1 = 2 * overlap / (len(predicted) + len(expected)) if predicted or expected else 1.0
        scores.append((float(predicted == expected), f1))
    return {'exact_match': max(s[0] for s in scores), 'token_f1': max(s[1] for s in scores)}


def run_experiment(cases, corpus, config, cloud, engine, *, fixed_sizes=(5, 10, 20, 40),
                   repeats=3, order_seed=42, session_epsilon=10.0):
    """Reuse the same corpus, prompt cap, mechanism and preloaded model.

    The seed randomizes execution order only; DP randomness is not seeded or
    exposed. Independent reruns estimate variability, not bitwise reproducibility.
    """
    if not cases or repeats < 1 or any(
        not isinstance(case.get('query'), str) or not case['query'].strip()
        or not isinstance(case.get('references'), list) or not case['references']
        or any(not isinstance(ref, str) for ref in case['references'])
        for case in cases
    ):
        raise ValueError('Servono casi con query, references non vuote e repeats positivo')
    variants = [None, *fixed_sizes]
    if any(not 5 <= n <= config.candidates for n in fixed_sizes):
        raise ValueError('Le baseline fisse devono essere tra 5 e candidates')
    jobs = [(i, variant, repeat) for i in range(len(cases))
            for variant in variants for repeat in range(repeats)]
    random.Random(order_seed).shuffle(jobs)
    sigma = deriva_sigma_da_budget(config.epsilon, config.epsilon / 2,
                                   config.epsilon / 2, config.delta)
    account = DP_KSA_Filter(
        epsilon=session_epsilon, delta=config.delta,
        delta_budget=(len(jobs) + 1) * config.delta,
        epsilon_find_best_k=config.epsilon / 2, epsilon_top_k_ptr=config.epsilon / 2,
        sigma=sigma, r_min_k=config.r_min_k, r_max_k=config.r_max_k,
    )
    rows = []
    stopped = None
    for case_index, fixed_n, repeat in jobs:
        case = cases[case_index]
        try:
            result = run_request(case['query'], corpus, replace(config, fixed_n=fixed_n),
                                 cloud, engine=engine, privacy_filter=account)
        except DPBudgetExhaustedError as exc:
            stopped = str(exc)
            break
        result.update(case_index=case_index, repeat=repeat,
                      variant='adaptive' if fixed_n is None else f'fixed_{fixed_n}')
        result['quality'] = (None if result['cloud_simulated'] or result['provider_error']
                             else answer_scores(result['response'], case['references']))
        rows.append(result)
    summary = {}
    for variant in ['adaptive', *(f'fixed_{n}' for n in fixed_sizes)]:
        group = [row for row in rows if row['variant'] == variant]
        if not group:
            continue
        times = sorted(row['request_ms'] for row in group)
        scores = [row['quality']['token_f1'] for row in group if row['quality'] is not None]
        summary[variant] = {
            'cloud_simulated': all(row['cloud_simulated'] for row in group),
            'runs': len(group), 'request_ms_mean': sum(times) / len(times),
            'request_ms_min': times[0], 'request_ms_max': times[-1],
            'ptr_release_rate': sum(bool(row['released_keywords']) for row in group) / len(group),
            'sla_violation_rate': sum(row['sla_violated'] for row in group) / len(group),
            'provider_errors': sum(row['provider_error'] is not None for row in group),
            'token_f1_mean': sum(scores) / len(scores) if scores else None,
        }
    return {'summary': summary, 'runs': rows, 'stopped_budget': stopped,
            'planned_runs': len(jobs), 'order_seed': order_seed,
            'session_epsilon_limit': session_epsilon,
            'cumulative_epsilon': account.account.epsilon_dp if account.numero_invocazioni else 0,
            'cumulative_delta': account.account.delta_total if account.numero_invocazioni else 0,
            'measurement': 'warm preloaded model; corpus ingestion excluded; local report is NOT DP'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documents', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True,
                        help='JSON: [{"query": "...", "references": ["..."]}]')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixed-sizes', nargs='+', type=int, default=[5, 10, 20, 40])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--order-seed', type=int, default=42)
    parser.add_argument('--epsilon', type=float, default=1.0, help='Calibrazione per richiesta')
    parser.add_argument('--session-epsilon', type=float, default=10.0, help='Limite cumulativo sessione')
    parser.add_argument('--max-latency-ms', type=float, default=30_000)
    parser.add_argument('--prompt-token-budget', type=int, default=1000)
    parser.add_argument('--offline-cloud', action='store_true')
    parser.add_argument('--model-path')
    parser.add_argument('--model-url')
    args = parser.parse_args()
    load_dotenv()
    corpus = DocumentCorpus.from_path(args.documents)
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    engine = LocalNeuralEngine(model_path=args.model_path, model_url=args.model_url)
    report = run_experiment(cases, corpus, RequestConfig(
        epsilon=args.epsilon, sla_ms=args.max_latency_ms,
        prompt_token_budget=args.prompt_token_budget,
    ), CloudGenerator(offline=args.offline_cloud), engine,
        fixed_sizes=args.fixed_sizes, repeats=args.repeats, order_seed=args.order_seed,
        session_epsilon=args.session_epsilon)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    return 2 if report['stopped_budget'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
