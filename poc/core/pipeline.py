"""Testable request orchestration; no CLI or hidden document discovery."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from .cloud import CloudGenerator
from .documents import DocumentCorpus
from .engine import LocalNeuralEngine
from .model_config import DEFAULT_LOCAL_MODEL_CONFIG
from .privacy import DEFAULT_DELTA, DP_KSA_Filter
from .scheduler import AdaptiveScheduler


@dataclass(frozen=True)
class RequestConfig:
    epsilon: float = 1.0
    delta: float = DEFAULT_DELTA
    sla_ms: float = 1500.0
    rtt_ms: float = 50.0
    cloud_ms: float = 150.0
    prefill_tps: float = 250.0
    generation_tps: float = 50.0
    prompt_token_budget: int = 1000
    max_tokens: int = DEFAULT_LOCAL_MODEL_CONFIG.max_tokens
    candidates: int = 40
    fixed_n: int | None = None
    r_min_k: int = 1
    r_max_k: int = 10


def run_request(
    query: str,
    corpus: DocumentCorpus,
    config: RequestConfig,
    cloud: CloudGenerator,
    *,
    engine: Any = None,
    engine_options: dict[str, Any] | None = None,
    tracer: Any = None,
    privacy_filter: DP_KSA_Filter | None = None,
) -> dict[str, Any]:
    """Run one request; returned diagnostics are for local experiments only.

    Timed from scheduler entry to final response, including retrieval, privacy
    and lazy model setup. Corpus ingestion and trace flush are separate. Inject
    a preloaded engine for warm measurements. A supplied filter composes across
    requests; a fresh default filter only accounts for this single request.
    """
    if not query.strip() or config.prompt_token_budget < 1 or not 5 <= config.candidates <= 40:
        raise ValueError('Servono query, budget prompt positivo e 5..40 slot pubblici')
    started = time.perf_counter()
    decision = AdaptiveScheduler(max_tokens=config.max_tokens).schedule(
        [config.prompt_token_budget] * config.candidates,
        epsilon_budget=config.epsilon, delta=config.delta,
        latenza_rete_ms=config.rtt_ms, latenza_massima_ms=config.sla_ms,
        tempo_cloud_ms=config.cloud_ms, tok_per_sec_prefill=config.prefill_tps,
        tok_per_sec_generazione=config.generation_tps, fixed_n=config.fixed_n,
    )
    if tracer is not None:
        tracer.avvia_richiesta(query, metadata={'scheduler_inputs': 'public_config'})
        tracer.registra_decisione_scheduler(decision)
    drafts: list[str] = []
    contexts: list[str] = []
    selected_ids: list[str] = []
    setup_ms = 0.0
    edge_ms = 0.0
    privacy_ms = 0.0
    retrieval_ms = 0.0
    completion_tokens = 0
    prefill_estimated_ms = 0.0
    dp = None
    if decision.n_ensemble:
        # Account validation precedes model setup or reading document excerpts.
        filter_ = privacy_filter if privacy_filter is not None else DP_KSA_Filter(
            epsilon=config.epsilon, delta=config.delta, sigma=decision.sigma,
            epsilon_find_best_k=decision.epsilon_find_best_k,
            epsilon_top_k_ptr=decision.epsilon_top_k_ptr,
            r_min_k=config.r_min_k, r_max_k=config.r_max_k,
        )
        filter_.verifica_budget()
        phase = time.perf_counter()
        selected = corpus.retrieve(query, decision.n_ensemble)
        retrieval_ms = (time.perf_counter() - phase) * 1000
        if engine is None and any(not doc.is_padding for doc in selected):
            phase = time.perf_counter()
            engine = LocalNeuralEngine(**(engine_options or {}))
            setup_ms = (time.perf_counter() - phase) * 1000
        phase = time.perf_counter()
        for doc in selected:
            if doc.is_padding:
                drafts.append('')
                continue
            context = engine.limita_contesto(
                doc.context, query, config.prompt_token_budget, config.max_tokens,
            )
            output = engine.genera_bozza(context, query, max_tokens=config.max_tokens)
            drafts.append(output.testo)
            contexts.append(context)
            selected_ids.append(doc.id)
            completion_tokens += output.completion_tokens
            prefill_estimated_ms += output.tempo_prefill_stimato_sec * 1000
        edge_ms = (time.perf_counter() - phase) * 1000
        if tracer is not None:
            tracer.registra_fase_edge(len(contexts), drafts, edge_ms,
                                     completion_tokens / (edge_ms / 1000) if edge_ms else 0.0)
        phase = time.perf_counter()
        dp = filter_.filtra(drafts)
        privacy_ms = (time.perf_counter() - phase) * 1000
        if tracer is not None:
            tracer.registra_fase_privacy(dp)
    keywords = dp.parole_rilasciate if dp else []
    response = cloud.genera(query, keywords, contexts)
    request_ms = (time.perf_counter() - started) * 1000
    trace_url = None
    if tracer is not None:
        trace_url = tracer.registra_fase_cloud(
            response.risposta_testuale, response.byte_trasmessi_dp,
            response.risparmio_percentuale, response.latenza_rete_sec, model=cloud.model,
        )
    return {
        'config': asdict(config), 'decision': asdict(decision),
        'response': response.risposta_testuale, 'provider_error': response.errore,
        'cloud_simulated': response.simulato, 'released_keywords': keywords,
        'ptr_passed': dp.ptr_superato if dp else False,
        'k_hat': dp.k_hat if dp else None,
        'epsilon_consumed': dp.budget_consumato_epsilon if dp else 0.0,
        'delta_consumed': dp.budget_consumato_delta if dp else 0.0,
        'request_ms': request_ms, 'model_setup_ms': setup_ms,
        'retrieval_ms': retrieval_ms, 'edge_ms': edge_ms, 'privacy_ms': privacy_ms,
        'cloud_call_ms': response.latenza_rete_sec * 1000,
        'prefill_estimated_ms': prefill_estimated_ms,
        'sla_violated': request_ms > config.sla_ms,
        'prompt_text_bytes': response.byte_trasmessi_dp,
        'context_text_bytes': response.byte_grezzi_rag,
        'text_saving_percent': response.risparmio_percentuale,
        'local_diagnostics': {'selected_document_ids': selected_ids,
                              'actual_documents': len(contexts)},
        'trace_url': trace_url,
        'account_scope': 'supplied_session' if privacy_filter is not None else 'single_request',
    }
