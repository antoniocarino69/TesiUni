#!/usr/bin/env python3
"""Run the fictional payroll corpus with a real local model and no external services.

DP trials reuse cached real drafts: they measure conditional release frequency,
not repeated inference latency or end-to-end quality. Seeded trials are local
diagnostics on PUBLIC synthetic data, not privacy-protected releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from core.cloud import CloudGenerator
from core.documents import DocumentCorpus
from core.engine import LocalNeuralEngine
from core.model_config import DEFAULT_LOCAL_MODEL_CONFIG, percorso_modello_predefinito
from core.pipeline import RequestConfig, run_request
from core.privacy import DP_KSA_Filter, costruisci_istogramma, deriva_sigma_da_budget

DEMO_ROOT = Path(__file__).resolve().parent / 'docs' / 'azienda_demo'


class RecordingEngine:
    """Record actual local drafts for the public synthetic experiment only."""

    def __init__(self, engine):
        self.engine = engine
        self.records = []

    def limita_contesto(self, *args):
        return self.engine.limita_contesto(*args)

    def genera_bozza(self, context, query, max_tokens):
        result = self.engine.genera_bozza(context, query, max_tokens=max_tokens)
        self.records.append(asdict(result))
        if len(self.records) % 10 == 0:
            print(f'  {len(self.records)}/40 inferenze locali completate', flush=True)
        return result


def contains_reference(text: str, references: list[str]) -> bool:
    """Literal normalized reference coverage; this is not semantic correctness."""
    tokens = re.findall(r'\w+', text.casefold())
    for reference in references:
        expected = re.findall(r'\w+', reference.casefold())
        if expected and any(tokens[i:i + len(expected)] == expected
                            for i in range(len(tokens) - len(expected) + 1)):
            return True
    return False


def release_trials(drafts, target_token, *, trials=500, epsilons=(1.0, 4.0, 8.0), seed=83):
    """Independent diagnostic replications; never a cumulative DP session."""
    if trials < 1 or len(drafts) < 40:
        raise ValueError('Servono almeno 40 bozze e trials positivo')
    rows = []
    generator = np.random.default_rng(seed)
    for n in (5, 10, 20, 40):
        histogram = costruisci_istogramma(drafts[:n])
        for epsilon in epsilons:
            released = 0
            recovered = 0
            sigma = deriva_sigma_da_budget(epsilon, epsilon / 2, epsilon / 2)
            for _ in range(trials):
                outcome = DP_KSA_Filter(epsilon=epsilon, sigma=sigma, rng=generator).filtra(drafts[:n])
                released += bool(outcome.parole_rilasciate)
                recovered += target_token is not None and target_token in outcome.parole_rilasciate
            rows.append({
                'n': n, 'epsilon_per_trial': epsilon, 'delta_per_trial': 2e-4,
                'sigma': sigma, 'trials': trials, 'release_rate': released / trials,
                'target_recovery_rate': recovered / trials if target_token is not None else None,
                'target_count_in_histogram': histogram.get(target_token, 0),
                'scope': 'local conditional trials on cached public synthetic drafts',
            })
    return rows


def verify_corpus(root: Path) -> tuple[DocumentCorpus, dict]:
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('synthetic') is not True:
        raise ValueError('Questo runner è riservato al corpus pubblico fittizio')
    expected = {root / item['path'] for item in manifest['documents']}
    actual = {path for path in (root / 'documenti').rglob('*') if path.is_file()}
    if actual != expected:
        raise ValueError('La directory documenti contiene file mancanti o aggiunti al corpus demo')
    for item in manifest['documents']:
        if hashlib.sha256((root / item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'Corpus demo modificato: {item["path"]}')
    corpus = DocumentCorpus.from_path(root / 'documenti')
    return corpus, manifest


def run_demo(root, engine, *, trials=500):
    corpus, manifest = verify_corpus(root)
    cases = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
    by_path = {str(root / row['path']): row for row in manifest['documents']}
    cloud = CloudGenerator(api_key='unused-offline', base_url='http://unused.invalid',
                           model='offline-simulation', offline=True)
    observed = RecordingEngine(engine)
    config = RequestConfig(epsilon=4.0, fixed_n=40, sla_ms=30_000)
    sigma = deriva_sigma_da_budget(4.0, 2.0, 2.0)
    account = DP_KSA_Filter(epsilon=4.0 * len(cases), epsilon_find_best_k=2.0,
                            epsilon_top_k_ptr=2.0, sigma=sigma,
                            delta_budget=(len(cases) + 1) * config.delta)
    results = []
    for case_index, case in enumerate(cases):
        print(f'Caso {case["id"]}: {case["query"]}', flush=True)
        observed.records.clear()
        selected = corpus.retrieve(case['query'], 40)
        pipeline = run_request(case['query'], corpus, config, cloud,
                               engine=observed, privacy_filter=account)
        drafts = [record['testo'] for record in observed.records]
        reference_coverage = sum(contains_reference(text, case['references']) for text in drafts)
        relevant = sum(by_path[doc.source]['department'] == case['department'] for doc in selected)
        rows = release_trials(drafts, case['target_token'], trials=trials, seed=83 + case_index)
        results.append({
            'case': case, 'pipeline': pipeline, 'local_drafts': list(observed.records),
            'selected_files': [str(Path(doc.source).relative_to(root)) for doc in selected],
            'relevant_department_in_top40': relevant if case['department'] else None,
            'drafts_containing_reference': reference_coverage,
            'histogram': costruisci_istogramma(drafts), 'conditional_dp_trials': rows,
            'cloud_answer_quality': None,
        })
        print(f'  {reference_coverage}/40 bozze contengono una risposta attesa; '
              f'tempo richiesta {pipeline["request_ms"] / 1000:.2f} s; '
              f'keyword nella singola richiesta: {pipeline["released_keywords"]}', flush=True)
    fallback = run_request(cases[0]['query'], corpus, RequestConfig(), cloud, engine=observed)
    return {
        'synthetic_data': True, 'real_local_inference': True, 'external_calls': False,
        'corpus_documents': len(corpus.documents),
        'corpus_manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
        'results': results, 'fallback': fallback,
        'pipeline_session_epsilon': account.account.epsilon_dp,
        'pipeline_session_delta': account.account.delta_total,
        'interpretation': (
            'Local real inference once per document/query; cloud simulated. '
            'DP trials reuse those drafts with seeded noise on public synthetic data. '
            'They are not repeated timing measurements or an aggregate DP guarantee. '
            'Reference coverage is literal, not a semantic quality score.'
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['filter', 'scheduler'], default='filter')
    parser.add_argument('--trials', type=int, default=500)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--model-path', type=Path, default=percorso_modello_predefinito())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.trials < 1 or args.repeats < 1 or not args.model_path.is_file():
        parser.error('Servono trials/repeats positivi e modello GGUF già presente localmente')
    output = args.output or Path(f'reports/azienda_demo_{args.mode}.json')
    started = time.perf_counter()
    print('Caricamento del modello locale; nessun provider o Langfuse verrà contattato.', flush=True)
    engine = LocalNeuralEngine(model_path=args.model_path)
    setup_seconds = time.perf_counter() - started
    if args.mode == 'filter':
        report = run_demo(DEMO_ROOT, engine, trials=args.trials)
    else:
        from benchmark_scheduler import run_experiment
        corpus, _ = verify_corpus(DEMO_ROOT)
        case = json.loads((DEMO_ROOT / 'cases.json').read_text(encoding='utf-8'))[0]
        print(f'Confronto Tecnologia: adattivo e N=5/20/40, {args.repeats} ripetizioni.', flush=True)
        report = run_experiment(
            [case], corpus, RequestConfig(epsilon=4.0, sla_ms=30_000),
            CloudGenerator(api_key='unused-offline', base_url='http://unused.invalid',
                           model='offline-simulation', offline=True),
            engine, fixed_sizes=[5, 20, 40], repeats=args.repeats,
            session_epsilon=4.0 * 4 * args.repeats,
        )
        report.update(synthetic_data=True, real_local_inference=True, external_calls=False,
                      case=case, corpus_documents=len(corpus.documents))
        print(json.dumps(report['summary'], ensure_ascii=False, indent=2), flush=True)
    report.update(model_setup_seconds=setup_seconds, model_path=str(args.model_path),
                  model_config=asdict(DEFAULT_LOCAL_MODEL_CONFIG), platform=platform.platform(),
                  total_experiment_seconds=time.perf_counter() - started)
    with args.model_path.open('rb') as handle:
        fingerprint = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            fingerprint.update(chunk)
    report['model_sha256'] = fingerprint.hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Report locale: {output}', flush=True)


if __name__ == '__main__':
    main()
