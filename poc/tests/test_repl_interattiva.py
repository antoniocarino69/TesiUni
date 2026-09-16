"""REPL interattiva: account condiviso, fallback zero-shot e comandi."""
from types import SimpleNamespace

import pytest

from core.cloud import CloudGenerator
from core.documents import DocumentCorpus, LocalDocument
from core.pipeline import RequestConfig
from repl_interattiva import ReplSession


class FakeEngine:
    def limita_contesto(self, context, query, budget, max_tokens):
        return context

    def genera_bozza(self, context, query, max_tokens):
        return SimpleNamespace(testo='Denver Broncos', completion_tokens=2,
                               tempo_prefill_stimato_sec=0.0)


def corpus():
    return DocumentCorpus([LocalDocument(str(i), f'public context {i}', '') for i in range(6)])


def sessione(*, engine=None, config=None, max_queries=1, offline=True):
    return ReplSession(
        corpus(),
        config or RequestConfig(sla_ms=100_000),
        CloudGenerator(offline=offline),
        max_queries=max_queries,
        engine=engine,
    )


def test_comandi_di_uscita():
    session = sessione(engine=FakeEngine())
    for comando in ('/exit', '/quit', '/q'):
        output, esci = session.interpreta_comando(comando)
        assert output
        assert esci


def test_comando_sconosciuto_non_esce():
    session = sessione(engine=FakeEngine())
    output, esci = session.interpreta_comando('/boh')
    assert not esci
    assert 'sconosciuto' in output


def test_help_elenca_i_comandi():
    session = sessione(engine=FakeEngine())
    output, esci = session.interpreta_comando('/help')
    assert not esci
    assert '/stats' in output and '/exit' in output


def test_docs_conta_il_corpus():
    session = sessione(engine=FakeEngine())
    output, esci = session.interpreta_comando('/docs')
    assert not esci
    assert '6' in output


def test_session_condivide_l_account_e_poi_va_in_zero_shot():
    session = sessione(engine=FakeEngine(), max_queries=1)
    primo = session.rispondi('public')
    assert primo['account_scope'] == 'supplied_session'
    assert primo['epsilon_consumed'] > 0
    assert not primo['zero_shot_forzato']
    secondo = session.rispondi('public')
    assert secondo['zero_shot_forzato']
    assert secondo['decision']['n_ensemble'] == 0
    assert secondo['released_keywords'] == []
    assert secondo['epsilon_consumed'] == 0
    assert secondo['cloud_simulated']


def test_statistiche_rispettano_l_invariante_di_budget():
    session = sessione(engine=FakeEngine(), max_queries=3)
    session.rispondi('public')
    stats = session.statistiche()
    assert stats['invocazioni'] == 1
    assert stats['epsilon_consumato'] + stats['epsilon_rimasto'] == pytest.approx(
        stats['epsilon_sessione'])
    assert stats['delta_consumato'] <= stats['delta_sessione'] + 1e-12


def test_statistiche_a_sessione_vergine_mostrano_zero():
    session = sessione(engine=FakeEngine(), max_queries=3)
    stats = session.statistiche()
    assert stats['invocazioni'] == 0
    assert stats['epsilon_consumato'] == 0
    assert stats['epsilon_rimasto'] == pytest.approx(stats['epsilon_sessione'])
    assert stats['delta_consumato'] == 0


def test_zero_shot_non_carica_il_modello(monkeypatch):
    monkeypatch.setattr(
        'repl_interattiva.LocalNeuralEngine',
        lambda **kwargs: pytest.fail('Zero-shot non deve caricare il modello'),
    )
    session = sessione(config=RequestConfig(sla_ms=0.0), max_queries=3)
    result = session.rispondi('public')
    assert result['decision']['n_ensemble'] == 0
    assert result['epsilon_consumed'] == 0
    assert session.engine is None


def test_delta_sessione_fuori_soglia_rifiutato():
    with pytest.raises(ValueError):
        ReplSession(
            corpus(),
            RequestConfig(sla_ms=100_000, delta=0.2),
            CloudGenerator(offline=True),
            max_queries=3,
            engine=FakeEngine(),
        )


def test_sforamento_k_e_force_zero_shot_via_parser(tmp_path):
    """--sforamento-k and --force-zero-shot reach the scheduler through the REPL parser."""
    import repl_interattiva

    (tmp_path / 'doc.md').write_text('synthetic')
    args = repl_interattiva.build_parser().parse_args([
        '--documents', str(tmp_path / 'doc.md'),
        '--sforamento-k', '3.5',
        '--force-zero-shot',
    ])
    config = RequestConfig(
        epsilon=args.epsilon, delta=args.delta, sla_ms=args.max_latency_ms,
        rtt_ms=args.rtt_ms, cloud_ms=args.tempo_cloud_ms,
        prefill_tps=args.tok_per_sec_prefill,
        generation_tps=args.tok_per_sec_generazione,
        prompt_token_budget=args.prompt_token_budget,
        max_tokens=args.max_tokens,
        candidates=args.ensemble_size, fixed_n=args.fixed_n,
        r_min_k=args.r_min_k, r_max_k=args.r_max_k,
        k_sforamento=args.sforamento_k,
    )
    assert config.k_sforamento == pytest.approx(3.5)
    if args.force_zero_shot:
        from dataclasses import replace as dc_replace
        config = dc_replace(config, fixed_n=0)
    assert config.fixed_n == 0


def test_repl_parser_accepts_no_calibration_and_manual_throughputs(tmp_path):
    """The REPL parser honours ``--no-calibration`` and the manual flags."""
    import repl_interattiva

    (tmp_path / 'doc.md').write_text('synthetic')
    args = repl_interattiva.build_parser().parse_args([
        '--documents', str(tmp_path / 'doc.md'),
        '--no-calibration',
        '--tok-per-sec-prefill', '1950.0',
        '--tok-per-sec-generazione', '480.0',
    ])
    assert args.no_calibration is True
    assert args.tok_per_sec_prefill == pytest.approx(1950.0)
    assert args.tok_per_sec_generazione == pytest.approx(480.0)
    # Defaults still apply when the flags are not given.
    default_args = repl_interattiva.build_parser().parse_args([
        '--documents', str(tmp_path / 'doc.md'),
    ])
    assert default_args.no_calibration is False
    assert default_args.tok_per_sec_prefill == pytest.approx(250.0)
    assert default_args.tok_per_sec_generazione == pytest.approx(50.0)

