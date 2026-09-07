"""Local neural inference and reliable GGUF model provisioning.

Responsibilities:
    * Download the configured GGUF model atomically when it is absent.
    * Show download progress and validate the HTTP ``Content-Length``.
    * Run local ``llama.cpp`` inference and expose measured token metrics.

External dependencies:
    ``requests`` downloads the model, ``rich`` renders progress, and
    ``llama-cpp-python`` performs local inference.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import requests
from rich.progress import Progress

from .model_config import (
    DEFAULT_LOCAL_MODEL_CONFIG,
    costruisci_prompt,
    percorso_modello_predefinito,
    stima_tempo_prefill,
)

__all__ = [
    "DEFAULT_MODEL_FILENAME",
    "DEFAULT_MODEL_URL",
    "LocalNeuralEngine",
    "ModelDownloadError",
    "OutputInferenza",
    "assicura_presenza_modello",
]

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL_FILENAME = DEFAULT_LOCAL_MODEL_CONFIG.filename
DEFAULT_MODEL_URL = DEFAULT_LOCAL_MODEL_CONFIG.url
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_SIZE_BYTES = 131_072
LOCAL_MAX_TOKENS = DEFAULT_LOCAL_MODEL_CONFIG.max_tokens
PREFILL_GENERATION_RATIO = DEFAULT_LOCAL_MODEL_CONFIG.prefill_generation_ratio
SYSTEM_PROMPT = DEFAULT_LOCAL_MODEL_CONFIG.system_prompt


@dataclass(frozen=True, slots=True)
class OutputInferenza:
    """Metrics and text returned by one local model invocation."""

    testo: str
    prompt_tokens: int
    completion_tokens: int
    durata_totale_sec: float
    tempo_prefill_stimato_sec: float
    token_al_secondo: float


class ModelDownloadError(RuntimeError):
    """Raised when the local GGUF model cannot be downloaded safely."""


def _parse_content_length(headers: Mapping[str, str]) -> int | None:
    """Parse an optional HTTP Content-Length header."""

    raw_length = headers.get("Content-Length")
    if raw_length is None:
        return None
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ModelDownloadError(
            f"Content-Length non valido ricevuto dal server: {raw_length!r}"
        ) from exc
    if length < 0:
        raise ModelDownloadError("Content-Length non può essere negativo")
    return length


def assicura_presenza_modello(
    model_path: str | os.PathLike[str],
    model_url: str = DEFAULT_MODEL_URL,
) -> None:
    """Ensure that a complete GGUF model exists at ``model_path``.

    The response is written to a temporary file in the target directory and
    atomically renamed only after the stream has completed and its byte count
    matches ``Content-Length``. A failed download therefore cannot poison the
    final path or prevent a later retry.

    Args:
        model_path: Destination path for the GGUF file. A bare filename is
            valid and resolves to the current directory.
        model_url: Source URL used only when ``model_path`` is absent. The
            caller is responsible for matching the URL to the requested GGUF
            model; the destination path alone does not identify a model.

    Raises:
        ModelDownloadError: If the HTTP request, stream, or integrity check
            fails.
        OSError: If the destination directory cannot be created.
    """

    destination = Path(model_path)
    if destination.is_file():
        return
    if destination.exists():
        raise ModelDownloadError(f"Il percorso del modello non è un file: {destination}")
    if not isinstance(model_url, str) or not model_url.strip():
        raise ValueError("model_url deve essere una URL non vuota")

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        LOGGER.info("Download modello da %s verso %s", model_url, destination)
        with requests.get(
            model_url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()
            expected_bytes = _parse_content_length(response.headers)
            downloaded_bytes = 0
            with Progress(transient=True) as progress:
                task_id = progress.add_task(
                    "Download modello GGUF",
                    total=expected_bytes,
                )
                with temporary_path.open("wb") as model_file:
                    for chunk in response.iter_content(
                        chunk_size=DOWNLOAD_CHUNK_SIZE_BYTES
                    ):
                        if not chunk:
                            continue
                        model_file.write(chunk)
                        downloaded_bytes += len(chunk)
                        progress.update(task_id, completed=downloaded_bytes)
                    model_file.flush()
                    os.fsync(model_file.fileno())

        if expected_bytes is not None and downloaded_bytes != expected_bytes:
            raise ModelDownloadError(
                "Download modello incompleto: "
                f"ricevuti {downloaded_bytes} byte su {expected_bytes}"
            )
        if downloaded_bytes == 0:
            raise ModelDownloadError("Il server ha restituito un modello vuoto")
        os.replace(temporary_path, destination)
        LOGGER.info("Modello scaricato correttamente: %s byte", downloaded_bytes)
    except requests.RequestException as exc:
        LOGGER.exception("Download del modello fallito")
        raise ModelDownloadError("Download del modello fallito") from exc
    except OSError as exc:
        LOGGER.exception("Errore filesystem durante il download del modello")
        raise ModelDownloadError("Impossibile salvare il modello") from exc
    finally:
        temporary_path.unlink(missing_ok=True)


class LocalNeuralEngine:
    """Manage local ``llama.cpp`` inference.

    Args:
        model_path: Optional GGUF path. When omitted, the model is stored in
            ``poc/models`` using :data:`DEFAULT_MODEL_FILENAME`.
        n_ctx: Context-window size passed to ``llama_cpp.Llama``.
        model_url: Optional download URL for a custom GGUF model.
        n_gpu_layers: Number of layers offloaded to the available accelerator.
        verbose: Whether llama.cpp should emit verbose logs.

    Raises:
        ModelDownloadError: If the default model is absent and cannot be
            provisioned.
        ImportError: If ``llama-cpp-python`` is not installed.
    """

    def __init__(
        self,
        model_path: str | os.PathLike[str] | None = None,
        n_ctx: int = DEFAULT_LOCAL_MODEL_CONFIG.n_ctx,
        model_url: str | None = None,
        n_gpu_layers: int = DEFAULT_LOCAL_MODEL_CONFIG.n_gpu_layers,
        verbose: bool = DEFAULT_LOCAL_MODEL_CONFIG.verbose,
    ) -> None:
        if n_ctx < 1:
            raise ValueError("n_ctx deve essere positivo")
        if model_path is None:
            model_path = percorso_modello_predefinito()
        selected_model_url = DEFAULT_MODEL_URL if model_url is None else model_url
        assicura_presenza_modello(model_path, model_url=selected_model_url)

        from llama_cpp import Llama

        self.model_path = str(model_path)
        self.model_url = selected_model_url
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.verbose = verbose
        self.llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            verbose=verbose,
        )

    def limita_contesto(self, contesto: str, domanda: str, prompt_token_budget: int,
                        max_tokens: int = LOCAL_MAX_TOKENS) -> str:
        """Fit one excerpt into a PUBLIC total prompt cap using the real tokenizer.

        Truncation is local to one document. Query/template overhead is included;
        impossible public query budgets are rejected before generation.
        """
        if prompt_token_budget < 1 or prompt_token_budget + max_tokens > self.n_ctx:
            raise ValueError("Budget prompt e generazione incompatibili con n_ctx")
        def count(text: str) -> int:
            return len(self.llm.tokenize(costruisci_prompt(text, domanda).encode('utf-8')))
        if count('') > prompt_token_budget:
            raise ValueError("Query e template superano il budget pubblico del prompt")
        # Removing a word can increase BPE token count; check the final prompt
        # after each truncation rather than assuming token-count monotonicity.
        words = contesto.split()
        while words:
            candidate = ' '.join(words)
            total = count(candidate)
            if total <= prompt_token_budget:
                return candidate
            remove = max(1, int(len(words) * (total - prompt_token_budget) / total))
            words = words[:-remove]
        return ''

    def genera_bozza(
        self,
        contesto: str,
        domanda: str,
        max_tokens: int = LOCAL_MAX_TOKENS,
    ) -> OutputInferenza:
        """Generate a concise local answer and collect timing metrics.

        Args:
            contesto: Retrieved document context kept on the edge device.
            domanda: User question.
            max_tokens: Maximum completion tokens.

        Returns:
            Generated text and inference/token measurements.

        Raises:
            ValueError: If ``max_tokens`` is not positive.
        """

        if max_tokens < 1:
            raise ValueError("max_tokens deve essere positivo")
        prompt = costruisci_prompt(contesto, domanda)

        t0 = time.perf_counter()
        risultato = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=DEFAULT_LOCAL_MODEL_CONFIG.temperature,
            stop=list(DEFAULT_LOCAL_MODEL_CONFIG.stop),
        )
        durata = time.perf_counter() - t0

        testo_generato = str(risultato["choices"][0]["text"]).strip()
        usage = risultato["usage"]
        n_prompt_tok = int(usage["prompt_tokens"])
        n_comp_tok = int(usage["completion_tokens"])
        prefill_stima = stima_tempo_prefill(
            durata,
            n_prompt_tok,
            n_comp_tok,
        )
        velocita = n_comp_tok / durata if durata > 0.0 else 0.0

        return OutputInferenza(
            testo=testo_generato,
            prompt_tokens=n_prompt_tok,
            completion_tokens=n_comp_tok,
            durata_totale_sec=durata,
            tempo_prefill_stimato_sec=prefill_stima,
            token_al_secondo=velocita,
        )
