"""Tests for atomic model provisioning."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import requests

from core.engine import ModelDownloadError, assicura_presenza_modello


class _InterruptedResponse:
    """Small requests-compatible response that fails mid-stream."""

    headers = {"Content-Length": "12"}

    def __enter__(self) -> _InterruptedResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        yield b"partial"
        raise requests.ConnectionError("stream interrotto")


def test_interrupted_download_removes_partial_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "model.gguf"
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _InterruptedResponse())
    with pytest.raises(ModelDownloadError):
        assicura_presenza_modello(destination)
    assert not destination.exists()
    assert list(destination.parent.glob("*.part")) == []


def test_bare_filename_is_a_valid_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    destination = Path("model.gguf")
    response = _InterruptedResponse()
    response.headers = {"Content-Length": "7"}
    response.iter_content = lambda chunk_size: iter([b"partial"])  # type: ignore[method-assign]
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    assicura_presenza_modello(destination)
    assert destination.read_bytes() == b"partial"


def test_content_length_mismatch_removes_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "model.gguf"
    response = _InterruptedResponse()
    response.iter_content = lambda chunk_size: iter([b"partial"])  # type: ignore[method-assign]
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    with pytest.raises(ModelDownloadError, match="incompleto"):
        assicura_presenza_modello(destination)
    assert not destination.exists()


def test_custom_model_url_is_used_for_a_missing_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "custom.gguf"
    response = _InterruptedResponse()
    response.headers = {"Content-Length": "7"}
    response.iter_content = lambda chunk_size: iter([b"partial"])  # type: ignore[method-assign]
    observed: dict[str, str] = {}

    def fake_get(url: str, **kwargs: object) -> _InterruptedResponse:
        del kwargs
        observed["url"] = url
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    assicura_presenza_modello(destination, model_url="https://models.local/custom.gguf")

    assert observed["url"] == "https://models.local/custom.gguf"
    assert destination.read_bytes() == b"partial"


def test_public_prompt_cap_includes_query_and_template() -> None:
    from core.engine import LocalNeuralEngine
    from core.model_config import costruisci_prompt
    class Tokenizer:
        def tokenize(self, text):
            return list(text)
    engine = LocalNeuralEngine.__new__(LocalNeuralEngine)
    engine.llm = Tokenizer()
    engine.n_ctx = 4096
    base = len(costruisci_prompt('', 'query').encode())
    context = engine.limita_contesto('private document words ' * 100, 'query', base + 50, 30)
    assert len(costruisci_prompt(context, 'query').encode()) <= base + 50
    with pytest.raises(ValueError, match='Query e template'):
        engine.limita_contesto('context', 'query', base - 1, 30)
    with pytest.raises(ValueError, match='n_ctx'):
        engine.limita_contesto('context', 'query', 4096, 30)
