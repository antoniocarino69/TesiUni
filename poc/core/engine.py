"""
Modulo Engine: Gestore dell'inferenza neurale locale tramite llama.cpp (Metal/CUDA).
"""

import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class OutputInferenza:
    testo: str
    prompt_tokens: int
    completion_tokens: int
    durata_totale_sec: float
    tempo_prefill_sec: float
    token_al_secondo: float

class LocalNeuralEngine:
    def __init__(self, model_path: Optional[str] = None, n_ctx: int = 4096):
        if not model_path:
            model_path = os.path.join(os.path.dirname(__file__), "..", "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Modello non trovato in {model_path}")

        from llama_cpp import Llama
        self.model_path = model_path
        self.llm = Llama(
            model_path=model_path,
            n_gpu_layers=-1,  # Tutta la rete su GPU (Metal su Apple Silicon, CUDA su PC)
            n_ctx=n_ctx,
            verbose=False
        )

    def genera_bozza(self, contesto: str, domanda: str, max_tokens: int = 30) -> OutputInferenza:
        """Esegue l'inferenza della bozza misurando i tempi di prefill e generazione."""
        prompt = (
            f"<|im_start|>system\nYou are a precise and concise factual extractor. "
            f"Answer using ONLY facts from the provided context in under 10 words.<|im_end|>\n"
            f"<|im_start|>user\nContext:\n{contesto}\n\nQuestion: {domanda}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        t0 = time.perf_counter()
        risultato = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=0.2,
            stop=["<|im_end|>", "\n\n"]
        )
        t1 = time.perf_counter()

        testo_generato = risultato["choices"][0]["text"].strip()
        usage = risultato["usage"]
        n_prompt_tok = usage["prompt_tokens"]
        n_comp_tok = usage["completion_tokens"]
        durata = t1 - t0

        vel_tok = n_comp_tok / durata if durata > 0 else 0
        # Approssimazione del tempo prefill
        prefill_stima = durata * (n_prompt_tok / (n_prompt_tok + n_comp_tok * 4))

        return OutputInferenza(
            testo=testo_generato,
            prompt_tokens=n_prompt_tok,
            completion_tokens=n_comp_tok,
            durata_totale_sec=durata,
            tempo_prefill_sec=prefill_stima,
            token_al_secondo=vel_tok
        )
