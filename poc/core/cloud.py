"""
Modulo Cloud: Connessione verso il provider di inferenza remota (OpenAI / mock).
"""

import os
import time
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class RisultatoCloud:
    risposta_testuale: str
    latenza_rete_sec: float
    byte_trasmessi_dp: int
    byte_grezzi_rag: int
    risparmio_percentuale: float

class CloudGenerator:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def genera(self, domanda: str, parole_chiave: List[str], testi_grezzi_per_confronto: List[str]) -> RisultatoCloud:
        kw_string = ", ".join(parole_chiave)
        prompt_cloud = (
            f"You are a factual synthesis assistant. Answer the user question based strictly on these "
            f"privately verified key concepts: [{kw_string}].\n\nQuestion: {domanda}"
        )
        byte_dp = len(prompt_cloud.encode("utf-8"))

        testo_totale_grezzo = "\n".join(testi_grezzi_per_confronto)
        byte_grezzi = len(testo_totale_grezzo.encode("utf-8"))
        risparmio = ((byte_grezzi - byte_dp) / byte_grezzi) * 100 if byte_grezzi > 0 else 0

        if not self.api_key:
            return RisultatoCloud(
                risposta_testuale=f"[Cloud Simulato] Synthesized response using verified terms [{kw_string}]: The answer is grounded in the retrieved facts.",
                latenza_rete_sec=0.150,  # 150 ms simulati di rete RTT
                byte_trasmessi_dp=byte_dp,
                byte_grezzi_rag=byte_grezzi,
                risparmio_percentuale=risparmio
            )

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            t0 = time.perf_counter()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a factual assistant. Answer clearly."},
                    {"role": "user", "content": prompt_cloud}
                ],
                max_tokens=60,
                temperature=0.2
            )
            t_call = time.perf_counter() - t0
            risposta = resp.choices[0].message.content.strip()
            return RisultatoCloud(
                risposta_testuale=risposta,
                latenza_rete_sec=t_call,
                byte_trasmessi_dp=byte_dp,
                byte_grezzi_rag=byte_grezzi,
                risparmio_percentuale=risparmio
            )
        except Exception as e:
            return RisultatoCloud(
                risposta_testuale=f"Errore API Cloud: {str(e)}",
                latenza_rete_sec=0.0,
                byte_trasmessi_dp=byte_dp,
                byte_grezzi_rag=byte_grezzi,
                risparmio_percentuale=risparmio
            )
