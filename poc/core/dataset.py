"""
Modulo Dataset: Caricamento e gestione dei documenti reali dal benchmark accademico.
"""

import os
import json
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DocumentoBenchmark:
    id: str
    argomento: str
    domanda: str
    contesto: str
    risposte_attese: List[str]
    token_stimati: int

class DatasetLoader:
    def __init__(self, data_path: Optional[str] = None):
        if not data_path:
            data_path = os.path.join(os.path.dirname(__file__), "..", "data", "squad_real_benchmark.json")
        self.data_path = data_path
        self.documenti: List[DocumentoBenchmark] = []
        self._carica()

    def _carica(self):
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"File dataset non trovato in {self.data_path}. Esegui prima lo script di download.")
        
        with open(self.data_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        for item in raw_data:
            self.documenti.append(DocumentoBenchmark(
                id=item["id"],
                argomento=item["argomento"],
                domanda=item["domanda"],
                contesto=item["contesto"],
                risposte_attese=item["risposte_corrette"],
                token_stimati=item["token_stimati"]
            ))

    def ottieni_per_argomento(self, argomento: str) -> List[DocumentoBenchmark]:
        return [d for d in self.documenti if d.argomento.lower() == argomento.lower()]

    def ottieni_campione_ensemble(self, n: int = 5) -> List[DocumentoBenchmark]:
        """Ritorna i primi N documenti reali per formare l'ensemble locale."""
        return self.documenti[:n]
