#!/usr/bin/env python3
"""
Script per scaricare un modello compatto reale (Qwen 2.5 0.5B GGUF, ~398MB)
nella cartella poc/models/.
"""

import os
from huggingface_hub import hf_hub_download

MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
DEST_DIR = os.path.join(os.path.dirname(__file__), "models")

def main():
    os.makedirs(DEST_DIR, exist_ok=True)
    target_path = os.path.join(DEST_DIR, MODEL_FILE)

    if os.path.exists(target_path):
        print(f"Modello già presente: {target_path}")
        return target_path

    print(f"Download in corso di {MODEL_FILE} da Hugging Face ({MODEL_REPO})...")
    path = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILE,
        local_dir=DEST_DIR
    )
    print(f"Modello scaricato con successo in: {path}")
    return path

if __name__ == "__main__":
    main()
