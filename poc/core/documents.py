"""Local document ingestion and per-document lexical retrieval.

One source document contributes at most one response. Scores and excerpt
selection depend only on that document and the public query (no corpus IDF).
The fixed-size retrieval pads missing documents with empty public slots.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf.errors import PyPdfError

SUPPORTED_SUFFIXES = {'.txt', '.md', '.pdf'}


def normalized_content(text: str) -> str:
    return ' '.join(text.split())


def content_id(text: str) -> str:
    return hashlib.sha256(normalized_content(text).encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class LocalDocument:
    id: str
    text: str
    source: str


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    id: str
    context: str
    source: str
    score: int
    is_padding: bool = False


class DocumentCorpus:
    """Deduplicate original documents; never treat chunks as ensemble members."""

    def __init__(self, documents: list[LocalDocument]) -> None:
        unique: dict[str, LocalDocument] = {}
        for document in documents:
            if not document.text.strip():
                raise ValueError(f'Documento senza testo: {document.source}')
            key = content_id(document.text)
            unique.setdefault(key, LocalDocument(key, document.text, document.source))
        self.documents = tuple(sorted(unique.values(), key=lambda doc: doc.id))
        self.duplicates_removed = len(documents) - len(self.documents)

    @classmethod
    def from_path(cls, path: str | Path) -> DocumentCorpus:
        """Read only an explicitly supplied file/directory; UTF-8 or text PDF.

        Symlinks are excluded from directory scans. Scanned/image PDFs require
        local OCR upstream; no automatic cloud OCR or document upload occurs.
        """
        root = Path(path).expanduser()
        if not root.exists():
            raise ValueError(f'Percorso documenti inesistente: {root}')
        paths = [root] if root.is_file() else sorted(
            item for item in root.rglob('*')
            if item.is_file() and not item.is_symlink()
            and not any(part.startswith('.') for part in item.relative_to(root).parts)
            and item.suffix.lower() in SUPPORTED_SUFFIXES
        )
        if not paths:
            raise ValueError('Nessun documento TXT, Markdown o PDF nel percorso')
        documents = []
        for item in paths:
            if item.suffix.lower() not in SUPPORTED_SUFFIXES:
                raise ValueError(f'Formato non supportato: {item.suffix}')
            try:
                if item.suffix.lower() == '.pdf':
                    from pypdf import PdfReader
                    reader = PdfReader(item)
                    if reader.is_encrypted:
                        raise ValueError(f'PDF cifrato non supportato: {item.name}')
                    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                else:
                    text = item.read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError, PyPdfError) as exc:
                raise ValueError(f'Impossibile leggere il documento: {item.name}') from exc
            if not text.strip():
                raise ValueError(f'Nessun testo estraibile da {item.name}; per scansioni usare OCR locale')
            documents.append(LocalDocument(content_id(text), text, str(item)))
        return cls(documents)

    def retrieve(self, query: str, n: int, chunk_words: int = 400) -> list[RetrievedDocument]:
        """Independent lexical scores, stable ties, one best excerpt per source.

        With a public fixed n, changing one unique source changes at most one
        selected member (replacement adjacency), ignoring output order. Local
        generations must be independent and the histogram permutation invariant.
        Scores/IDs/excerpts are local diagnostics, never DP releases.
        """
        if not query.strip() or n < 1 or chunk_words < 1:
            raise ValueError('Servono query, n e chunk_words positivi')
        query_terms = set(re.findall(r'\w+', query.casefold()))
        candidates = []
        for doc in self.documents:
            words = doc.text.split()
            chunks = [' '.join(words[i:i + chunk_words]) for i in range(0, len(words), chunk_words)]
            scores = [len(query_terms & set(re.findall(r'\w+', chunk.casefold()))) for chunk in chunks]
            best = max(range(len(chunks)), key=lambda i: (scores[i], -i))
            candidates.append(RetrievedDocument(doc.id, chunks[best], doc.source, scores[best]))
        selected = sorted(candidates, key=lambda doc: (-doc.score, doc.id))[:n]
        return selected + [
            RetrievedDocument(f'public-empty-{i}', '', '', 0, True)
            for i in range(n - len(selected))
        ]
