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


def test_missing_content_length_still_accepts_non_empty_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Content-Length assente: nessuna verifica di consistenza, ma il
    download non-vuoto deve andare a buon fine (atomicità basata sui byte
    effettivamente ricevuti)."""
    destination = tmp_path / "model.gguf"
    response = _InterruptedResponse()
    response.headers = {}
    response.iter_content = lambda chunk_size: iter([b"partial"])  # type: ignore[method-assign]
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    assicura_presenza_modello(destination)
    assert destination.read_bytes() == b"partial"


@pytest.mark.parametrize("bad_url", ["", "   ", None, 123])
def test_invalid_model_url_is_rejected(tmp_path: Path, bad_url: object) -> None:
    """URL vuoto, non-stringa o None deve essere rifiutato prima del download."""
    destination = tmp_path / "model.gguf"
    with pytest.raises(ValueError):
        assicura_presenza_modello(destination, model_url=bad_url)  # type: ignore[arg-type]


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


def test_gpu_offload_supported_on_accelerated_host() -> None:
    """If llama_cpp is installed and nvidia-smi is present, verify GPU offload."""
    import shutil

    try:
        import llama_cpp
    except ImportError:
        pytest.skip("llama_cpp non installato")
    if shutil.which("nvidia-smi"):
        assert llama_cpp.llama_supports_gpu_offload() is True


def test_local_neural_engine_inference_with_local_model_if_present() -> None:
    """Run one real inference if the local GGUF model is present on disk."""
    from core.engine import LocalNeuralEngine
    from core.model_config import percorso_modello_predefinito

    model_path = percorso_modello_predefinito()
    if not model_path.is_file():
        pytest.skip("Modello GGUF locale non presente")
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        pytest.skip("llama_cpp non installato")

    engine = LocalNeuralEngine(model_path=model_path, n_gpu_layers=-1)
    out = engine.genera_bozza("Contesto di test", "Domanda?", max_tokens=5)
    assert out.durata_totale_sec > 0.0
    assert out.prompt_tokens > 0

