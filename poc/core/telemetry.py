"""
Modulo Telemetria: Gestione del tracciamento distribuito su Langfuse.
"""

import os
from typing import Optional, List, Dict

class LangfuseTracer:
    def __init__(self, pk: Optional[str] = None, sk: Optional[str] = None, host: Optional[str] = None):
        self.public_key = pk or os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = sk or os.environ.get("LANGFUSE_SECRET_KEY")
        self.host = host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self.client = None
        self.current_trace = None
        self._connetti()

    def _connetti(self):
        if not self.public_key or not self.secret_key:
            return
        try:
            from langfuse import Langfuse
            client = Langfuse(public_key=self.public_key, secret_key=self.secret_key, host=self.host)
            if client.auth_check():
                self.client = client
        except Exception:
            self.client = None

    @property
    def is_active(self) -> bool:
        return self.client is not None

    def avvia_richiesta(self, domanda: str, metadata: Optional[Dict] = None):
        if not self.is_active:
            return
        self.current_trace = self.client.trace(
            name="dp-rag-distributed-request",
            input={"domanda": domanda},
            metadata=metadata or {}
        )

    def registra_fase_edge(self, n_documenti: int, bozze: List[str], durata_ms: float, tok_per_sec: float):
        if not self.current_trace:
            return
        span = self.current_trace.span(
            name="edge-neural-ensemble",
            input={"documenti_elaborati": n_documenti},
            metadata={
                "durata_ms": durata_ms,
                "velocita_tok_s": tok_per_sec
            }
        )
        span.end(output={"bozze_generate": bozze})

    def registra_fase_privacy(self, epsilon: float, tau: float, conteggi_reali: Dict, rilasciati: List[str], scartati: List[str]):
        if not self.current_trace:
            return
        span = self.current_trace.span(
            name="dp-ptr-filter",
            input={"raw_counts": conteggi_reali},
            metadata={"epsilon": epsilon, "tau": tau}
        )
        span.end(output={"termini_rilasciati": rilasciati, "termini_scartati": scartati})

    def registra_fase_cloud(self, risposta_finale: str, byte_inviati: int, risparmio_perc: float, latenza_sec: float) -> Optional[str]:
        if not self.current_trace:
            return None
        gen = self.current_trace.generation(
            name="cloud-llm-generation",
            model="gpt-4o-mini",
            output=risposta_finale,
            metadata={
                "byte_inviati": byte_inviati,
                "risparmio_rete_percentuale": risparmio_perc,
                "latenza_ms": latenza_sec * 1000
            }
        )
        gen.end()
        self.current_trace.update(output=risposta_finale)
        self.client.flush()
        try:
            return self.current_trace.get_trace_url()
        except Exception:
            return None
