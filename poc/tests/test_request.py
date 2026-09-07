"""Offline orchestration regressions, with no model downloads or credentials."""
from types import SimpleNamespace

import pytest

from core.cloud import CloudGenerator
from core.documents import DocumentCorpus, LocalDocument
from core.pipeline import RequestConfig, run_request


class FakeEngine:
    def __init__(self):
        self.contexts = []

    def limita_contesto(self, context, query, budget, max_tokens):
        return context

    def genera_bozza(self, context, query, max_tokens):
        self.contexts.append(context)
        return SimpleNamespace(testo='Denver Broncos', completion_tokens=2,
                               tempo_prefill_stimato_sec=0.0)


def corpus():
    return DocumentCorpus([LocalDocument(str(i), f'public context {i}', '') for i in range(6)])


def test_impossible_sla_skips_retrieval_and_engine(monkeypatch):
    data = corpus()
    monkeypatch.setattr(data, 'retrieve', lambda *args: pytest.fail('No retrieval on zero-shot'))
    result = run_request('public query', data, RequestConfig(), CloudGenerator(offline=True))
    assert result['decision']['n_ensemble'] == 0
    assert result['model_setup_ms'] == 0
    assert result['epsilon_consumed'] == result['delta_consumed'] == 0
    assert result['cloud_simulated']


def test_public_schedule_independent_of_document_lengths_and_count():
    engine = FakeEngine()
    config = RequestConfig(sla_ms=100_000)
    a = run_request('public', corpus(), config, CloudGenerator(offline=True), engine=engine)
    b = run_request('public', DocumentCorpus([LocalDocument('long', 'public ' * 5000, '')]),
                    config, CloudGenerator(offline=True), engine=engine)
    assert a['decision'] == b['decision']
    assert a['decision']['n_ensemble'] == 21
    assert a['local_diagnostics']['actual_documents'] == 6
    assert b['local_diagnostics']['actual_documents'] == 1
    assert len(engine.contexts) == 7
    assert a['request_ms'] >= a['edge_ms'] + a['privacy_ms']


def test_cli_dry_run_requires_no_model_provider_or_tracer(tmp_path, monkeypatch):
    import run_pipeline
    path = tmp_path / 'document.md'
    path.write_text('synthetic test text')
    monkeypatch.setattr(run_pipeline, 'LangfuseTracer', lambda **kwargs: pytest.fail('No trace'))
    assert run_pipeline.main(['--documents', str(path), '--query', 'text', '--dry-run']) == 0
    with pytest.raises(SystemExit):
        run_pipeline.main(['--documents', str(path), '--dry-run'])


def test_experiment_composes_and_marks_simulated_quality():
    from benchmark_scheduler import run_experiment
    report = run_experiment([{'query': 'public', 'references': ['Denver Broncos']}], corpus(),
                            RequestConfig(sla_ms=100_000), CloudGenerator(offline=True),
                            FakeEngine(), fixed_sizes=[5], repeats=2)
    assert len(report['runs']) == 4
    assert report['cumulative_delta'] == pytest.approx(5e-4)
    assert all(row['quality'] is None for row in report['runs'])
    assert report['summary']['adaptive']['runs'] == 2


def test_answer_scores_compare_reference_tokens():
    from benchmark_scheduler import answer_scores
    assert answer_scores('Denver Broncos!', ['denver broncos']) == {'exact_match': 1., 'token_f1': 1.}
    assert answer_scores('Denver', ['Denver Broncos'])['token_f1'] == pytest.approx(2 / 3)


def test_exhausted_session_stops_before_more_local_inference():
    from core.privacy import DP_KSA_Filter, DPBudgetExhaustedError
    engine = FakeEngine()
    account = DP_KSA_Filter(epsilon=1.0)
    config = RequestConfig(sla_ms=100_000)
    run_request('public', corpus(), config, CloudGenerator(offline=True),
                engine=engine, privacy_filter=account)
    processed = len(engine.contexts)
    with pytest.raises(DPBudgetExhaustedError):
        run_request('public', corpus(), config, CloudGenerator(offline=True),
                    engine=engine, privacy_filter=account)
    assert len(engine.contexts) == processed
