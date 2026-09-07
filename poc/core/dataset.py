"""Dataset loading and reproducible ensemble sampling.

Responsibilities:
    * Validate and load the local SQuAD-derived benchmark JSON.
    * Expose topic filtering for coherent retrieval experiments.
    * Sample ensemble documents randomly, with an optional deterministic seed.

External dependencies:
    Only the Python standard library is required.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .documents import DocumentCorpus, LocalDocument, content_id

__all__ = ["DatasetLoader", "DocumentoBenchmark"]

DEFAULT_DATASET_PATH = (
    Path(__file__).parent.parent / "data" / "squad_real_benchmark.json"
)


@dataclass(frozen=True, slots=True)
class DocumentoBenchmark:
    """One benchmark document and its question-answer metadata."""

    id: str
    argomento: str
    domanda: str
    contesto: str
    risposte_attese: list[str]
    token_stimati: int


class DatasetLoader:
    """Load benchmark documents and produce ensemble samples.

    Args:
        data_path: Optional JSON path. The bundled SQuAD sample is used when
            omitted.

    Raises:
        FileNotFoundError: If the dataset path does not exist.
        ValueError: If the JSON structure is invalid.
    """

    def __init__(self, data_path: str | Path | None = None) -> None:
        self.data_path = Path(data_path) if data_path is not None else DEFAULT_DATASET_PATH
        self.documenti = self._carica()

    def _carica(self) -> list[DocumentoBenchmark]:
        """Read and validate the benchmark JSON file."""

        if not self.data_path.is_file():
            raise FileNotFoundError(
                f"File dataset non trovato in {self.data_path}. "
                "Esegui prima lo script di download."
            )
        try:
            with self.data_path.open("r", encoding="utf-8") as file_handle:
                raw_data: Any = json.load(file_handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON dataset non valido: {self.data_path}") from exc
        if not isinstance(raw_data, list):
            raise ValueError("il dataset deve contenere una lista di record")

        documenti: list[DocumentoBenchmark] = []
        for item in raw_data:
            if not isinstance(item, dict):
                raise ValueError("ogni record del dataset deve essere un oggetto JSON")
            try:
                if (any(not isinstance(item[name], str) or not item[name].strip()
                        for name in ("id", "argomento", "domanda", "contesto"))
                    or not isinstance(item["risposte_corrette"], list)
                    or any(not isinstance(answer, str) for answer in item["risposte_corrette"])
                    or not isinstance(item["token_stimati"], int)
                    or item["token_stimati"] < 0):
                    raise ValueError("tipi o valori non validi")
                documenti.append(
                    DocumentoBenchmark(
                        id=str(item["id"]),
                        argomento=str(item["argomento"]),
                        domanda=str(item["domanda"]),
                        contesto=str(item["contesto"]),
                        risposte_attese=[str(value) for value in item["risposte_corrette"]],
                        token_stimati=int(item["token_stimati"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("record dataset incompleto o non valido") from exc
        if not documenti:
            raise ValueError("il dataset non può essere vuoto")
        unique = {content_id(doc.contesto): doc for doc in reversed(documenti)}
        self.duplicates_removed = len(documenti) - len(unique)
        return list(unique.values())

    def as_corpus(self) -> DocumentCorpus:
        """Use unique original contexts, not repeated question/answer rows."""
        return DocumentCorpus([
            LocalDocument(content_id(doc.contesto), doc.contesto, doc.id)
            for doc in self.documenti
        ])

    def ottieni_per_argomento(self, argomento: str) -> list[DocumentoBenchmark]:
        """Return documents whose topic matches case-insensitively.

        Args:
            argomento: Topic to search.

        Returns:
            Matching benchmark documents in source order.
        """

        return [
            documento
            for documento in self.documenti
            if documento.argomento.casefold() == argomento.casefold()
        ]

    def ottieni_campione_ensemble(
        self,
        n: int = 5,
        seed: int | None = None,
    ) -> list[DocumentoBenchmark]:
        """Return a random ensemble sample without replacement.

        Args:
            n: Number of documents to sample.
            seed: Optional seed for a reproducible benchmark sample. When
                omitted, a fresh system-seeded generator is used.

        Returns:
            A newly allocated list containing ``n`` distinct documents.

        Raises:
            ValueError: If ``n`` is outside the available population.
        """

        if n < 1 or n > len(self.documenti):
            raise ValueError(
                f"n deve essere compreso tra 1 e {len(self.documenti)}, ricevuto {n}"
            )
        return random.Random(seed).sample(self.documenti, n)
