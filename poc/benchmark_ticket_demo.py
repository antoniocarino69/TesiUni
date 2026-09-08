#!/usr/bin/env python3
"""Local IT-ticket experiment: procedure evidence versus case-specific details.

All inputs are verified public fictional fixtures. No provider or telemetry is
used. Seeded repetitions on cached drafts are local diagnostics, not a DP release
of their aggregate. Lexical metrics do not certify procedural correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

# These two helpers only validate a manifest and record model outputs; neither
# loads payroll data or starts an experiment when imported.
from benchmark_salary_demo import RecordingEngine, verify_corpus
from core.cloud import CloudGenerator
from core.engine import LocalNeuralEngine
from core.model_config import DEFAULT_LOCAL_MODEL_CONFIG, percorso_modello_predefinito
from core.pipeline import RequestConfig, run_request
from core.privacy import DP_KSA_Filter, costruisci_istogramma, normalizza_e_tokenizza

DEMO_ROOT = Path(__file__).resolve().parent / 'docs' / 'ticket_demo'


def sensitive_token_sets(manifest):
    """Support counts use tickets, not fields: repeated fields are not extra votes.

    Normalization splits domains and IPs. Fragment matches and no observed matches
    must never be interpreted as complete PII detection or client-level DP.
    """
    support = Counter()
    for record in manifest['documents']:
        tokens = set()
        for value in record['sensitive_fields'].values():
            tokens.update(normalizza_e_tokenizza(value))
        support.update(tokens)
    return set(support), {token for token, count in support.items() if count == 1}


def lexical_step_matches(tokens, step_groups):
    """Each step needs all clauses; each clause accepts any declared synonym."""
    observed = set(tokens)
    return {name: all(observed.intersection(aliases) for aliases in clauses)
            for name, clauses in step_groups.items()}


def measure_release(tokens, case, sensitive, unique):
    observed = set(tokens)
    steps = lexical_step_matches(observed, case['step_groups'])
    return {
        'step_matches': steps,
        'all_step_terms_present': all(steps.values()) if steps else None,
        'sensitive_fragments': sorted(observed & sensitive),
        'unique_identifier_tokens': sorted(observed & unique),
        'shared_identifier_present': 'clusterinternoaurora' in observed,
    }


def conditional_trials(drafts, case, sensitive, unique, *, trials=500, seed=2042,
                       epsilons=(1.0, 4.0, 8.0)):
    if trials < 1 or len(drafts) < 40:
        raise ValueError('Servono trials positivo e almeno 40 bozze')
    generator = np.random.default_rng(seed)
    rows = []
    for n in (5, 10, 20, 40):
        for epsilon in epsilons:
            released = complete = unique_events = shared_events = 0
            step_hits = Counter()
            fragment_hits = Counter()
            for _ in range(trials):
                outcome = DP_KSA_Filter(epsilon=epsilon, rng=generator).filtra(drafts[:n])
                metrics = measure_release(outcome.parole_rilasciate, case, sensitive, unique)
                released += bool(outcome.parole_rilasciate)
                complete += metrics['all_step_terms_present'] is True
                unique_events += bool(metrics['unique_identifier_tokens'])
                shared_events += metrics['shared_identifier_present']
                step_hits.update(name for name, hit in metrics['step_matches'].items() if hit)
                fragment_hits.update(metrics['sensitive_fragments'])
            rows.append({
                'n': n, 'epsilon': epsilon, 'delta_per_trial': 2e-4, 'trials': trials,
                'release_rate': released / trials,
                'all_step_terms_rate': complete / trials if case['step_groups'] else None,
                'step_term_rates': {name: step_hits[name] / trials for name in case['step_groups']},
                'unique_identifier_rate': unique_events / trials,
                'shared_identifier_rate': shared_events / trials,
                'sensitive_fragment_hits': dict(fragment_hits),
            })
    return rows


def synthesize_locally(engine, query, keywords):
    """Exercise the cloud's role locally; the model sees only query and DP words.

    This extra inference is reported separately from the offline CloudGenerator.
    With no evidence, abstain deterministically instead of inventing a procedure.
    """
    if not keywords:
        return {'text': 'Informazioni insufficienti: nessuna keyword rilasciata.',
                'inference_ms': 0.0, 'input_keywords': [], 'provider': 'no inference'}
    words = sorted(set(keywords))
    result = engine.genera_bozza('Keyword disponibili: ' + ', '.join(words), query)
    return {'text': result.testo, 'inference_ms': result.durata_totale_sec * 1000,
            'input_keywords': words, 'provider': 'real local model; keyword-only input'}


def run_demo(root, engine, *, trials=500):
    corpus, manifest = verify_corpus(root)
    cases = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
    sensitive, unique = sensitive_token_sets(manifest)
    by_path = {str(root / record['path']): record for record in manifest['documents']}
    observed = RecordingEngine(engine)
    cloud = CloudGenerator(api_key='unused-offline', base_url='http://unused.invalid',
                           model='offline-simulation', offline=True)
    # Same calibration for all four real requests, composed in one session.
    prototype = DP_KSA_Filter(epsilon=4.0)
    account = DP_KSA_Filter(epsilon=4.0 * len(cases), sigma=prototype.sigma,
                            epsilon_find_best_k=2.0, epsilon_top_k_ptr=2.0,
                            delta_budget=(len(cases) + 1) * 1e-4)
    results = []
    for index, case in enumerate(cases):
        print(f'Caso {case["id"]}: {case["query"]}', flush=True)
        observed.records.clear()
        selected = corpus.retrieve(case['query'], 40)
        pipeline = run_request(case['query'], corpus,
                               RequestConfig(epsilon=4.0, fixed_n=40, sla_ms=30_000),
                               cloud, engine=observed, privacy_filter=account)
        drafts = [record['testo'] for record in observed.records]
        release_metrics = measure_release(pipeline['released_keywords'], case, sensitive, unique)
        draft_metrics = [measure_release(normalizza_e_tokenizza(text), case, sensitive, unique)
                         for text in drafts]
        # Uses the actual release of this run, never cherry-picks a successful trial.
        synthesis = synthesize_locally(engine, case['query'], pipeline['released_keywords'])
        result = {
            'case': case, 'pipeline': pipeline, 'local_drafts': list(observed.records),
            'selected_files': [str(Path(doc.source).relative_to(root)) for doc in selected],
            'relevant_tickets': sum(by_path[doc.source]['error'] == case['error'] for doc in selected),
            'histogram': costruisci_istogramma(drafts), 'draft_metrics': draft_metrics,
            'release_metrics': release_metrics, 'local_keyword_synthesis': synthesis,
            'synthesis_metrics': measure_release(normalizza_e_tokenizza(synthesis['text']),
                                                 case, sensitive, unique),
            'conditional_trials': conditional_trials(drafts, case, sensitive, unique,
                                                       trials=trials, seed=2042 + index),
            'cloud_answer_quality': None,
        }
        results.append(result)
        print(f'  Keyword effettive: {pipeline["released_keywords"]}', flush=True)
        print(f'  Sintesi locale con sole keyword: {synthesis["text"]}', flush=True)
    customer_counts = Counter(record['customer_id'] for record in manifest['documents'])
    return {
        'synthetic_data': True, 'privacy_unit': 'ticket', 'client_level_guarantee': False,
        'real_local_inference': True, 'external_calls': False,
        'documents': len(corpus.documents), 'distinct_customers': len(customer_counts),
        'max_tickets_per_customer': max(customer_counts.values()),
        'corpus_manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
        'results': results, 'pipeline_session_epsilon': account.account.epsilon_dp,
        'pipeline_session_delta': account.account.delta_total,
        'limits': 'Conditional trials are seeded local diagnostics on public synthetic data. '
                  'Word coverage does not check order, negation, technical validity or PII completeness. '
                  'Keyword-only synthesis runs locally and is not a real cloud evaluation.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-path', type=Path, default=percorso_modello_predefinito())
    parser.add_argument('--trials', type=int, default=500)
    parser.add_argument('--output', type=Path, default=Path('reports/ticket_demo.json'))
    args = parser.parse_args()
    if not args.model_path.is_file() or args.trials < 1:
        parser.error('Servono modello locale già presente e trials positivo')
    started = time.perf_counter()
    print('Avvio esperimento ticket: modello locale reale, nessun servizio esterno.', flush=True)
    engine = LocalNeuralEngine(model_path=args.model_path)
    setup_seconds = time.perf_counter() - started
    report = run_demo(DEMO_ROOT, engine, trials=args.trials)
    with args.model_path.open('rb') as handle:
        fingerprint = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            fingerprint.update(chunk)
    report.update(model_sha256=fingerprint.hexdigest(), model_setup_seconds=setup_seconds,
                  model_config=asdict(DEFAULT_LOCAL_MODEL_CONFIG), platform=platform.platform(),
                  total_experiment_seconds=time.perf_counter() - started)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Report locale: {args.output}', flush=True)


if __name__ == '__main__':
    main()
