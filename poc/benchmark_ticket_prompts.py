"""Paired local prompt/model screening on verified synthetic tickets; no DP release.

This diagnostic does not replace the pipeline or evaluate SLA/accounting. All
arms use identical inputs, greedy decoding and a fixed seed. No cloud or dotenv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path

from benchmark_salary_demo import verify_corpus
from benchmark_ticket_demo import DEMO_ROOT, lexical_step_matches
from core.engine import LocalNeuralEngine
from core.model_config import (
    DEFAULT_LOCAL_MODEL_CONFIG,
    KEYWORD_SYNTHESIS_PROMPT,
    TICKET_EXTRACTION_PROMPT,
    costruisci_prompt,
)
from core.privacy import normalizza_e_tokenizza


def profiles(system_prompt):
    base = replace(DEFAULT_LOCAL_MODEL_CONFIG, temperature=0.0)
    return {
        'original_30': base,
        'original_96': replace(base, max_tokens=96),
        'specialized_96': replace(base, max_tokens=96, system_prompt=system_prompt),
    }


def infer(llm, context, query, config):
    started = time.perf_counter()
    result = llm(costruisci_prompt(context, query, config), max_tokens=config.max_tokens,
                 temperature=config.temperature, seed=42, stop=list(config.stop))
    return {'text': result['choices'][0]['text'].strip(),
            'seconds': time.perf_counter() - started,
            'finish_reason': result['choices'][0].get('finish_reason'),
            'usage': result['usage']}


def evaluate(model_path, sample):
    corpus, _ = verify_corpus(DEMO_ROOT)
    cases = json.loads((DEMO_ROOT / 'cases.json').read_text())
    engine = LocalNeuralEngine(model_path=model_path)
    rows = []
    for name, config in profiles(TICKET_EXTRACTION_PROMPT).items():
        config = replace(config, filename=model_path.name, url='')
        for case in (cases[0], cases[3]):
            outputs = []
            for doc in corpus.retrieve(case['query'], sample):
                result = infer(engine.llm, doc.context, case['query'], config)
                terms = normalizza_e_tokenizza(result['text'])
                result.update(source=Path(doc.source).name,
                              all_step_terms=all(lexical_step_matches(
                                  terms, case['step_groups']).values())
                              if case['step_groups'] else None,
                              exact_abstention=result['text'].strip(' .!\n').casefold()
                              == 'non disponibile')
                outputs.append(result)
            rows.append({'profile': name, 'case': case['id'], 'config': asdict(config),
                         'query': case['query'],
                         'outputs': outputs,
                         'complete_terms': sum(x['all_step_terms'] is True for x in outputs),
                         'abstentions': sum(x['exact_abstention'] for x in outputs),
                         'median_seconds': statistics.median(x['seconds'] for x in outputs)})
            print(model_path.name, name, case['id'], rows[-1]['complete_terms'],
                  rows[-1]['abstentions'], flush=True)
    # Fixed outputs from the previous actual DP run; no oracle procedure is supplied.
    previous = json.loads((DEMO_ROOT / 'risultati.json').read_text())
    synthesis = []
    for name, config in profiles(KEYWORD_SYNTHESIS_PROMPT).items():
        config = replace(config, filename=model_path.name, url='')
        for case in previous['results']:
            words = sorted(set(case['released_keywords']))
            if not words:
                continue  # production benchmark abstains without invoking a model
            result = infer(engine.llm, 'Keyword disponibili: ' + ', '.join(words),
                           case['case']['query'], config)
            synthesis.append({'profile': name, 'case': case['case']['id'],
                              'input_keywords': words, 'config': asdict(config), **result})
    with model_path.open('rb') as handle:
        fingerprint = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            fingerprint.update(chunk)
        digest = fingerprint.hexdigest()
    engine.llm.close()
    return {'model_file': model_path.name, 'sha256': digest, 'sample_per_case': sample,
            'platform': platform.platform(), 'llama_cpp_version': version('llama-cpp-python'),
            'corpus_manifest_sha256': hashlib.sha256(
                (DEMO_ROOT / 'manifest.json').read_bytes()).hexdigest(),
            'decoding': 'greedy; seed=42; same inputs in all arms',
            'extraction': rows, 'synthesis': synthesis,
            'limits': 'Synthetic screening, no DP or SLA evaluation. Lexical coverage does '
                      'not establish order/correctness. Synthesis uses previous 0.5B releases.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-path', type=Path, required=True)
    parser.add_argument('--sample', type=int, default=12)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.model_path.is_file() or not 1 <= args.sample <= 40:
        parser.error('Serve un modello presente e sample compreso tra 1 e 40')
    report = evaluate(args.model_path, args.sample)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
