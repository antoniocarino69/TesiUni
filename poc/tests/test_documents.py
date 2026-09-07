"""Document privacy unit, retrieval stability and supported local formats."""
from pathlib import Path

import pytest

from core.documents import DocumentCorpus, LocalDocument


def doc(text: str) -> LocalDocument:
    return LocalDocument(text, text, 'synthetic')


def test_duplicates_and_chunks_never_multiply_votes(tmp_path: Path) -> None:
    (tmp_path / 'one.txt').write_text('alpha beta ' * 1000)
    (tmp_path / 'duplicate.md').write_text('alpha   beta\n' * 1000)
    corpus = DocumentCorpus.from_path(tmp_path)
    result = corpus.retrieve('alpha', 5, chunk_words=10)
    assert len(corpus.documents) == 1
    assert corpus.duplicates_removed == 1
    assert sum(not d.is_padding for d in result) == 1
    assert len(result[0].context.split()) == 10


def test_query_retrieval_and_replacement_stability() -> None:
    originals = [doc(f'alpha item{i}') for i in range(10)]
    original = DocumentCorpus(originals).retrieve('alpha beta', 5)
    for i in range(10):
        adjacent = DocumentCorpus(originals[:i] + [doc('alpha beta new')] + originals[i+1:])
        selected = adjacent.retrieve('alpha beta', 5)
        assert selected[0].context == 'alpha beta new'
        assert len({d.id for d in original} - {d.id for d in selected}) <= 1


def test_best_chunk_is_chosen_within_one_document() -> None:
    corpus = DocumentCorpus([doc('irrelevant words alpha beta')])
    assert corpus.retrieve('alpha beta', 1, chunk_words=2)[0].context == 'alpha beta'


def test_pdf_text_is_read_locally(tmp_path: Path) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
        NameObject('/F1'): writer._add_object(font),
    })})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 100 Td (alpha beta) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    path = tmp_path / 'text.pdf'
    writer.write(path)
    assert 'alpha beta' in DocumentCorpus.from_path(path).documents[0].text


def test_empty_scans_and_unsupported_inputs_are_explicit(tmp_path: Path) -> None:
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    path = tmp_path / 'scan.pdf'
    writer.write(path)
    with pytest.raises(ValueError, match='OCR locale'):
        DocumentCorpus.from_path(path)
    with pytest.raises(ValueError, match='inesistente'):
        DocumentCorpus.from_path(tmp_path / 'missing')
    with pytest.raises(ValueError):
        DocumentCorpus([doc('')])


def test_directory_does_not_read_symlinks_or_hidden_files(tmp_path: Path) -> None:
    (tmp_path / '.hidden.txt').write_text('private')
    (tmp_path / 'visible.md').write_text('public')
    (tmp_path / 'link.txt').symlink_to(tmp_path / '.hidden.txt')
    corpus = DocumentCorpus.from_path(tmp_path)
    assert len(corpus.documents) == 1
    assert corpus.documents[0].text == 'public'
