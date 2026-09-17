# Piano delle osservazioni sperimentali

Questo documento dice cosa eseguire, in che ordine, con quali comandi e con
quali criteri di chiusura, per produrre le osservazioni che servono ai
capitoli 3 e 4 della tesi. È scritto per essere eseguito da un assistente o
da un modello diverso da quello che lo ha redatto: ogni fase è autonoma, ha
comandi espliciti e un risultato atteso verificabile.

Le regole del progetto restano quelle di `AGENTS.md` nella root del vault.
In caso di conflitto fra questo documento e `AGENTS.md`, vale `AGENTS.md`.
Il disegno metodologico di riferimento è `docs/CONCEZIONE_SPERIMENTALE.md`;
questo piano ne operationalizza i punti ancora scoperti e le campagne di
misura conseguenti.

## 1. Stato attuale

| Elemento                                                         | Stato                                                                                                                                                                                               | Riferimento                                                       |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Calibrazione locale delle velocità                               | Implementata, testata, usata nei test preliminari                                                                                                                                                   | `core/calibration.py`, `--no-calibration`                         |
| Probe cloud di latenza (E2E)                                     | Implementato; una sola chiamata pubblica per sessione, costo in `cli_total_ms` non in `request_ms`, salta con `--offline-cloud` o senza credenziali; vedi `core/cloud.py::CloudGenerator.probe` | CONCEZIONE §2.2                                                   |
| Soglia di sforamento accettabile + parametro k                   | Implementata; default `k=0` conserva il comportamento prudente, `--sforamento-k` apre la tolleranza; visibile in `sforamento_previsto_ms`, `sforamento_piano_minimo_ms`, `tolleranza_sforamento_ms` | CONCEZIONE §3                                                     |
| Etichette sperimentali (completo/degradato/insufficienti/errore) | Implementate in `core/etichette.py`; calcolate a posteriori in `core/pipeline.py`; euristiche documentate in CONCEZIONE §4 (variante stretta per ticket via `riferimenti_ticket`); disattivabili con `--no-etichette` | CONCEZIONE §4                                                     |
| Sweep su k in `poc/docs/esplorazione_soglia/`                        | **Non eseguito**, directory assente                                                                                                                                                                 | CONCEZIONE §3                                                     |
| Estensioni benchmark (calibrazione automatica, flag throughput)  | Implementate; `benchmark_scheduler.py` calibra per default; `--no-calibration`, `--tok-per-sec-prefill/--generazione` su CLI/REPL | CONCEZIONE §3                                                     |
| Telemetria hardware (misure sul "ferro") | Implementata in `core/telemetry_hw.py` cross-platform (macOS + Linux); `--hw-metrics` e `--hw-sample-period N` su CLI/REPL; TTFT locale reale via stream llama-cpp; default spento per preservare il determinismo pytest | AGENTS.md (Architetture e Reti)                |
| Campagne offline (cloud simulato)                                | Eseguite: corpus salariale e ticket                                                                                                                                                                 | `docs/azienda_demo/RISULTATI.md`, `docs/ticket_demo/RISULTATI.md` |
| Esecuzioni con provider reale                                    | 4 run singole, non ripetute                                                                                                                                                                         | `docs/test_preliminari_settembre2026.md`                          |
| Capitoli bozza                                                   | `Bozza/` presente ma non versionato (untracked); `tesi_finale/` ancora da creare; Cap. 3 contiene riferimenti a sviluppi previsti ormai chiusi da allineare                                                              | `Bozza/`                                                          |

Conseguenza operativa: la fase A (A1 probe, A2 soglia di sforamento, A3
etichette, A4 estensioni benchmark, A5 telemetria hardware) è chiusa al
commit di audit del 16/09/2026; gli strumenti esistono e i test sono
verdi. Restano da eseguire le campagne sperimentali delle fasi B, C, D
ed E: nessuna richiede modifiche al meccanismo DP.

## 2. Regole per chi esegue

1. Lavorare dalla directory `poc/`, solo con `.venv/bin/python`.
2. Ogni modifica al codice sta su un branch dedicato (`feat/…`, `fix/…`) e
   viene mergiata su `main` solo con `ruff check .` pulito e `pytest -v`
   tutto verde. Copertura di `core.scheduler` ≥ 90%.
3. Privacy e utilità vengono prima dello SLA. Non saltare il filtro, non
   alzare epsilon per ottenere rilasci, non inviare contesti grezzi al
   provider, non presentare una stima come garanzia.
4. Lo SLA è soft: di ogni campagna si riportano frequenza ed entità degli
   sforamenti, non un semplice "rispettato/non rispettato".
5. Ogni modifica comportamentale aggiorna nella stessa modifica
   `pseudocodice.md`, `schemaablocchi.md`, `docs/CONFIGURATION.md`,
   `ARCHITECTURE.md` e i test toccati (vedi CONCEZIONE §5 per
   `test_impossible_sla_skips_retrieval_and_engine`).
6. I report JSON dettagliati vanno in `poc/reports/` (ignorato da Git).
   Le sintesi discusse vanno in markdown versionato, nel percorso indicato
   da ciascuna fase. Nei markdown versionati non copiare bozze locali o
   risposte cloud integrali se il corpus non è sintetico; per i corpus
   sintetici inclusi nel repo è ammesso.
7. Ogni sintesi markdown riporta obbligatoriamente: data, commit Git,
   macchina, modello GGUF con hash SHA-256, valori di calibrazione, valori
   del probe (o `cloud_probe_skipped`), accounting privacy cumulativo,
   numero di ripetizioni. Senza questi campi l'osservazione non è
   riproducibile e non va riportata nel capitolo 4.
8. Le run ripetute della CLI hanno ciascuna un account privacy nuovo: sono
   diagnostica, non una sessione DP unica. Scrivere le repliche come
   frequenze empiriche, mai come probabilità esatte o garanzie.
9. Prima di ogni fase con provider reale, stimare il numero di chiamate
   cloud e il tempo locale totale e scriverli nella sintesi. Non superare
   il preventivo senza chiederlo all'utente.

## 3. Fase A — Completare gli strumenti previsti

Tre branch separati, in quest'ordine. Nessuno cambia il meccanismo DP: la
scala Gumbel `4/ε`, il test PTR, il dominio pubblico k=1..10 e
l'accounting RDP non si toccano.

### A1. Probe cloud di latenza

- Implementato in `core/cloud.py` con `CloudGenerator.probe() -> RisultatoProbe`.
  Una sola generazione pubblica per sessione (prompt `PROBE_QUERY`, max
  16 token). Niente retry, niente contenuti privati.
- Esegue solo con credenziali+endpoint configurati e `offline=False`. Con
  `--offline-cloud` o senza `api_key`/`base_url`/`client`, il probe viene
  saltato e `cloud_probe_skipped=True` con `e2e_cloud_ms=None`.
- Il costo del probe (`cloud_probe_ms`) entra in `cli_total_ms` ma non in
  `request_ms`. Il campo `E2E_cloud_ms` misurato alimenta la tolleranza A2
  sostituendo la somma manuale `RTT + tempo_cloud_ms`.
- Test: `tests/test_cloud.py::test_probe_*` (5 test), `tests/test_scheduler.py::test_e2e_cloud_ms_*` (2 test), `tests/test_pipeline_integration.py::test_cli_full_run_records_probe_when_credentials_are_configured`, `test_cli_full_run_skips_probe_when_offline`.
- Documenti aggiornati: `ARCHITECTURE.md` §Scheduler e tempi, `pseudocodice.md`, `schemaablocchi.md` (sezione "Sviluppi concordati" → implementato), `CONFIGURATION.md` (tabella parametri).
- Campi del report JSON: `cloud_probe_ms`, `e2e_cloud_ms_ms`, `ttft_cloud_ms`, `cloud_probe_skipped`, `cloud_probe_simulato`, `cloud_probe_errore`.

Chiusura: gate verdi; con `cloud_probe_ms` e `E2E_cloud_ms_ms` plausibili (confronto con i 4,9–10,1 s osservati nei test preliminari) il report JSON riporta correttamente il probe. Lo smoke run con provider reale è ancora da eseguire (account OpenCode al momento segnala limite mensile raggiunto).

### A2. Soglia di sforamento accettabile

- Implementato in `core/scheduler.py` con la formula della CONCEZIONE §3:
  `tolleranza_ms = k · E2E_cloud_ms`;
  `accetta_sforamento = sforamento_piano_minimo_ms <= tolleranza_ms`.
  `E2E_cloud_ms` è la misura reale del probe A1 quando disponibile,
  altrimenti la somma manuale `RTT + tempo_cloud_ms`.
- Se accetta: `n_ensemble = N_MIN`, campi `sforamento_accettato`,
  `sforamento_previsto_ms`, `sforamento_piano_minimo_ms`,
  `tolleranza_sforamento_ms` e `k_sforamento` nella decisione. Se non accetta:
  il piano cade in `N=0` e i campi restano come etichette informative.
- N=0 resta solo per `--force-zero-shot` e per budget privacy esaurito.
  Non è più il default per SLA incompatibile.
- Parametro `--sforamento-k` con default `0`; la CLI protegge da `inf`/`nan`
  (lo scheduler valida `k_sforamento` con `_validate_finite_non_negative`).
- Test: `test_sforamento_k_zero_reproduces_conservative_behavior`,
  `test_sforamento_k_positive_accepts_small_overrun`,
  `test_sforamento_k_positive_but_insufficient_still_zero_shot`,
  `test_fixed_baseline_does_not_apply_sforamento_policy`,
  `test_sforamento_previsto_describes_the_executed_plan`,
  `test_force_zero_shot_is_explicit_and_bypasses_tolerance`,
  `test_accepted_overrun_is_declared_as_an_estimate`,
  `test_tolerance_does_not_change_a_plan_that_already_fits`,
  `test_k_sforamento_is_validated`, `test_tolerance_requires_enough_candidates`,
  `test_accepted_overrun_message_does_not_claim_infeasibility`. Test integrazione
  pipeline: `test_impossible_sla_with_tolerance_runs_retrieval_and_engine`,
  `test_impossible_sla_with_k_zero_skips_retrieval_and_engine`,
  `test_force_zero_shot_skips_retrieval_even_with_a_roomy_sla`. REPL:
  `test_sforamento_k_e_force_zero_shot_via_parser`. Copertura scheduler ≥ 90%.

Chiusura: gate verdi; con `k>0` e SLA leggermente sotto il piano minimo,
lo scheduler pianifica N_MIN e marca lo sforamento previsto nel report.

### A3. Etichette sperimentali

- Implementate in `core/etichette.py` con la funzione
  `classifica_risultato(decisione, dp, risposta, riferimenti) -> EsitoRisultato`.
  Quattro label: `insufficienti`, `errore`, `completo`, `degradato`. Gerarchia
  deterministica: `insufficienti` (rilascio vuoto o zero-shot) > `errore`
  (provider fallito) > `completo` (riusa keyword e niente astensione,
  oppure passaggi in ordine se `riferimenti_ticket` sono forniti) >
  `degradato` (rilascio e risposta arrivata ma non soddisfano la euristica
  di completo).
- Pattern di astensione dichiarati in `ASTENSIONE_PATTERN` (italiano e
  inglese). Sono conservativi: servono a raggruppare i risultati per
  discussione, non a certificare la qualità.
- Variante stretta per ticket: campo `riferimenti_ticket: tuple[PatternRiferimento, ...]`
  sul `RequestConfig`. Ogni `PatternRiferimento` ha `passaggi: tuple[str, ...]`
  che devono comparire nella risposta nell'ordine dato (substring match
  case-insensitive). Almeno un riferimento completo → `completo`,
  altrimenti `degradato`.
- Calcolate a posteriori in `core/pipeline.py` senza modificare prompt,
  query, sequenza di chiamate né comportamento. Il campo `esito` del
  report JSON ha `label`, `motivazione`, `riferimenti_usati`.
- Disattivabili da CLI/REPL con `--no-etichette` (campo
  `etichette_attive: bool = True` sul `RequestConfig`). Quando disattivate
  il report registra `motivazione="etichette disattivate via CLI"`.
- Test: 17 in `tests/test_etichette.py` (gerarchia, astensione, ticket in
  ordine e ordine sbagliato, zero-shot, serializzazione JSON,
  riferimenti vuoti); 2 in `tests/test_pipeline_integration.py`
  (`test_cli_full_run_attaches_esito_label`,
  `test_cli_full_run_no_etichette_disables_label`).

Chiusura: gate verdi; il report JSON dei run di smoke include il campo
`esito` con label e motivazione. Le etichette sono euristiche: il
capitolo 4 le discute come metadati di analisi, non come claim di
qualità.

### A4. Estensioni minori agli strumenti di benchmark

- Implementato. `benchmark_scheduler.py` ora calibra automaticamente le
  velocità locali all'avvio della sessione (default) e propaga i valori
  misurati nel `RequestConfig` di ogni run. Senza calibrazione il
  confronto adattivo/fisso era tarato sui default `250/50 tok/s`, smentiti
  dalle misure reali (`~1950/~480` nei test preliminari).
- Flag nuovi su `benchmark_scheduler.py` e `repl_interattiva.py`:
  `--no-calibration` (disattiva), `--tok-per-sec-prefill`,
  `--tok-per-sec-generazione` (manuali, usati solo con
  `--no-calibration`). Comportamento allineato a `run_pipeline.py`.
- Report JSON del benchmark include `prefill_tps`, `generation_tps`,
  `calibration_ms` per documentare i valori usati nelle run.
- `repl_interattiva.py` coerente con A1–A3: probe A1 all'avvio,
  `--sforamento-k`, `--force-zero-shot`, `--no-etichette`,
  calibrazione automatica all'avvio.
- Test: 2 in `tests/test_benchmark_scheduler.py` (calibrazione attiva
  + manuale); 1 in `tests/test_repl_interattiva.py` (parser flags).
- Documenti aggiornati: `CONFIGURATION.md` (tabella parametri).
- Vincoli non toccati: `core/privacy` non modificato, REPL invariato
  come sessione DP cumulativa.

### A5. Telemetria hardware (misure sul "ferro")

- Implementata in `core/telemetry_hw.py` con `snapshot()` e
  `HwSampler.sample_until(stop_event)`. Cross-platform: macOS
  (`powermetrics`, `top`, `vm_stat`, `sysctl`) e Linux (`nvidia-smi`,
  `sensors`, `top`, `/proc/meminfo`).
- Metriche: temperatura CPU/GPU/SoC, util CPU/GPU, RAM used/total,
  VRAM, Watt CPU/GPU, memory pressure. Sensori che richiedono sudo
  (`powermetrics` su macOS, `sensors` su Linux) restituiscono `None`
  quando il tool manca o non è invocabile: il prototipo non solleva.
  Per abilitare letture sudo senza prompt: configurare
  `NOPASSWD` in `/etc/sudoers.d/` e impostare `POC_HW_SUDO=1`.
  Operazione di setup laboratorio, non artefatto di produzione.
- CLI e REPL accettano `--hw-metrics` (istantanei prima/dopo) e
  `--hw-sample-period N` (sampler continuo durante la run, su thread
  separato). Default spento, determinismo pytest preservato.
- `LocalNeuralEngine.genera_bozza` misura il TTFT reale via stream
  llama-cpp (`tempo_prefill_reale_sec`), distinto dalla stima
  euristica (`tempo_prefill_stimato_sec`). `prefill_real_ms` nel
  report JSON (None se non misurato).
- `benchmark_scheduler.py` con `--hw-metrics` aggiunge `hw_before` a
  ogni riga del report: la campagna può correlare edge latency con
  drift termico/utilizzo fra run.
- Test: 11 in `tests/test_telemetry_hw.py`, 4 in
  `tests/test_engine_runtime.py`, 1 in `test_benchmark_scheduler.py`
  (`hw_metrics`), 2 in `test_pipeline_integration.py` (CLI con e
  senza `--hw-metrics`).
- Documenti aggiornati: `ARCHITECTURE.md`, `CONFIGURATION.md`,
  `pseudocodice.md`, `schemaablocchi.md`.

## 4. Fase B — Sweep sul coefficiente k

Dipende da A1+A2. Produce i primi dati per la scelta di k e va in
`poc/docs/esplorazione_soglia/RISULTATI.md` (markdown versionato) con i
JSON in `poc/reports/`.

- Griglia: `k ∈ {0, 0.1, 0.25, 0.5}` × 10 ripetizioni, ordine mescolato
  con seed registrato.
- Setup: corpus `docs/ticket_demo/documenti`, query E42 procedurale,
  provider reale, SLA scelto appena sotto il tempo stimato del piano
  minimo (ricavato da un run preliminare: lo sforamento previsto deve
  essere piccolo ma non nullo, altrimenti k non discrimina).
- Per ogni run registrare: k, N scelto, `sforamento_accettato`,
  `sforamento_previsto_ms`, tempo misurato, sforamento reale, esito del
  filtro, etichetta.
- Analisi: per ciascun k, frequenza degli sforamenti reali e loro entità
  (media e massimo), frequenza di rilascio, quota di piani minimi
  accettati. La domanda a cui rispondere è: quale k tiene gli sforamenti
  dentro la variabilità naturale del provider senza rinunciare al lavoro
  locale?
- Il risultato è un'ipotesi di lavoro discussa nel capitolo 4, non una
  scelta definitiva (CONCEZIONE §7).

Costo indicativo: ~40 chiamate cloud, ~30–40 minuti di tempo totale.

## 5. Fase C — Campagne di misura

### C1. Ripetibilità dei quattro casi preliminari (dopo A3)

Rieseguire i casi di `docs/test_preliminari_settembre2026.md` con 5
ripetizioni ciascuno, stessa configurazione (SQuAD ε=1 δ=1e-4 e ε=8 δ=0.01;
ticket E42 procedura e codice privato ε=8 δ=0.01; SLA 60000 ms; provider
reale; calibrazione attiva).

- Domande: quanto variano `request_ms` e `E2E_cloud_ms` fra ripetizioni?
  L'esito del PTR è stabile fra run? Le etichette di utilità coincidono
  con la lettura manuale dei test preliminari?
- Comando base (adattare query e corpus per caso):

```bash
.venv/bin/python run_pipeline.py --documents docs/ticket_demo/documenti \
  --query "Come si risolve l'errore E42 dopo aggiornamento di FerroSync? Riporta i passaggi della procedura generale in ordine." \
  --epsilon 8 --delta 0.01 --max-latency-ms 60000 \
  --output reports/c1_ticket_e42_run1.json
```

- Sintesi in `docs/test_preliminari_settembre2026.md` (sezione nuova
  "ripetizioni") o in un file dedicato nella stessa directory.
- Costo: 20 chiamate cloud.

### C2. Effetto di N ed ε sul rilascio (offline, senza provider)

Estendere al corpus ticket la griglia già usata per il corpus salariale:
una generazione reale di bozze per (query, N), poi repliche del solo
filtro sulle bozze congelate.

- Strumento esistente: `benchmark_ticket_demo.py --trials 500` copre già
  N ∈ {5,10,20,40} × ε ∈ {1,4,8} su 4 query. Rieseguirlo dopo A per
  verificare che nulla sia cambiato, e confrontare con
  `docs/ticket_demo/RISULTATI.md`.
- Aggiungere, se il tempo lo consente, una query del corpus salariale per
  confermare l'effetto "documenti non pertinenti riducono il gap" già
  osservato (N=20 vs N=40 su Amministrazione/Commerciale).
- Nessuna chiamata cloud. Le repliche con seed diagnostico su dati
  sintetici restano diagnostica condizionale, non sessioni DP.
- Questa campagna alimenta il capitolo 4.3 insieme alle 24 000 repliche
  già esistenti: riportare le frequenze come empiriche, con la dimensione
  campionaria, e non attribuire probabilità zero alle celle con zero
  eventi.

### C3. Adattivo contro N fisso, con calibrazione e SLA realistici

Dipende da A4. La domanda del capitolo 4.2 è se l'adattivo, con throughput
misurati invece dei default, smette di comportarsi come la baseline minima.

- Strumento: `benchmark_scheduler.py` su corpus salariale e ticket, con
  calibrazione o throughput calibrati passati esplicitamente.
- Variante per SLA: {5000, 15000, 30000} ms. Per ciascuno: adattivo,
  fisso 5, 10, 20, 40; 5 ripetizioni per variante, ordine mescolato
  (`--order-seed` registrato), account di sessione con `--session-epsilon`
  dichiarato.
- Metriche per variante: N scelto, tempo medio/min/max, frequenza di
  rilascio, sforamenti (frequenza ed entità), ε cumulativo consumato.
- Prima in `--offline-cloud` (nessun costo, tempi cloud nulli dichiarati
  come simulazione), poi le sole celle decisive ripetute con provider
  reale se l'utente autorizza il costo.
- Sintesi in `docs/azienda_demo/RISULTATI.md` (sezione nuova) e in una
  sintesi analoga per i ticket.

### C4. Effetto della calibrazione sulle decisioni

Confronto diretto default vs calibrazione sulle decisioni dello scheduler,
senza provider.

- Stesso corpus e query di C3, SLA stretto (1500 ms default) e SLA medio
  (5000 ms): `run_pipeline.py` con e senza `--no-calibration`, anche in
  `--dry-run` dove basta il piano.
- Tabella attesa: per ogni (SLA, modalità) il N pianificato, la stima, la
  fattibilità. I test preliminari prevedono che con i default e SLA 1500
  ms si cada in zero-shot mentre con la calibrazione si pianifichi lavoro
  locale: verificarlo e quantificarlo.
- Questa osservazione chiude il cerchio con il capitolo 4.2 ("prototipo
  troppo conservativo") e motiva la calibrazione nel capitolo 3.

## 6. Fase D — Utilità delle risposte

Dipende da A3 e C1. Il capitolo 4.4 ha bisogno di una valutazione
esplicita, non della sola presenza di keyword.

- Per ogni run con rilascio: tabella keyword rilasciate ↔ passaggi attesi
  da `cases.json`; controllo manuale di ordine e completezza della
  risposta cloud (l'ordine alfabetico del rilascio non conserva la
  sequenza operativa: va dichiarato).
- Classificare le risposte con le etichette e confrontare l'etichetta con
  il giudizio manuale: riportare i disaccordi come limiti delle euristiche
  (CONCEZIONE §7).
- Casi negativi da presidiare: codice privato (attesa: astensione, nessun
  codice inventato) ed E99 assente (attesa: nessuna procedura inventata).
  Un rilascio rumoroso di token frequenti ma scorretti, come "patriots"
  nel caso Super Bowl, va riportato come limite del meccanismo, non
  nascosto.
- Sul cloud simulato nessun punteggio di qualità: dichiararlo ogni volta.

## 6b. Fase E — Confronto hardware cross-platform

Contributo distintivo della proposta per Architetture e Reti (analisi
del thermal throttling, throughput edge, latenza locale al variare
dell'hardware). Lo strumento è già implementato in `core/telemetry_hw.py`
ed è cross-platform; manca l'esecuzione su macchine diverse dal Mac ARM64
di sviluppo. Va dichiarata come fase di lavoro non come "sviluppo
futuro": il confronto è parte integrante della tesi.

Dipendenze: A5 (telemetria), C3 (adattivo vs fisso — produce le metriche
edge da confrontare).

- **Macchina A (riferimento):** Apple Silicon (Apple M1/M2/M3), raccolta
  già disponibile via `powermetrics` + `top` + `vm_stat` + `sysctl`.
  Le misure vanno in `poc/docs/esplorazione_hw/M1/RISULTATI.md` con
  allegato il JSON del report (`poc/reports/hw_mac_*.json`).
- **Macchina B (x86 con acceleratore):** desktop o laptop Linux con GPU
  NVIDIA (es. RTX 2070). Letture via `nvidia-smi` + `sensors` + `top` +
  `/proc/meminfo`. Stessa CLI, stesso modello GGUF, stesse query di C3
  su corpus salariale e ticket. Output in
  `poc/docs/esplorazione_hw/x86_rtx2070/RISULTATI.md`.
- **Macchina C (x86 senza acceleratore, opzionale):** per isolare
  l'effetto della GPU dal thermal throttling del pacchetto CPU+GPU.

Per ogni macchina raccogliere: `--hw-metrics` + `--hw-sample-period 5`
per almeno 30 minuti di run, includendo il drift termico fra run
iniziale e run finale; stessa griglia di C3; campioni hw durante le
inferenze per correlare `tempo_per_inferenza` con temperatura/utilizzo.

Sintesi attesa in `poc/docs/esplorazione_hw/CONFRONTO.md`: tabella con
per-macchina (P_{prefill}, P_{generazione}, T_{idle}, T_{sotto_carico},
ΔT dopo 30 min, jitter di latency). Limitare le conclusioni alle
misure: nessuna estrapolazione a hardware non testato.

Costo indicativo: solo tempo macchina locale, nessuna chiamata cloud
aggiuntiva. La fase E non blocca la stesura della tesi: Cap. 3 può
partire con le sole misure Mac, Cap. 4.2 può essere esteso dopo.

## 7. Ordine di esecuzione consigliato

| #   | Fase                           | Dipende da | Costo provider         | Tempo locale stimato |
| ---:| ------------------------------ | ---------- | ----------------------:| -------------------- |
| 1   | ~~A2 soglia di sforamento~~    | —          | 0                      | medio                |
| 2   | A1 probe cloud                 | —          | 1 chiamata di verifica | medio                |
| 3   | A3 etichette                   | —          | 0                      | medio                |
| 4   | A4 benchmark scheduler         | A1, A2     | 0                      | basso                |
| 5   | C4 effetto calibrazione        | —          | 0                      | basso                |
| 6   | C2 griglia N×ε (offline)       | —          | 0                      | alto                 |
| 7   | C3 adattivo vs fisso (offline) | A4         | 0                      | alto                 |
| 8   | B sweep su k                   | A1, A2     | ~40 chiamate           | medio                |
| 9   | C1 ripetizioni provider reale  | A3         | ~20 chiamate           | medio                |
| 10  | D utilità                      | A3, C1     | 0 (analisi)            | medio                |
| 11  | E confronto hardware           | A5, C3     | 0 (tempo macchina)     | medio–alto           |

Le fasi 1–3 sono indipendenti fra loro e possono essere eseguite in
qualunque ordine; la tabella mette prima le modifiche che sbloccano più
campagne. Le fasi 5–7 non richiedono modifiche e possono partire subito se
la fase A viene rinviata, ma C3 senza A4 va dichiarata tarata sui default.

## 8. Cose aperte / da fare

Lista operativa, distinta dalla roadmap delle campagne. È il riferimento
per chi riapre il vault: dice "cosa stava per essere fatto e non è stato
chiuso". Aggiungere voci nuove solo quando sono diventate bloccanti;
quelle solo "interessanti" vanno in §7 o nei promemoria personali.

| # | Voce | Stato al 17/09/2026 | Prossima azione |
| -:| ---- | ------------------- | --------------- |
| 1 | Eseguire C4 (effetto calibrazione) | Non eseguita; strumenti pronti, nessun provider richiesto | Lanciare `run_pipeline.py` su corpus salariale e ticket con e senza `--no-calibration`, `--dry-run` dove basta il piano; sintesi in `docs/azienda_demo/RISULTATI.md` sezione "calibrazione" |
| 2 | Eseguire C2 (griglia N × ε ticket) | Non eseguita dopo le modifiche A | `benchmark_ticket_demo.py --trials 500`; confrontare con `docs/ticket_demo/RISULTATI.md` |
| 3 | Eseguire C3 (adattivo vs fisso offline) | Non eseguita dopo A4 | `benchmark_scheduler.py` con sweep SLA su corpus salariale + ticket; output in `docs/azienda_demo/RISULTATI.md` |
| 4 | Eseguire B (sweep su k) | Non eseguita | `poc/docs/esplorazione_soglia/` da creare; ~40 chiamate cloud |
| 5 | Eseguire C1 (ripetizioni provider reale, 5 repliche/caso) | Non eseguita; account OpenCode al limite mensile | Verificare disponibilità account, altrimenti provider alternativo |
| 6 | Eseguire D (analisi utilità risposte) | Non eseguita | Dopo C1; usa `core/etichette` per il confronto con giudizio manuale |
| 7 | Eseguire E (confronto hardware) | Non eseguita; solo Mac ARM64 misurato | Predisporre macchina x86 con GPU NVIDIA; replicare CLI + `--hw-metrics`; sintesi in `poc/docs/esplorazione_hw/CONFRONTO.md` |
| 8 | Stesura capitoli | `Bozza/` untracked, `tesi_finale/` assente | Versionare `Bozza/`, creare `tesi_finale/`, allineare Cap. 3 al codice attuale (rimuovere riferimenti a "sviluppi previsti" ormai chiusi) |
| 9 | Allineamento `Bozza/03_Capitolo3.md` al codice attuale | Non eseguito | Rimuovere le frasi su "calibrazione ancora da chiudere", "probe da implementare", TTFT come misura diretta (oggi è stima euristica) |
| 10 | Allineamento `Bozza/04_Capitolo4.md` ai dati | Non eseguito | Inserire numeri solo dopo l'esecuzione delle campagne; riportare dimensione campionaria e condizioni di misura |
| 11 | Dichiarazione formale del confronto hardware al relatore | Da decidere la formulazione | Da concordare con l'utente: la fase E è ora pianificata, va comunicato che è parte integrante della tesi (non "sviluppo futuro") |
| 12 | Limitare l'uso di `LANGFUSE_CAPTURE_SENSITIVE` ai soli esperimenti autorizzati | Policy già in `AGENTS.md`, ma va richiamata in ogni run di campagna | Promemoria da spostare in testa alle checklist di C1, B, D |

Le voci 1–7 sono eseguibili senza modifiche al codice. Le voci 8–11
richiedono decisioni dell'utente. La 12 è promemoria operativo.

## 9. Cosa aggiornare alla fine

- `Bozza/03_Capitolo3.md`: §3.1 setup di sessione (calibrazione e probe
  con i valori misurati), §3.3 protocollo effettivo, §3.4 metriche ed
  etichette. Rimuovere o correggere le affermazioni non più aderenti al
  codice (per esempio il ruolo del seed, oggi a solo scopo di compatibilità
  nel retrieval deterministico, e il TTFT, oggi stima euristica e non
  misura). Includere la fase E (confronto hardware) con le prime misure
  Mac, segnalando che il dato x86 è pianificato e non ancora disponibile.
- `Bozza/04_Capitolo4.md`: §4.1 stima vs osservato (C1, C4), §4.2
  adattivo vs fisso (C3, B), §4.3 rilascio in funzione di N ed ε (C2),
  §4.4 utilità (D), §4.5 limiti. I numeri vanno inseriti solo dopo
  l'esecuzione, con la dimensione campionaria e le condizioni di misura.
- `pseudocodice.md` e `schemaablocchi.md`: spostare le voci dalla sezione
  sviluppi previsti a quella implementata man mano che la fase A chiude
  (fatto al commit di audit; tenere aggiornato se A riapre).
- `docs/CONFIGURATION.md` e `ARCHITECTURE.md`: a ogni merge della fase A
  o di modifiche allo scheduler/probe.

## 10. Divieti espliciti per chi esegue

- Non modificare le costanti del meccanismo DP (scala Gumbel `4/ε`, soglia
  PTR `max(2, d_k)`, sensibilità del gap 2) né `strict_gap_guard`.
- Non toccare `poc/archive/` e `poc/poc_real_dp_ksa.py` oltre l'uso legacy.
- Non usare documenti reali dell'utente, credenziali vere nei test, né
  inviare contenuti a Langfuse con `capture_sensitive` fuori dagli
  esperimenti autorizzati su dati sintetici o pubblici.
- Non scegliere i parametri "per far funzionare" una tesi attesa: se
  l'adattivo perde contro il fisso, si riporta; se il rilascio è raro, si
  riporta.
- Non dichiarare garantito ciò che è stimato: SLA, prefill, tempi cloud e
  etichette sono stime o euristiche, e vanno etichettati come tali in ogni
  sintesi.
- Non mergiare con test rossi o ruff sporco; in caso di blocco, lasciare
  il branch aperto con commit `wip:` e segnalare cosa è rotto e perché.
