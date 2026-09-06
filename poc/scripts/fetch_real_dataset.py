#!/usr/bin/env python3
"""
Scarica un campione reale di dati accademici dal benchmark SQuAD v2
(utilizzato nel paper di riferimento DP-RAG) e lo organizza per lunghezza dei token.
"""

import json
import os

import requests

__all__ = ["fetch_squad_samples", "main"]

DEST_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "squad_real_benchmark.json")
DEFAULT_SAMPLE_LIMIT = 25

def fetch_squad_samples(limit: int = DEFAULT_SAMPLE_LIMIT) -> list[dict]:
    """Fetch valid answerable SQuAD validation rows.

    Args:
        limit: Maximum number of rows requested from the datasets service.

    Returns:
        Normalized benchmark records sorted by estimated token count.
    """

    url = f"https://datasets-server.huggingface.co/rows?dataset=rajpurkar%2Fsquad&config=plain_text&split=validation&offset=0&limit={limit}"
    print(f"Download di {limit} esempi reali da SQuAD v2 via Hugging Face...")
    
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    samples = []
    for item in data.get("rows", []):
        row = item.get("row", {})
        context = row.get("context", "").strip()
        question = row.get("question", "").strip()
        answers = row.get("answers", {}).get("text", [])
        title = row.get("title", "").replace("_", " ")

        if context and question and answers:
            # Stima approssimativa parole/token (1 parola ~ 1.3 token)
            word_count = len(context.split())
            approx_tokens = int(word_count * 1.3)

            samples.append({
                "id": row.get("id"),
                "argomento": title,
                "domanda": question,
                "risposte_corrette": answers,
                "contesto": context,
                "conteggio_parole": word_count,
                "token_stimati": approx_tokens
            })

    # Ordina per lunghezza di contesto crescente
    samples.sort(key=lambda x: x["token_stimati"])
    return samples

def main() -> None:
    """Download the default benchmark sample into the local data directory."""

    os.makedirs(os.path.dirname(DEST_FILE), exist_ok=True)
    samples = fetch_squad_samples(limit=DEFAULT_SAMPLE_LIMIT)
    
    with open(DEST_FILE, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)

    print(f"Salvati {len(samples)} campioni reali in: {DEST_FILE}")
    print("\nDistribuzione lunghezze contesto (token stimati):")
    for s in samples[:5]:
        print(f" - [{s['argomento']}] ~{s['token_stimati']} token | Domanda: {s['domanda'][:60]}...")
    print(" ...")
    for s in samples[-3:]:
        print(f" - [{s['argomento']}] ~{s['token_stimati']} token | Domanda: {s['domanda'][:60]}...")

if __name__ == "__main__":
    main()
