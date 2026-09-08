"""Public synthetic payroll fixtures and local diagnostic protocol."""
import json

import pytest

from benchmark_salary_demo import contains_reference, release_trials, verify_corpus
from scripts.create_salary_demo import build_demo, write_demo


def test_salary_documents_are_unique_and_query_retrieval_selects_department(tmp_path):
    write_demo(tmp_path)
    corpus, manifest = verify_corpus(tmp_path)
    assert len(corpus.documents) == 80
    assert corpus.duplicates_removed == 0
    rows = {str(tmp_path / row['path']): row for row in manifest['documents']}
    cases = json.loads((tmp_path / 'cases.json').read_text())
    for case in cases[:3]:
        selected = corpus.retrieve(case['query'], case['relevant_documents'])
        assert all(rows[item.source]['department'] == case['department'] for item in selected)
        assert all(str(rows[item.source]['base_salary_eur']) == case['target_token']
                   for item in selected)
    assert len({row['bonus_eur'] for row in rows.values()}) > 1


def test_demo_regeneration_is_reproducible_and_preserves_manual_edits(tmp_path):
    assert build_demo() == build_demo()
    write_demo(tmp_path)
    write_demo(tmp_path)
    changed = tmp_path / 'documenti' / 'DEMO-T001.md'
    changed.write_text('manual change')
    with pytest.raises(ValueError, match='non sovrascritto'):
        write_demo(tmp_path)
    assert changed.read_text() == 'manual change'
    with pytest.raises(ValueError, match='modificato'):
        verify_corpus(tmp_path)


def test_salary_runner_rejects_other_documents_in_demo_folder(tmp_path):
    write_demo(tmp_path)
    (tmp_path / 'documenti' / 'extra.md').write_text('extra synthetic document')
    with pytest.raises(ValueError, match='aggiunti'):
        verify_corpus(tmp_path)


def test_amount_coverage_matches_full_numbers_not_substrings():
    assert contains_reference('Lo stipendio è 42000 euro.', ['42000'])
    assert not contains_reference('142000 euro', ['42000'])
    assert not contains_reference('420000 euro', ['42000'])
    assert contains_reference('Non disponibile.', ['non disponibile'])


def test_diagnostic_trials_recover_consistent_target_with_sufficient_redundancy():
    rows = release_trials(['42000 euro'] * 40, '42000', trials=200, epsilons=(8.0,))
    by_n = {row['n']: row for row in rows}
    assert by_n[40]['target_recovery_rate'] > 0.9
    assert by_n[5]['target_recovery_rate'] < 0.5
    assert by_n[40]['target_count_in_histogram'] == 40
    assert all(row['delta_per_trial'] == 2e-4 for row in rows)
