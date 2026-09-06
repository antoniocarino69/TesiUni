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
