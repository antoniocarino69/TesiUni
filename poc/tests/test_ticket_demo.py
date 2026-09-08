"""Ticket-level fixtures, procedure coverage and sensitivity diagnostics."""
import json
from collections import Counter
from types import SimpleNamespace

from benchmark_salary_demo import verify_corpus
from benchmark_ticket_demo import (
    conditional_trials,
    lexical_step_matches,
    sensitive_token_sets,
    synthesize_locally,
)
from scripts.create_ticket_demo import build_demo, write_demo


def test_corpus_has_independent_e42_tickets_and_explicit_repeated_customer(tmp_path):
    write_demo(tmp_path)
    corpus, manifest = verify_corpus(tmp_path)
    assert len(corpus.documents) == 80
    assert Counter(row['error'] for row in manifest['documents']) == {'E42': 48, 'E17': 16, 'E55': 16}
    assert max(Counter(row['customer_id'] for row in manifest['documents']).values()) == 10
    cases = json.loads((tmp_path / 'cases.json').read_text())
    records = {str(tmp_path / row['path']): row for row in manifest['documents']}
    for case in cases[:3]:
        selected = corpus.retrieve(case['query'], 40)
        assert all(records[doc.source]['error'] == 'E42' for doc in selected)
        assert len({records[doc.source]['customer_id'] for doc in selected}) == 40


def test_canaries_are_counted_per_ticket_and_shared_details_are_not_unique():
    manifest = json.loads(build_demo()['manifest.json'])
    sensitive, unique = sensitive_token_sets(manifest)
    assert 'privatoe42001' in unique
    assert 'clientefittizioe42001' in unique  # also in domain, still ONE ticket
    assert 'clusterinternoaurora' in sensitive - unique
    assert 'clienteripetuto' in sensitive - unique
    assert '192' in sensitive  # exposes that IP normalization is fragment-level


def test_cache_step_requires_both_action_and_object():
    steps = json.loads(build_demo()['cases.json'])[0]['step_groups']
    assert not lexical_step_matches(['cache'], steps)['clear_cache']
    assert not lexical_step_matches(['cancellare'], steps)['clear_cache']
    matches = lexical_step_matches(['arrestare', 'cancellare', 'cache', 'riavviare'], steps)
    assert all(matches.values())


def test_keyword_synthesis_cannot_see_original_ticket_and_abstains_without_release():
    class Sink:
        def genera_bozza(self, context, query):
            self.context = context
            return SimpleNamespace(testo='Cancellare la cache.', durata_totale_sec=0.01)
    engine = Sink()
    empty = synthesize_locally(engine, 'query', [])
    assert empty['inference_ms'] == 0
    assert not hasattr(engine, 'context')
    result = synthesize_locally(engine, 'query', ['cache', 'cancellare', 'cache'])
    assert engine.context == 'Keyword disponibili: cache, cancellare'
    assert result['input_keywords'] == ['cache', 'cancellare']


def test_dp_does_not_semantically_redact_a_shared_internal_identifier():
    case = {'step_groups': {}}
    rows = conditional_trials(['clusterinternoaurora'] * 40, case,
                              {'clusterinternoaurora'}, set(), trials=200, epsilons=(8.0,))
    assert rows[-1]['shared_identifier_rate'] > 0.9
    assert rows[-1]['unique_identifier_rate'] == 0


def test_ticket_specific_canaries_do_not_gain_false_consensus():
    drafts = [f'privatoticket{i:03}' for i in range(40)]
    rows = conditional_trials(drafts, {'step_groups': {}}, set(drafts), set(drafts),
                              trials=200, epsilons=(8.0,))
    # Empirical regression with fixed public test seed, not a proof of zero leakage.
    assert all(row['unique_identifier_rate'] < 0.02 for row in rows)
