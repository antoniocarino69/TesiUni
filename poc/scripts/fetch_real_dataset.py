#!/usr/bin/env python3
"""Build a benchmark of distinct original paragraphs from public SQuAD 1.1."""
from __future__ import annotations

import json
from pathlib import Path

import requests

DEST_FILE = Path(__file__).resolve().parents[1] / 'data' / 'squad_real_benchmark.json'
DEFAULT_SAMPLE_LIMIT = 100
SQUAD_URL = 'https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v1.1.json'


def fetch_squad_samples(limit: int = DEFAULT_SAMPLE_LIMIT) -> list[dict]:
    if limit < 1:
        raise ValueError('limit deve essere positivo')
    response = requests.get(SQUAD_URL, timeout=60)
    response.raise_for_status()
    unique = {}
    for article in response.json()['data']:
        for paragraph in article['paragraphs']:
            context = paragraph['context'].strip()
            qa = next((qa for qa in paragraph['qas'] if qa.get('answers')), None)
            key = ' '.join(context.split())
            if context and qa and key not in unique:
                unique[key] = {
                    'id': qa['id'], 'argomento': article['title'].replace('_', ' '),
                    'domanda': qa['question'], 'contesto': context,
                    'risposte_corrette': [answer['text'] for answer in qa['answers']],
                    'token_stimati': int(len(context.split()) * 1.3),
                }
    pool = list(unique.values())
    count = min(limit, len(pool))
    if not count:
        raise ValueError('Nessun paragrafo valido nel benchmark scaricato')
    # Spread across the source corpus instead of taking repeated QAs from its start.
    return [pool[i * len(pool) // count] for i in range(count)]


def main() -> None:
    samples = fetch_squad_samples()
    DEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEST_FILE.with_suffix('.json.part')
    try:
        temporary.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(DEST_FILE)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Salvati {len(samples)} documenti originali distinti da SQuAD 1.1 in {DEST_FILE}')


if __name__ == '__main__':
    main()
