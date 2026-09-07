# Istruzioni del repository

## Ambito

- Questa root è un vault di materiali per la tesi. Il codice eseguibile e i test sono in `poc/`; Markdown, traduzioni e PDF della root sono materiale di ricerca, non input di build.
- L'entrypoint supportato è `poc/run_pipeline.py`. `poc/poc_real_dp_ksa.py` è solo un wrapper di compatibilità legacy; `poc/archive/` contiene prototipi storici e non va esteso.
- Per il flusso, le invarianti e le assunzioni privacy leggere `poc/ARCHITECTURE.md`; per configurazione e formule usare rispettivamente `poc/docs/CONFIGURATION.md` e `poc/docs/PRIVACY_ACCOUNTING.md`.
- Il paper di riferimento è: Tang et al., *"Differentially Private Retrieval-Augmented Generation"*, PDF locale con metadati editoriali provvisori YYYY(X); non attribuire una pubblicazione PoPETS 2025 verificata. Ogni scelta implementativa che tocca il meccanismo DP deve essere ricondotta agli Algoritmi 1, 2, 3 e alla dimostrazione in Appendice A di quel paper.

## Ambiente e comandi

- Eseguire i comandi dalla directory `poc/` e usare sempre `.venv/bin/python`, non il Python di sistema.
- Setup: `.venv/bin/python -m pip install -r requirements-dev.txt` (include anche `requirements.txt`). Se manca il benchmark, eseguire `.venv/bin/python scripts/fetch_real_dataset.py`.
- Suite completa: `.venv/bin/python -m pytest -v`.
- Test mirato: `.venv/bin/python -m pytest -q tests/test_scheduler.py` oppure aggiungere `::nome_del_test` al percorso.
- Lint: `.venv/bin/python -m ruff check .`. Ruff usa Python 3.10, limite di 100 caratteri e legge `poc/pyproject.toml`; esclude `archive/`, `models/` e `.venv/`.
- Coverage mirata: `.venv/bin/python -m coverage erase`, poi `.venv/bin/python -m coverage run -m pytest -q tests/test_scheduler.py -p no:cov`, infine `.venv/bin/python -m coverage report -m`.

## Flusso di lavoro Git

Ogni modifica al codice deve seguire questo flusso. Il branch `main` deve essere sempre in uno stato funzionante (tutti i test verdi, ruff pulito).

**1. Crea un branch dedicato** prima di toccare qualsiasi file:
```bash
git checkout main && git pull
git checkout -b fix/<nome-breve>   # es. fix/dp-ksa-filter, fix/scheduler-adaptive
```

**2. Implementa e testa in locale** (dalla directory `poc/`):
```bash
.venv/bin/python -m ruff check .          # zero warning prima di procedere
.venv/bin/python -m pytest -v             # tutti i test devono passare
```

**3. Merge su main solo se entrambi i gate sono verdi:**
```bash
git checkout main
git merge --no-ff fix/<nome-breve> -m "fix: <descrizione>"
git branch -d fix/<nome-breve>
```

**Se i test falliscono:** non mergiare. Lasciare il branch aperto, documentare il fallimento in un commit con prefisso `wip:`, e segnalare all'utente cosa è rotto e perché.

**Convenzioni sui nomi di branch:**
- `fix/<cosa>` — correzione di un bug o di un'implementazione errata
- `feat/<cosa>` — feature nuova (es. `feat/scheduler-adaptive`)
- `refactor/<cosa>` — refactoring senza cambiamento di comportamento
- `docs/<cosa>` — solo documentazione

**Commit message:** usare prefissi convenzionali (`fix:`, `feat:`, `refactor:`, `docs:`, `test:`). Ogni commit deve essere atomico: un solo concetto logico per commit.

## Runtime e dati

- Il primo avvio di `run_pipeline.py` o `benchmark_tokens.py` può scaricare il modello GGUF in `poc/models/`; il download è automatico e il file è ignorato da Git. Per esperimenti riproducibili preferire un URL del modello versionato invece del default `main`. Il download deve essere atomico: se il file è incompleto (dimensione != Content-Length) va cancellato e sollevato un errore esplicito.
- `run_pipeline.py` è il percorso per gli esperimenti correnti. Usare `--seed` per rendere riproducibile il campionamento; `benchmark_tokens.py` richiede il modello locale e `llama-cpp-python`. Il seed resta disponibile nell’API `ottieni_campione_ensemble(n, seed=seed)`; la pipeline corrente usa retrieval deterministico per query e mantiene `--seed` solo per compatibilità.
- Copiare `poc/.env.example` in `poc/.env` per provider cloud o Langfuse. Non versionare `.env`, chiavi o modelli. Senza chiave e senza endpoint cloud viene usata la simulazione offline deterministica.
- `core.model_config` è la fonte unica per prompt, limiti di generazione e configurazione del modello condivisi da inferenza e benchmark; non duplicare questi valori nei due percorsi.
- I tempi di prefill esposti da `core.engine` (campo `tempo_prefill_stimato_sec`) sono stime euristiche basate su un fattore fisso, non misurazioni dirette. Etichettarli sempre come tali nell'output e nei commenti.

## Confini architetturali e privacy

- `core.documents` legge solo percorsi locali esplicitamente indicati (TXT, Markdown, PDF testuali), deduplica i contesti originali e sceglie un estratto per documento con punteggi locali rispetto alla query. Non usare chunk o righe QA duplicate come voti indipendenti. Gli slot mancanti sono vuoti pubblici, mai copie dei documenti. `core.dataset` conserva il benchmark e l'API di campionamento con seed opzionale.
- L'unità protetta è il documento originale normalizzato. Query, N e configurazione devono essere indipendenti dal contenuto privato. Non introdurre IDF del corpus o retrieval che cambi più di un membro tra corpus adiacenti senza aggiornare l'analisi.
- `core.scheduler` sceglie N tra 5 e 40 oppure N=0 (fallback zero-shot). Riceve slot e limiti del prompt pubblici, non lunghezze misurate dai documenti. Se il piano minimo non entra nello SLA stimato, la pipeline non avvia retrieval e inferenza locale. `sla_fattibile` è riferito alle stime, non una garanzia rigida. `fixed_n` è una baseline sperimentale che può eccedere lo SLA e deve dichiararlo. Il campo storico `ptr_pass_rate_attesa` contiene solo P(pass | gap=3), non una previsione sul corpus. Budget insufficiente: `core.scheduler.PrivacyBudgetExhaustedError`.
- `core.engine` gestisce llama.cpp e il download atomico del modello. Non espone il testo dei documenti al di fuori del processo locale.
- `core.privacy` implementa **DP-KSA (Tang et al., PDF locale)** con due algoritmi distinti:
  - **FindBestK (Algorithm 3, adattamento conservativo):** dominio pubblico predefinito k=1..10, conteggi zero impliciti, inclusione del gap dell'ultimo token osservato. Sensibilità globale del gap = 2. Scala Gumbel **4/ε**, secondo la Definizione A.7 `exp(ε q/(2Δ))`. Lo pseudocodice scrive 2/ε: la differenza è esplicita in `poc/docs/PRIVACY_ACCOUNTING.md`; non ripristinare la costante meno prudente senza prova. Il rumore va calibrato sull'epsilon effettivamente contabilizzato.
  - **TopKWithPTR (Algorithm 2):** rilascia l’insieme top-k-hat in ordine alfabetico (mai per frequenza privata) solo se il test d-hat_k = max(2, d_k) + N(0, 4σ²) − Φ(1−δ; 0, 2σ) > 2 passa. Se il test fallisce: zero-shot, nessun token rilasciato. Per gap >2 l’insieme è localmente stabile; per gap <=2 resta il failure event di probabilità delta. Non confondere il passaggio rumoroso con la certezza di stabilità.
  - La classe esposta è `DP_KSA_Filter`. Mantiene un account RDP cumulativo (composizione via Teorema A.3, conversione in (ε,δ)-DP via Teorema A.6): chiamate ripetute possono sollevare `DPBudgetExhaustedError`; query diverse sullo stesso corpus devono condividere lo stesso account. `delta_budget` è un limite cumulativo esplicito e di default consente una chiamata. La CLI singola non persiste l’account fra avvii: non dichiarare protezione di una sessione intera dopo un reset del filtro. L'output `EsitoDP` espone `budget_consumato_epsilon` e `budget_consumato_delta`.
- Non alterare l'interpretazione della prova senza aggiornare formule, test e documentazione. `strict_gap_guard` è disattivato di default e non fa parte del meccanismo formale del paper.
- `core.cloud` deve inviare al provider solo query e parole rilasciate dal filtro; i contesti grezzi restano locali e servono solo al calcolo delle metriche di confronto.
- `core.telemetry` è opzionale e serve **alla visibilità sperimentale e a dimostrare gli assunti della tesi**. L'utente autorizza l'uso dell'istanza Langfuse cloud per esperimenti su dati pubblici o autorizzati; **non chiedere di installare ora un'istanza locale**. In un deployment reale con documenti riservati l'utente userebbe un'istanza Langfuse locale nel perimetro fidato.
- La diagnostica completa (`LANGFUSE_CAPTURE_SENSITIVE=true`) può includere query, bozze, conteggi e metriche private per la dimostrazione. Non è coperta dalla garanzia DP del rilascio al provider. Anche i trace redatti, i tempi, la console e i report JSON sono diagnostica sperimentale, non meccanismi DP. Mantenere questa distinzione esplicita senza bloccare il lavoro di osservabilità autorizzato. `--no-telemetry` disabilita i trace; `--offline-cloud` forza la simulazione anche con credenziali configurate.
- Nei test usare corpus sintetici, client fittizi e directory temporanee. Non leggere segreti né inviare documenti reali dell'utente a provider o telemetria. I byte del testo non sono byte di rete; prefill stimato non è TTFT misurato. Le risposte simulate non hanno un punteggio di qualità reale.

## Invarianti di test

- `core.privacy` — **FindBestK:** il rumore Gumbel deve avere scala ≈ 4/ε (test statistico N=10000). **TopKWithPTR:** con d_k > 2 e σ piccola il test deve passare con alta probabilità; con d_k ≤ 2 la probabilità analitica di rilascio è delta; solo con strict_gap_guard è zero. Testare dominio pubblico anche su istogrammi vuoti e ordinamento alfabetico dopo la selezione. Token con frequenza 0 non devono comparire nell'output. Dopo ogni invocazione: `budget_consumato_epsilon + epsilon_rimasto == epsilon_budget`.
- `core.dataset` — invocazioni successive senza seed devono restituire campioni diversi con probabilità > 0.99.
- `core.scheduler` — SLA incompatibile con N_MIN → N=0; budget temporale sufficiente → N=N_MAX; ε esaurito → `PrivacyBudgetExhaustedError`; `epsilon_find_best_k + epsilon_top_k_ptr ≤ epsilon_budget`.
- `core.engine` — se il download si interrompe prima del completamento (dimensione file < Content-Length), il file parziale deve essere cancellato e deve essere sollevato un errore esplicito.
- Copertura minima: `core.scheduler` ≥ 90%. Suite completa: zero failing su `pytest -v`. Nessun warning da `ruff check .`.

## Comunicazione

- Quando si scrivono email, risposte o testi accademici, seguire `.agents/rules/no-tecnichese.md` e `.agents/skills/natural-communication/SKILL.md`: tono sobrio, diretto e senza gergo o formule da modello non necessarie.
