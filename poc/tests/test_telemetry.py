"""Tests for the Langfuse payload privacy policy."""

from __future__ import annotations

from types import SimpleNamespace

from core.telemetry import LangfuseTracer


class _FakeSpan:
    def __init__(self) -> None:
        self.ended_output: object = None

    def end(self, output: object = None) -> None:
        self.ended_output = output


class _FakeTrace:
    def __init__(self) -> None:
        self.input: object = None
        self.spans: list[_FakeSpan] = []
        self.generation_output: object = None
        self.updated_output: object = None

    def span(self, **kwargs: object) -> _FakeSpan:
        span = _FakeSpan()
        span.input = kwargs.get("input")  # type: ignore[attr-defined]
        span.metadata = kwargs.get("metadata")  # type: ignore[attr-defined]
        self.spans.append(span)
        return span

    def generation(self, **kwargs: object) -> _FakeSpan:
        generation = _FakeSpan()
        self.generation_output = kwargs.get("output")
        self.spans.append(generation)
        return generation

    def update(self, **kwargs: object) -> None:
        self.updated_output = kwargs.get("output")

    def get_trace_url(self) -> str:
        return "http://langfuse.local/trace/test"


class _FakeClient:
    def __init__(self, trace: _FakeTrace) -> None:
        self.trace_result = trace

    def trace(self, **kwargs: object) -> _FakeTrace:
        self.trace_result.input = kwargs.get("input")
        return self.trace_result

    def flush(self) -> None:
        return None


class _FakeV4Observation:
    def __init__(self) -> None:
        self.trace_id = "trace-v4"
        self.observations: list[_FakeSpan] = []
        self.ended = False

    def start_observation(self, **kwargs: object) -> _FakeSpan:
        observation = _FakeSpan()
        observation.input = kwargs.get("input")  # type: ignore[attr-defined]
        observation.metadata = kwargs.get("metadata")  # type: ignore[attr-defined]
        self.observations.append(observation)
        return observation

    def update(self, **kwargs: object) -> None:
        self.updated_output = kwargs.get("output")  # type: ignore[attr-defined]

    def end(self) -> None:
        self.ended = True


class _FakeV4Client:
    def __init__(self) -> None:
        self.trace_result = _FakeV4Observation()

    def start_observation(self, **kwargs: object) -> _FakeV4Observation:
        del kwargs
        return self.trace_result

    def get_trace_url(self, *, trace_id: str) -> str:
        return f"http://langfuse.local/trace/{trace_id}"

    def flush(self) -> None:
        return None


class _FailingTrace(_FakeTrace):
    def span(self, **kwargs: object) -> _FakeSpan:
        del kwargs
        raise RuntimeError("telemetry span unavailable")

    def generation(self, **kwargs: object) -> _FakeSpan:
        del kwargs
        raise RuntimeError("telemetry generation unavailable")


def _esito() -> SimpleNamespace:
    return SimpleNamespace(
        conteggi_reali={"segreto": 5},
        parole_rilasciate=["segreto"],
        parole_scartate=["altro"],
        epsilon_budget=1.0,
        delta=1e-4,
        sigma=2.0,
        k_hat=1,
        gap_ptr=3.0,
        gap_ptr_rumoroso=2.5,
        ptr_superato=True,
        budget_consumato_epsilon=0.7,
        epsilon_rimasto=0.3,
        budget_consumato_delta=2e-4,
        numero_invocazione=1,
    )


def _tracer(capture_sensitive: bool) -> tuple[LangfuseTracer, _FakeTrace]:
    trace = _FakeTrace()
    tracer = LangfuseTracer.__new__(LangfuseTracer)
    tracer.client = _FakeClient(trace)
    tracer.current_trace = None
    tracer.capture_sensitive = capture_sensitive
    return tracer, trace


def test_telemetry_redacts_sensitive_payloads_by_default() -> None:
    tracer, trace = _tracer(capture_sensitive=False)
    tracer.avvia_richiesta("domanda riservata")
    tracer.registra_fase_edge(1, ["bozza riservata"], 10.0, 2.0)
    tracer.registra_fase_privacy(_esito())
    tracer.registra_fase_cloud("risposta riservata", 10, 20.0, 0.2, model="local")

    assert trace.input == {"query_present": True}
    edge_span = trace.spans[0]
    privacy_span = trace.spans[1]
    assert "bozze_generate" not in edge_span.ended_output
    assert "raw_counts" not in privacy_span.input
    assert "termini_scartati" not in privacy_span.ended_output
    assert trace.generation_output == {"response_chars": len("risposta riservata")}
    assert trace.updated_output == {"response_chars": len("risposta riservata")}


def test_telemetry_can_capture_sensitive_payloads_for_trusted_local_deployment() -> None:
    tracer, trace = _tracer(capture_sensitive=True)
    tracer.avvia_richiesta("domanda riservata")
    tracer.registra_fase_edge(1, ["bozza riservata"], 10.0, 2.0)
    tracer.registra_fase_privacy(_esito())
    tracer.registra_fase_cloud("risposta riservata", 10, 20.0, 0.2, model="local")

    assert trace.input == {"domanda": "domanda riservata"}
    assert trace.spans[0].ended_output == {
        "bozze_count": 1,
        "bozze_generate": ["bozza riservata"],
    }
    assert trace.spans[1].input["raw_counts"] == {"segreto": 5}
    assert trace.spans[1].ended_output["termini_scartati"] == ["altro"]
    assert trace.generation_output == "risposta riservata"


def test_telemetry_failures_never_escape_the_pipeline() -> None:
    trace = _FailingTrace()
    tracer = LangfuseTracer.__new__(LangfuseTracer)
    tracer.client = _FakeClient(trace)
    tracer.current_trace = trace
    tracer.capture_sensitive = False

    tracer.registra_fase_edge(1, ["bozza"], 1.0, 1.0)
    tracer.registra_fase_privacy(_esito())
    assert tracer.registra_fase_cloud("risposta", 1, 1.0, 0.1) is None


def test_telemetry_supports_langfuse_v4_observations() -> None:
    client = _FakeV4Client()
    tracer = LangfuseTracer.__new__(LangfuseTracer)
    tracer.client = client
    tracer.current_trace = None
    tracer.capture_sensitive = False

    tracer.avvia_richiesta("domanda")
    tracer.registra_decisione_scheduler(
        SimpleNamespace(
            n_ensemble=5,
            sigma=2.0,
            epsilon_find_best_k=0.5,
            epsilon_top_k_ptr=0.5,
            tempo_stimato_ms=100.0,
            ptr_pass_rate_attesa=0.5,
            motivazione="test",
        )
    )
    trace_url = tracer.registra_fase_cloud("risposta", 1, 1.0, 0.1)

    assert trace_url == "http://langfuse.local/trace/trace-v4"
    assert client.trace_result.ended
