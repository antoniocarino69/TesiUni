"""Tests for the OpenAI-compatible cloud adapter."""

from __future__ import annotations

from types import SimpleNamespace

from core.cloud import CloudGenerator


class _FakeCompletions:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def test_cloud_adapter_supports_generic_openai_compatible_models() -> None:
    completions = _FakeCompletions(
        response=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" risposta "))]
        )
    )
    generator = CloudGenerator(
        base_url="http://localhost:8000/v1",
        model="local-instruct",
        client=_FakeClient(completions),
    )

    result = generator.genera("domanda", ["alpha"], ["contesto locale"])

    assert result.risposta_testuale == "risposta"
    assert result.errore is None
    assert completions.kwargs is not None
    assert completions.kwargs["model"] == "local-instruct"
    assert completions.kwargs["max_tokens"] == 1024


def test_cloud_empty_provider_response_is_explicit() -> None:
    completions = _FakeCompletions(
        response=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None),
                    finish_reason="length",
                )
            ]
        )
    )
    generator = CloudGenerator(client=_FakeClient(completions))

    result = generator.genera("domanda", ["alpha"], ["contesto locale"])

    assert result.errore == "empty_response"
    assert result.risposta_testuale.startswith("Errore API Cloud:")


def test_cloud_provider_failure_is_structured_without_exposing_exception() -> None:
    completions = _FakeCompletions(error=RuntimeError("secret provider detail"))
    generator = CloudGenerator(client=_FakeClient(completions))

    result = generator.genera("domanda", ["alpha"], ["contesto locale"])

    assert result.errore == "provider_error"
    assert result.risposta_testuale == "Errore API Cloud: impossibile completare la richiesta."
    assert "secret provider detail" not in result.risposta_testuale


def test_explicit_offline_overrides_credentials_and_never_calls_client():
    class ForbiddenClient:
        @property
        def chat(self):
            raise AssertionError('provider must not be called')
    result = CloudGenerator(api_key='synthetic', client=ForbiddenClient(), offline=True).genera(
        'query', [], [],
    )
    assert result.simulato
    assert result.latenza_rete_sec == 0.0


# ---------------------------------------------------------------------------
# Cloud probe (A1)
# ---------------------------------------------------------------------------


def test_probe_returns_latency_when_credentials_and_endpoint_are_configured():
    completions = _FakeCompletions(
        response=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="four"))]
        )
    )
    generator = CloudGenerator(
        base_url="http://localhost:8000/v1",
        model="local-instruct",
        client=_FakeClient(completions),
    )

    result = generator.probe()

    assert result.simulato is False
    assert result.errore is None
    assert result.e2e_cloud_ms is not None
    assert result.e2e_cloud_ms >= 0.0
    # Probe must be a real call: the fake client recorded the kwargs.
    assert completions.kwargs is not None
    assert completions.kwargs["model"] == "local-instruct"
    # The probe prompt must not carry any private content; it is a public
    # sanity question whose answer is irrelevant to the user workload.
    messages = completions.kwargs["messages"]
    assert any("public" in str(m["content"]).lower() for m in messages)
    # Max tokens capped to keep the probe cheap.
    assert completions.kwargs["max_tokens"] <= 16


def test_probe_is_skipped_when_offline():
    generator = CloudGenerator(
        api_key="synthetic", base_url="http://localhost:8000/v1", offline=True
    )
    result = generator.probe()
    assert result.simulato is True
    assert result.cloud_probe_skipped is True
    assert result.e2e_cloud_ms is None
    assert result.errore is None


def test_probe_is_skipped_without_credentials_or_endpoint(monkeypatch):
    # No api_key, no base_url, no client -> nothing to call. Strip any
    # credentials that may have been loaded by a prior test (e.g. via
    # dotenv during a CLI integration test).
    for name in ("CLOUD_API_KEY", "OPENAI_API_KEY", "CLOUD_BASE_URL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    generator = CloudGenerator()
    result = generator.probe()
    assert result.simulato is True
    assert result.cloud_probe_skipped is True
    assert result.e2e_cloud_ms is None


def test_probe_records_failure_without_raising():
    completions = _FakeCompletions(error=RuntimeError("upstream down"))
    generator = CloudGenerator(
        base_url="http://localhost:8000/v1",
        client=_FakeClient(completions),
    )
    result = generator.probe()
    assert result.simulato is False
    assert result.cloud_probe_skipped is True  # failure counts as "no measurement"
    assert result.e2e_cloud_ms is None
    assert result.errore == "provider_error"


def test_probe_does_not_retry_on_failure():
    """A single failed call must not trigger a second one (PIANO A1: no retry)."""
    calls = {"count": 0}

    class CountingCompletions:
        def create(self, **kwargs):
            calls["count"] += 1
            raise RuntimeError("upstream down")

    class CountingClient:
        chat = SimpleNamespace(completions=CountingCompletions())

    generator = CloudGenerator(
        base_url="http://localhost:8000/v1",
        client=CountingClient(),
    )
    generator.probe()
    assert calls["count"] == 1
