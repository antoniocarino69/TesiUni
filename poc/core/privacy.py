"""
Modulo Privacy Differenziale: Implementazione formale dell'algoritmo DP-KSA (PTR).
"""

import string
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np

STOPWORDS_ITALIANO_INGLESE = {
    # Italiano
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in", "con",
    "su", "per", "tra", "fra", "e", "ed", "o", "ha", "al", "del", "della", "delle", "dei",
    "ai", "agli", "alle", "dal", "dalla", "dalle", "nel", "nella", "è", "era", "sono", "stato",
    # Inglese (per i benchmark standard SQuAD/NQ)
    "the", "of", "and", "a", "to", "in", "is", "you", "that", "it", "he", "was", "for",
    "on", "are", "as", "with", "his", "they", "i", "at", "be", "this", "have", "from",
    "or", "one", "had", "by", "word", "but", "not", "what", "all", "were", "we", "when",
    "your", "can", "said", "there", "use", "an", "each", "which", "she", "do", "how", "their"
}

@dataclass
class EsitoDP:
    conteggi_reali: Dict[str, int]
    conteggi_rumorosi: Dict[str, float]
    rumore_applicato: Dict[str, float]
    parole_rilasciate: List[str]
    parole_scartate: List[str]
    epsilon: float
    soglia_tau: float

def normalizza_e_tokenizza(testo: str) -> List[str]:
    """Separa le parole rimuovendo punteggiatura e stopword."""
    testo_pulito = testo.replace("'", " ").replace("’", " ").replace("-", " ")
    parole = "".join(c if c.isalnum() or c.isspace() else " " for c in testo_pulito.lower()).split()
    return [p for p in parole if p not in STOPWORDS_ITALIANO_INGLESE and len(p) > 2]

class PrivacyFilterPTR:
    """
    Meccanismo Propose-Test-Release (PTR) con rumore Laplace.
    Sensibilità Delta = 1 (ogni documento privato influenza la frequenza di un termine al massimo di 1).
    """
    def __init__(self, epsilon: float = 1.0, soglia_tau: float = 3.0, sensibilità: float = 1.0):
        self.epsilon = max(epsilon, 1e-4)
        self.soglia_tau = soglia_tau
        self.sensibilità = sensibilità
        self.scala_rumore = self.sensibilità / self.epsilon

    def filtra(self, bozze_ensemble: List[str]) -> EsitoDP:
        conteggi: Dict[str, int] = {}
        for bozza in bozze_ensemble:
            termini_unici = set(normalizza_e_tokenizza(bozza))
            for t in termini_unici:
                conteggi[t] = conteggi.get(t, 0) + 1

        conteggi_rumorosi: Dict[str, float] = {}
        rumori: Dict[str, float] = {}
        rilasciati: List[str] = []
        scartati: List[str] = []

        for termine, freq in conteggi.items():
            rumore = float(np.random.laplace(0.0, self.scala_rumore))
            totale = freq + rumore

            conteggi_rumorosi[termine] = totale
            rumori[termine] = rumore

            if totale >= self.soglia_tau:
                rilasciati.append(termine)
            else:
                scartati.append(termine)

        rilasciati.sort(key=lambda x: conteggi_rumorosi[x], reverse=True)
        scartati.sort(key=lambda x: conteggi_rumorosi[x], reverse=True)

        return EsitoDP(
            conteggi_reali=conteggi,
            conteggi_rumorosi=conteggi_rumorosi,
            rumore_applicato=rumori,
            parole_rilasciate=rilasciati,
            parole_scartate=scartati,
            epsilon=self.epsilon,
            soglia_tau=self.soglia_tau
        )
