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

__all__ = ["CloudGenerator", "RisultatoCloud", "RisultatoProbe"]

LOGGER = logging.getLogger(__name__)
DEFAULT_CLOUD_MODEL = "gpt-4o-mini"
# Reasoning models such as MiMo can spend completion tokens before emitting
# the visible answer. A small cap can therefore produce a valid empty message.
DEFAULT_CLOUD_MAX_TOKENS = 1024
DEFAULT_CLOUD_TEMPERATURE = 0.2
# Probe budget: a single tiny generation keeps the per-session setup cost
# negligible compared to a real request. The answer is irrelevant.
PROBE_QUERY = "Reply with one short sentence confirming this public probe."
PROBE_MAX_TOKENS = 16


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


@dataclass(frozen=True, slots=True)
class RisultatoProbe:
    """Result of a one-shot public probe of the cloud adapter.

    The probe runs at session start to measure the end-to-end latency of the
    configured cloud client without exposing any private content. The
    measurement feeds the adaptive scheduler's tolerance comparison (A2):
    with a measured ``e2e_cloud_ms`` the tolerance is anchored to a real
    cloud round trip, not to the manual sum of ``RTT`` and ``tempo_cloud``.

    Attributes:
        e2e_cloud_ms: End-to-end latency in milliseconds when the probe
            completed; ``None`` when it was skipped or failed.
        ttft_cloud_ms: Optional time-to-first-token when the client exposes
            it. Most OpenAI-compatible clients do not, so this stays
            ``None`` for now.
        simulato: True when no real call was made (offline mode, missing
            credentials, or explicit skip).
        cloud_probe_skipped: True when the probe was not executed (offline,
            no credentials, or failure). ``simulato`` may also be True in
            that case but is reserved for "no real call attempted".
        errore: Provider error code when the call failed; ``None`` when the
            probe completed or was skipped.
    """

    e2e_cloud_ms: float | None = None
    ttft_cloud_ms: float | None = None
    simulato: bool = True
    cloud_probe_skipped: bool = True
    errore: str | None = None


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

    def probe(self) -> RisultatoProbe:
        """Run a one-shot public latency probe of the configured cloud client.

        The probe is the only place where the prototype measures an
        end-to-end cloud round trip before issuing real requests. It uses a
        fixed public prompt (``PROBE_QUERY``) with a tiny completion budget
        (``PROBE_MAX_TOKENS``) and never carries user content. No retry is
        attempted: a single failure is reported as a skipped measurement so
        the scheduler falls back to the manual ``RTT + tempo_cloud`` sum.

        Returns:
            A :class:`RisultatoProbe` describing what was measured, what
            was skipped, and why. The probe never raises.
        """
        if self.offline or (self._client is None and not self.api_key and not self.base_url):
            return RisultatoProbe(
                simulato=True,
                cloud_probe_skipped=True,
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
                client = OpenAI(**client_kwargs)
            else:
                client = self._client
            client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": PROBE_QUERY}],
                max_tokens=PROBE_MAX_TOKENS,
                temperature=0.0,
            )
            latency = time.perf_counter() - t0
            return RisultatoProbe(
                e2e_cloud_ms=latency * 1000.0,
                ttft_cloud_ms=None,
                simulato=False,
                cloud_probe_skipped=False,
            )
        except Exception:
            LOGGER.exception("Probe cloud fallito")
            return RisultatoProbe(
                e2e_cloud_ms=None,
                simulato=False,
                cloud_probe_skipped=True,
                errore="provider_error",
            )
