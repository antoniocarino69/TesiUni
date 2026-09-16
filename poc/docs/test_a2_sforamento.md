# Test della soglia di sforamento SLA (A2)

Catalogo dei test che verificano la policy A2 — tolleranza sullo sforamento
previsto del piano minimo — in tutte le sue forme: libreria, integrazione
pipeline, integrazione CLI. Tutti i test sono eseguibili offline, senza
modello GGUF né provider reale.
## Come consultarli

```bash
# Solo i test della policy A2 (filtra per parola chiave)
cd poc
.venv/bin/python -m pytest -v -k "sforamento or force_zero or tolerance or impossible"

# Lista completa con percorsi (per annotazioni o IDE)
.venv/bin/python -m pytest --collect-only -q -k "sforamento or force_zero or tolerance or impossible"

# Un solo test specifico
.venv/bin/python -m pytest -v tests/test_scheduler.py::test_accepted_overrun_is_declared_as_an_estimate
```

## Mappa dei test

### Logica dello scheduler (`tests/test_scheduler.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_sforamento_k_zero_reproduces_conservative_behavior` | Default `k=0` con SLA infeasibile → `N=0` |
| `test_sforamento_k_positive_accepts_small_overrun` | `k>0` con sforamento entro tolleranza → `N=N_MIN`, `sforamento_accettato=True` |
| `test_sforamento_k_positive_but_insufficient_still_zero_shot` | `k>0` con sforamento oltre tolleranza → `N=0` |
| `test_fixed_baseline_does_not_apply_sforamento_policy` | `--fixed-n` non applica mai la policy di tolleranza |
| `test_sforamento_previsto_describes_the_executed_plan` | `sforamento_previsto_ms` descrive il piano eseguito, non solo quello candidato |
| `test_force_zero_shot_is_explicit_and_bypasses_tolerance` | `fixed_n=0` è il percorso esplicito verso `N=0`, salta la tolleranza |
| `test_accepted_overrun_is_declared_as_an_estimate` | Sforamento accettato dichiarato come stima, non come scadenza |
| `test_tolerance_does_not_change_a_plan_that_already_fits` | `k>0` non altera un piano che già rientra nello SLA |
| `test_k_sforamento_is_validated` | `k_sforamento` rifiuta valori non finiti o negativi |
| `test_tolerance_requires_enough_candidates` | La libreria rifiuta input con meno di `N_MIN` slot |
| `test_accepted_overrun_message_does_not_claim_infeasibility` | Messaggio "SLA non fattibile" omesso quando lo sforamento è accettato |

### Integrazione pipeline (`tests/test_request.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_impossible_sla_with_tolerance_runs_retrieval_and_engine` | Pipeline con `k>0` esegue retrieval+filtro anche con SLA infeasibile |
| `test_impossible_sla_with_k_zero_skips_retrieval_and_engine` | Pipeline con `k=0` salta retrieval+filtro (default conservativo) |
| `test_force_zero_shot_skips_retrieval_even_with_a_roomy_sla` | `fixed_n=0` salta retrieval+filtro anche con SLA abbondante |

### Integrazione REPL (`tests/test_repl_interattiva.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_sforamento_k_e_force_zero_shot_via_parser` | `--sforamento-k` e `--force-zero-shot` raggiungono lo scheduler dalla CLI REPL |

### Integrazione CLI end-to-end (`tests/test_pipeline_integration.py`)

Questi test invocano `run_pipeline.main(argv)` come fa un utente dalla shell,
rileggono il JSON di output e verificano i campi della decisione. Lo stub
dell'engine locale evita il download del modello GGUF.

| Test | Cosa verifica |
| --- | --- |
| `test_cli_dry_run_with_k_zero_reports_zero_shot` | `run_pipeline.py --dry-run` con `k=0` esce con `N=0` e `sforamento_accettato=False` |
| `test_cli_full_run_with_high_k_reports_accepted_overrun` | `run_pipeline.py` con `k=10` produce JSON con `N=5`, `sforamento_accettato=True`, `tolleranza_sforamento_ms=15500` |
| `test_cli_full_run_with_force_zero_shot_overrides_tolerance` | `run_pipeline.py --force-zero-shot` con `k>0` produce JSON con `N=0` e motivazione "Zero-shot forzato" |
| `test_cli_dry_run_rejects_invalid_k` | `run_pipeline.py --sforamento-k nan|inf|-1.5` esce con codice 2 (argparse) |

## Comandi di riferimento (CLI reale)

Per riprodurre manualmente ciò che i test di integrazione CLI verificano:

```bash
cd poc

# Default conservativo (k=0)
.venv/bin/python run_pipeline.py --documents /tmp/doc.md --query "q" \
  --max-latency-ms 1500 --rtt-ms 1400 --tempo-cloud-ms 150 \
  --dry-run --no-calibration

# Tolleranza attiva (k=10)
.venv/bin/python run_pipeline.py --documents /tmp/doc.md --query "q" \
  --ensemble-size 5 --prompt-token-budget 256 \
  --max-latency-ms 1500 --rtt-ms 1400 --tempo-cloud-ms 150 \
  --sforamento-k 10.0 --no-calibration --offline-cloud --no-telemetry \
  --output /tmp/report.json

# Zero-shot forzato
.venv/bin/python run_pipeline.py --documents /tmp/doc.md --query "q" \
  --sforamento-k 10.0 --force-zero-shot \
  --dry-run --no-calibration

# Validazione k invalido
.venv/bin/python run_pipeline.py --documents /tmp/doc.md --query "q" \
  --dry-run --sforamento-k nan
# atteso: exit code 2, "argument --sforamento-k: Il valore deve essere finito e non negativo"
```

## Numeri di riferimento

Con `RTT=1400`, `cloud=150`, `prompt_budget=256`, `ensemble=5`,
`max_tokens=30`, throughput default `250/50 tok/s`:

- Latenza locale per inferenza: `256/250*1000 + 30/50*1000 = 1624 ms`
- 5 inferenze in serie: `8120 ms`
- `E2E_cloud_ms` = `1400 + 150` = `1550 ms`
- Stima totale per `N_MIN`: `1550 + 8120 = 9670 ms`
- Sforamento previsto (SLA 1500): `9670 − 1500 = 8170 ms`

| `k` | Tolleranza (ms) | Decisione |
| ---: | ---: | --- |
| 0 | 0 | `N=0` (default conservativo) |
| 0.1 | 155 | `N=0` (oltre tolleranza) |
| 1 | 1550 | `N=0` (oltre tolleranza) |
| 3 | 4650 | `N=0` (oltre tolleranza) |
| 10 | 15500 | `N=5` accettato |

## Stato al merge di A2

- ruff: pulito
- pytest: 120 passed (5 nuovi rispetto al merge)
- copertura `core.scheduler`: ≥ 90%

# Test delle etichette sperimentali (A3)

Le etichette A3 (`insufficienti`, `errore`, `completo`, `degradato`) sono
calcolate a posteriori in `core/etichette.py` su `(decisione, dp, risposta)`.
La variante stretta per ticket richiede `riferimenti_ticket` nel
`RequestConfig`.

## Comandi

```bash
# Solo i test delle etichette
cd poc
.venv/bin/python -m pytest -v tests/test_etichette.py

# Integrazione CLI
.venv/bin/python -m pytest -v tests/test_pipeline_integration.py -k esito
```

## Mappa dei test

### Logica di classificazione (`tests/test_etichette.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_insufficienti_quando_il_filtro_non_rilascia_parole` | Lista keyword vuota → `insufficienti` |
| `test_errore_quando_il_provider_fallisce` | `risposta.errore != None` → `errore` |
| `test_errore_quando_la_risposta_e_vuota` | `risposta_testuale == ""` → `errore` |
| `test_completo_quando_la_risposta_riusa_le_keyword` | Keyword rilasciata presente nel testo → `completo` |
| `test_completo_non_scattato_da_pattern_di_astensione` | Pattern "non lo so", "informazioni insufficienti", ecc. → `degradato` |
| `test_pattern_astensione_noti[*]` | Pattern multilingue (italiano + inglese) |
| `test_degradato_quando_rilascio_non_riusato` | Keyword rilasciate ma assenti nella risposta → `degradato` |
| `test_ticket_completo_con_passaggi_in_ordine` | Tutti i passaggi attesi presenti nell'ordine giusto → `completo` |
| `test_ticket_degradato_se_passaggi_mancano` | Passaggi mancanti → `degradato` |
| `test_ticket_degradato_se_ordine_sbagliato` | Passaggi presenti ma in ordine diverso → `degradato` |
| `test_insufficienti_ha_priorita_su_errore_per_il_caso_zero_shot` | Zero-shot è osservazione di rilascio, non di provider |
| `test_esito_e_serializzabile_in_json` | `EsitoRisultato.to_dict()` è JSON-safe |
| `test_riferimento_vuoto_non_alza_il_livello_di_rigor` | Senza `riferimenti_ticket` vale solo l'euristica generica |

### Integrazione CLI (`tests/test_pipeline_integration.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_cli_full_run_attaches_esito_label` | Il campo `esito` compare nel JSON di output con label valida e motivazione |
| `test_cli_full_run_no_etichette_disables_label` | `--no-etichette` registra `motivazione="etichette disattivate via CLI"` |

## Comandi di riferimento (CLI reale)

```bash
cd poc

# Default con etichetta
.venv/bin/python run_pipeline.py --documents docs/ticket_demo/documenti \
  --query "Come si risolve l'errore E42?" --offline-cloud --no-calibration \
  --output reports/a3_smoke.json
# atteso: report con esito.label ∈ {insufficienti, errore, completo, degradato}

# Etichette disattivate
.venv/bin/python run_pipeline.py --documents docs/ticket_demo/documenti \
  --query "Come si risolve l'errore E42?" --offline-cloud --no-calibration \
  --no-etichette --output reports/a3_smoke_disabled.json
# atteso: esito.motivazione == "etichette disattivate via CLI"
```

## Stato al merge di A3

- ruff: pulito
- pytest: 148 passed (17 nuovi `test_etichette.py` + 2 integrazione CLI)
- `core/etichette.py`: modulo nuovo, indipendente dal resto, 0 dipendenze pesanti

# Test della telemetria hardware (A5)

I test coprono sia il modulo `core/telemetry_hw` (snapshot e sampler)
sia l'integrazione nella CLI, REPL e benchmark.

## Comandi

```bash
cd poc
.venv/bin/python -m pytest -v tests/test_telemetry_hw.py
.venv/bin/python -m pytest -v tests/test_engine_runtime.py
.venv/bin/python -m pytest -v tests/test_pipeline_integration.py -k "hw_metrics"
.venv/bin/python -m pytest -v tests/test_benchmark_scheduler.py -k "hw_metrics"
```

## Mappa dei test

### Modulo hardware (`tests/test_telemetry_hw.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_is_platform_supported_recognises_current_host` | macOS / Linux riconosciuti; altre piattaforme no |
| `test_snapshot_returns_a_complete_dataclass` | Tutti i 12 campi sono presenti, anche come `None` |
| `test_snapshot_returns_floats_or_none` | I valori non-`None` sono `float`, non solleva eccezioni |
| `test_sampler_rejects_non_positive_period` | Validazione del periodo |
| `test_sampler_with_zero_seconds_returns_empty_list` | Finestra zero → lista vuota |
| `test_sampler_collects_at_least_two_snapshots_over_a_short_window` | Finestra 0.3 s con periodo 0.1 s → almeno 2 snapshot |
| `test_sampler_collects_exactly_one_snapshot_on_instant_window` | Finestra 0 s → lista vuota |
| `test_snapshot_is_json_serialisable` | `to_dict()` sopravvive a `json.dumps`/`loads` |
| `test_run_helper_handles_missing_tool` | `_run` ritorna stringa vuota se tool manca |
| `test_first_float_returns_none_on_garbage` | `_first_float` tollera input malformato |
| `test_first_float_extracts_first_match` | `_first_float` cattura il primo match |

### TTFT locale reale (`tests/test_engine_runtime.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_genera_bozza_misura_ttft_dal_primo_chunk` | Il primo chunk imposta `tempo_prefill_reale_sec` ≥ delay configurato |
| `test_genera_bozza_testo_vuoto_cade_su_none` | Nessun chunk → `tempo_prefill_reale_sec` = None |
| `test_genera_bozza_completion_tokens_da_fallback_quando_stream_non_emettono_usage` | Fallback non-streaming quando lo stream omette `usage` |
| `test_genera_bozza_rifiuta_max_tokens_non_positivo` | Validazione input |

### Integrazione CLI (`tests/test_pipeline_integration.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_cli_hw_metrics_adds_before_after_snapshots` | `--hw-metrics` scrive `hw_before` e `hw_after` nel JSON |
| `test_cli_without_hw_metrics_omits_hardware_fields` | Default non include campi hardware |

### Integrazione benchmark (`tests/test_benchmark_scheduler.py`)

| Test | Cosa verifica |
| --- | --- |
| `test_hw_metrics_attach_snapshot_to_each_row` | `--hw-metrics` aggiunge `hw_before` a ogni riga del report |

## Comandi di riferimento (CLI reale)

```bash
cd poc

# Snapshot istantanei
.venv/bin/python run_pipeline.py --documents /tmp/doc.md --query "q" \
  --no-calibration --offline-cloud --hw-metrics \
  --output /tmp/report.json
# atteso: hw_before + hw_after nel JSON

# Sampler continuo
.venv/bin/python run_pipeline.py --documents /tmp/doc.md --query "q" \
  --no-calibration --offline-cloud --hw-metrics --hw-sample-period 0.5 \
  --output /tmp/report.json
# atteso: hw_samples con N campioni presi durante run_request

# Benchmark con metriche
.venv/bin/python benchmark_scheduler.py --documents /tmp/docs \
  --cases /tmp/cases.json --output /tmp/report.json \
  --no-calibration --offline-cloud --hw-metrics
# atteso: ogni riga del report ha hw_before

# REPL con metriche
.venv/bin/python repl_interattiva.py --documents /tmp/docs \
  --no-calibration --hw-metrics
# atteso: ogni domanda stampa "Hardware prima/dopo" nella tabella
```

## Stato al merge di A5

- ruff: pulito
- pytest: 169 passed (3 nuovi in `test_pipeline_integration.py` + 1 in `test_benchmark_scheduler.py` rispetto al merge A4)
- `core/telemetry_hw.py`: modulo nuovo, cross-platform, 0 dipendenze nuove
- `LocalNeuralEngine.genera_bozza`: TTFT reale via stream llama-cpp
