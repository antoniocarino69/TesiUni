"""Cloud inference adapter and network-volume accounting.

The adapter sends only the query and the keywords released by DP-KSA. When no
provider key or compatible endpoint is configured it returns a deterministic
local simulation, which keeps offline benchmarks reproducible without
weakening the privacy filter.

External dependencies:
    ``openai`` is imported lazily only for the configured remote mode.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

__all__ = ["CloudGenerator", "RisultatoCloud"]

LOGGER = logging.getLogger(__name__)
DEFAULT_CLOUD_MODEL = "gpt-4o-mini"
# Reasoning models such as MiMo can spend completion tokens before emitting
# the visible answer. A small cap can therefore produce a valid empty message.
DEFAULT_CLOUD_MAX_TOKENS = 1024
DEFAULT_CLOUD_TEMPERATURE = 0.2


@dataclass(frozen=True, slots=True)
class RisultatoCloud:
    """Cloud response and system-level transfer metrics."""

    risposta_testuale: str
    latenza_rete_sec: float
    byte_trasmessi_dp: int
    byte_grezzi_rag: int
    risparmio_percentuale: float
    errore: str | None = None
    simulato: bool = False


class CloudGenerator:
    """Generate the final answer from DP-released keywords.

    The remote adapter uses the OpenAI Chat Completions protocol, not the
    OpenAI service specifically. ``base_url`` can point to any compatible
    provider, including a self-hosted deployment. When neither credentials
    nor a base URL are configured, the deterministic simulation is used.

    Args:
        api_key: Optional provider key. ``CLOUD_API_KEY`` and then
            ``OPENAI_API_KEY`` are used when omitted.
        base_url: Optional OpenAI-compatible endpoint. ``CLOUD_BASE_URL`` and
            then ``OPENAI_BASE_URL`` are used when omitted.
        model: Provider model identifier. ``CLOUD_MODEL`` and then
            ``OPENAI_MODEL`` are used when omitted.
        client: Optional already-created compatible client, useful for local
            adapters and tests. It must expose
            ``chat.completions.create(...)``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        offline: bool = False,
    ) -> None:
        self.api_key = api_key or os.environ.get("CLOUD_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        self.base_url = base_url or os.environ.get("CLOUD_BASE_URL") or os.environ.get(
            "OPENAI_BASE_URL"
        )
        self.model = model or os.environ.get("CLOUD_MODEL") or os.environ.get(
            "OPENAI_MODEL", DEFAULT_CLOUD_MODEL
        )
        self._client = client
        self.offline = offline

    def genera(
        self,
        domanda: str,
        parole_chiave: list[str],
        testi_grezzi_per_confronto: list[str],
    ) -> RisultatoCloud:
        """Generate an answer using only privacy-filtered keywords.

        Args:
            domanda: User query.
            parole_chiave: Exact tokens released by DP-KSA.
            testi_grezzi_per_confronto: Local-only contexts used to estimate
                the bandwidth saved by the privacy path.

        Returns:
            Cloud response, latency, and byte-volume metrics. Provider
            failures are logged with the original exception and returned as a
            generic ``errore="provider_error"`` result so a benchmark can
            still complete without exposing provider internals to the caller.
        """

        keyword_string = ", ".join(sorted(set(parole_chiave)))
        prompt_cloud = (
            "You are a factual synthesis assistant. Answer the user question "
            "based strictly on these privately verified key concepts: "
            f"[{keyword_string}].\n\nQuestion: {domanda}"
        )
        if not parole_chiave:
            prompt_cloud = f"Answer the question using your general knowledge. Question: {domanda}"
        # Text-volume estimates only: excludes JSON, headers, TLS and retries.
        byte_dp = len(prompt_cloud.encode("utf-8"))
        byte_grezzi = len("\n".join(testi_grezzi_per_confronto).encode("utf-8"))
        risparmio = (
            ((byte_grezzi - byte_dp) / byte_grezzi) * 100.0
            if byte_grezzi > 0
            else 0.0
        )

        if self.offline or (self._client is None and not self.api_key and not self.base_url):
            return RisultatoCloud(
                risposta_testuale=(
                    "[Cloud Simulato] Synthesized response using verified terms "
                    f"[{keyword_string}]. This simulation does not answer the question."
                ),
                latenza_rete_sec=0.0,
                simulato=True,
                byte_trasmessi_dp=byte_dp,
                byte_grezzi_rag=byte_grezzi,
                risparmio_percentuale=risparmio,
            )

        t0 = time.perf_counter()
        try:
            if self._client is None:
                from openai import OpenAI

                client_kwargs: dict[str, Any] = {
                    "api_key": self.api_key or "not-needed",
                }
                if self.base_url:
                    client_kwargs["base_url"] = self.base_url
                if self.base_url and self.base_url.startswith("https://opencode.ai/zen/go/"):
                    client_kwargs["default_headers"] = {
                        "x-opencode-session": f"poc-{uuid4().hex}",
                    }
                client = OpenAI(**client_kwargs)
            else:
                client = self._client
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a factual assistant. Answer clearly."},
                    {"role": "user", "content": prompt_cloud},
                ],
                max_tokens=DEFAULT_CLOUD_MAX_TOKENS,
                temperature=DEFAULT_CLOUD_TEMPERATURE,
            )
            latency = time.perf_counter() - t0
            response_text = response.choices[0].message.content or ""
            response_text = str(response_text).strip()
            if not response_text:
                finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
                LOGGER.error(
                    "Il provider cloud ha restituito una risposta senza testo; "
                    "finish_reason=%s",
                    finish_reason,
                )
                return RisultatoCloud(
                    risposta_testuale=(
                        "Errore API Cloud: il provider non ha restituito una risposta testuale."
                    ),
                    latenza_rete_sec=latency,
                    byte_trasmessi_dp=byte_dp,
                    byte_grezzi_rag=byte_grezzi,
                    risparmio_percentuale=risparmio,
                    errore="empty_response",
                )
            return RisultatoCloud(
                risposta_testuale=response_text,
                latenza_rete_sec=latency,
                byte_trasmessi_dp=byte_dp,
                byte_grezzi_rag=byte_grezzi,
                risparmio_percentuale=risparmio,
            )
        except Exception:
            LOGGER.exception("Chiamata al provider cloud fallita")
            return RisultatoCloud(
                risposta_testuale="Errore API Cloud: impossibile completare la richiesta.",
                latenza_rete_sec=time.perf_counter() - t0,
                byte_trasmessi_dp=byte_dp,
                byte_grezzi_rag=byte_grezzi,
                risparmio_percentuale=risparmio,
                errore="provider_error",
            )
