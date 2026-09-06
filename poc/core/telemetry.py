"""Optional Langfuse tracing for edge, privacy, scheduler, and cloud phases.

Telemetry is deliberately best-effort. By default, trace payloads contain
operational metadata only: no generated drafts, raw histograms, discarded
tokens, user query, or final answer. ``capture_sensitive=True`` enables the
full diagnostic payload for a trusted local/self-hosted Langfuse deployment.

External dependencies:
    ``langfuse`` is imported lazily when both Langfuse credentials exist.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from .privacy import EsitoDP
from .scheduler import DecisioneScheduler

__all__ = ["LangfuseTracer"]

LOGGER = logging.getLogger(__name__)
DEFAULT_LANGFUSE_HOST = "https://cloud.langfuse.com"
DEFAULT_CAPTURE_SENSITIVE = False


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    """Parse a human-readable environment boolean."""

    if raw_value is None:
        return default
    normalized = raw_value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    LOGGER.warning("Valore booleano Langfuse non riconosciuto: %r", raw_value)
    return default


class LangfuseTracer:
    """Manage one optional distributed Langfuse trace.

    Args:
        pk: Optional public key, otherwise ``LANGFUSE_PUBLIC_KEY``.
        sk: Optional secret key, otherwise ``LANGFUSE_SECRET_KEY``.
        host: Optional endpoint, otherwise ``LANGFUSE_HOST``.
        capture_sensitive: Include query, drafts, raw counts, and final
            response in traces. When omitted, ``LANGFUSE_CAPTURE_SENSITIVE``
            is read and defaults to ``False``.
    """

    def __init__(
        self,
        pk: str | None = None,
        sk: str | None = None,
        host: str | None = None,
        capture_sensitive: bool | None = None,
    ) -> None:
        self.public_key = pk or os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = sk or os.environ.get("LANGFUSE_SECRET_KEY")
        self.host = host or os.environ.get("LANGFUSE_HOST", DEFAULT_LANGFUSE_HOST)
        self.capture_sensitive = (
            _parse_bool(
                os.environ.get("LANGFUSE_CAPTURE_SENSITIVE"),
                DEFAULT_CAPTURE_SENSITIVE,
            )
            if capture_sensitive is None
            else capture_sensitive
        )
        self.client: Any = None
        self.current_trace: Any = None
        self._connetti()

    def _connetti(self) -> None:
        """Connect to Langfuse when credentials are configured."""

        if not self.public_key or not self.secret_key:
            return
        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )
            if client.auth_check():
                self.client = client
            else:
                LOGGER.warning("Autenticazione Langfuse fallita; tracing disattivato")
        except Exception:
            LOGGER.exception("Connessione Langfuse fallita; tracing disattivato")

    def _avvia_span(
        self,
        name: str,
        input_data: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> Any:
        """Start a child span with either the v2 or v4 Langfuse API."""

        if hasattr(self.current_trace, "span"):
            return self.current_trace.span(
                name=name,
                input=dict(input_data),
                metadata=dict(metadata),
            )
        return self.current_trace.start_observation(
            name=name,
            as_type="span",
            input=dict(input_data),
            metadata=dict(metadata),
        )

    @property
    def is_active(self) -> bool:
        """Return whether a valid Langfuse client is active."""

        return self.client is not None

    def avvia_richiesta(
        self,
        domanda: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Start a trace for one user request."""

        if not self.is_active:
            return
        trace_input: dict[str, Any] = (
            {"domanda": domanda}
            if self.capture_sensitive
            else {"query_present": bool(domanda)}
        )
        try:
            if hasattr(self.client, "trace"):
                self.current_trace = self.client.trace(
                    name="dp-rag-distributed-request",
                    input=trace_input,
                    metadata=dict(metadata or {}),
                )
            else:
                self.current_trace = self.client.start_observation(
                    name="dp-rag-distributed-request",
                    as_type="span",
                    input=trace_input,
                    metadata=dict(metadata or {}),
                )
        except Exception:
            self.current_trace = None
            LOGGER.exception("Avvio traccia Langfuse fallito; tracing disattivato")

    def registra_decisione_scheduler(self, decisione: DecisioneScheduler) -> None:
        """Record the adaptive scheduler decision as a trace span."""

        if not self.current_trace:
            return
        try:
            span = self._avvia_span(
                "adaptive-ensemble-scheduler",
                {"n_ensemble": decisione.n_ensemble},
                {
                    "sigma": decisione.sigma,
                    "epsilon_find_best_k": decisione.epsilon_find_best_k,
                    "epsilon_top_k_ptr": decisione.epsilon_top_k_ptr,
                    "tempo_stimato_ms": decisione.tempo_stimato_ms,
                    "ptr_pass_rate_attesa": decisione.ptr_pass_rate_attesa,
                    "motivazione": decisione.motivazione,
                },
            )
            span.end()
        except Exception:
            LOGGER.exception("Registrazione scheduler Langfuse fallita")

    def registra_fase_edge(
        self,
        n_documenti: int,
        bozze: list[str],
        durata_ms: float,
        tok_per_sec: float,
    ) -> None:
        """Record local inference metrics and generated drafts."""

        if not self.current_trace:
            return
        try:
            span = self._avvia_span(
                "edge-neural-ensemble",
                {"documenti_elaborati": n_documenti},
                {"durata_ms": durata_ms, "velocita_tok_s": tok_per_sec},
            )
            output: dict[str, Any] = {"bozze_count": len(bozze)}
            if self.capture_sensitive:
                output["bozze_generate"] = bozze
            span.end(output=output)
        except Exception:
            LOGGER.exception("Registrazione fase edge Langfuse fallita")

    def registra_fase_privacy(self, esito: EsitoDP) -> None:
        """Record DP-KSA accounting without sending raw document text."""

        if not self.current_trace:
            return
        metadata: dict[str, Any] = {
            "epsilon_budget": esito.epsilon_budget,
            "delta": esito.delta,
            "sigma": esito.sigma,
            "k_hat": esito.k_hat,
            "ptr_superato": esito.ptr_superato,
            "epsilon_consumato": esito.budget_consumato_epsilon,
            "epsilon_rimasto": esito.epsilon_rimasto,
            "delta_consumato": esito.budget_consumato_delta,
            "numero_invocazione": esito.numero_invocazione,
        }
        span_input: dict[str, Any] = {
            "histogram_size": len(esito.conteggi_reali),
            "released_count": len(esito.parole_rilasciate),
        }
        output = {"termini_rilasciati": esito.parole_rilasciate}
        if self.capture_sensitive:
            span_input["raw_counts"] = esito.conteggi_reali
            metadata.update(
                {
                    "gap_ptr": esito.gap_ptr,
                    "gap_ptr_rumoroso": esito.gap_ptr_rumoroso,
                }
            )
            output["termini_scartati"] = esito.parole_scartate
        try:
            span = self._avvia_span("dp-ksa-filter", span_input, metadata)
            span.end(output=output)
        except Exception:
            LOGGER.exception("Registrazione fase privacy Langfuse fallita")

    def registra_fase_cloud(
        self,
        risposta_finale: str,
        byte_inviati: int,
        risparmio_perc: float,
        latenza_sec: float,
        model: str = "unknown",
    ) -> str | None:
        """Close the cloud span and flush the trace."""

        if not self.current_trace:
            return None
        generation_metadata = {
            "byte_inviati": byte_inviati,
            "risparmio_rete_percentuale": risparmio_perc,
            "latenza_ms": latenza_sec * 1000.0,
        }
        generation_output: str | dict[str, Any] = (
            risposta_finale
            if self.capture_sensitive
            else {"response_chars": len(risposta_finale)}
        )
        try:
            if hasattr(self.current_trace, "generation"):
                generation = self.current_trace.generation(
                    name="cloud-llm-generation",
                    model=model,
                    output=generation_output,
                    metadata=generation_metadata,
                )
            else:
                generation = self.current_trace.start_observation(
                    name="cloud-llm-generation",
                    as_type="generation",
                    model=model,
                    output=generation_output,
                    metadata=generation_metadata,
                )
            generation.end()
            self.current_trace.update(
                output=risposta_finale
                if self.capture_sensitive
                else {"response_chars": len(risposta_finale)}
            )
            if hasattr(self.current_trace, "end"):
                self.current_trace.end()
            self.client.flush()
            if hasattr(self.current_trace, "get_trace_url"):
                return str(self.current_trace.get_trace_url())
            trace_id = getattr(self.current_trace, "trace_id", None)
            return str(self.client.get_trace_url(trace_id=trace_id))
        except Exception:
            LOGGER.exception("Chiusura traccia Langfuse fallita")
            return None
