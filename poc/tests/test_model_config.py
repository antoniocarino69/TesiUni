"""Tests for the shared local inference workload configuration."""

from __future__ import annotations

import pytest

from core.model_config import costruisci_prompt, stima_tempo_prefill


def test_engine_and_benchmark_prompt_contract_is_single_source() -> None:
    prompt = costruisci_prompt("context", "question")

    assert "Context:\ncontext" in prompt
    assert "Question: question" in prompt
    assert prompt.endswith("<|im_start|>assistant\n")


def test_prefill_estimate_handles_empty_usage_without_division_by_zero() -> None:
    assert stima_tempo_prefill(1.0, 0, 0) == 0.0
    assert stima_tempo_prefill(2.0, 100, 10) == pytest.approx(2.0 * 100 / 140)
