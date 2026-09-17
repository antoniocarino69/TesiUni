# Capitolo 3: Realizzazione del prototipo e metodologia sperimentale

## 3.1 Ambiente di esecuzione e organizzazione del software

Il prototipo del sistema è stato realizzato in linguaggio Python, organizzato in moduli che separano chiaramente le responsabilità architetturali. I confini logici sono stati tracciati per isolare le operazioni di competenza locale da quelle rivolte verso l'esterno.

Il modulo `core.engine` gestisce l'esecuzione del modello linguistico locale avvalendosi di llama.cpp, permettendo l'inferenza efficiente su hardware non specializzato (es. processori centrali standard o GPU di fascia consumer). Il modulo `core.privacy` contiene l'implementazione rigorosa del filtro DP-KSA (classe `DP_KSA_Filter`), inclusi gli algoritmi FindBestK e TopKWithPTR. Il modulo `core.scheduler` implementa le logiche decisionali per la scelta del parametro $N$ sulla base delle stime temporali e del budget disponibile.

A questi si aggiungono moduli di supporto sperimentale. `core.calibration` misura le velocità reali di prefill e generazione del modello locale all'avvio di ogni sessione, eseguendo inferenze di prova su testi pubblici a lunghezze rappresentative (256, 512, 1024 token). Le misure sostituiscono i valori di default (250/50 token al secondo) che, come mostrano i test preliminari, sottostimano di un fattore 8–10 le prestazioni reali del modello. Il modulo `core.cloud` espone un metodo di probe E2E che esegue una sola generazione pubblica per sessione, misurando la latenza end-to-end della chiamata cloud senza trasportare contenuti privati. Il modulo `core.etichette` calcola a posteriori quattro label euristiche (`insufficienti`, `errore`, `completo`, `degradato`) sul risultato di ogni richiesta, come metadati di analisi per la discussione sperimentale. Infine, `core.telemetry_hw` raccoglie metriche hardware (temperatura, utilizzo, RAM, VRAM, Watt) su macOS e Linux per correlare le prestazioni con le condizioni del dispositivo.

Il codice è stato sviluppato adottando pratiche rigorose di test (unit testing e controlli di copertura) per verificare le invarianti formali, garantendo ad esempio che nessun token non ammesso possa superare il filtro e che la contabilizzazione del budget sia conservativa. La suite comprende 181 test con copertura del modulo `core.scheduler` superiore al 97%.

## 3.2 Dataset di test: ticket IT

Per valutare il sistema in condizioni realistiche e focalizzandosi sul bilanciamento tra risorse computazionali e qualità delle risposte, è stato adottato un dataset composto da ticket di supporto IT. Questo scenario rappresenta un classico caso d'uso per sistemi RAG aziendali: l'utente cerca soluzioni interrogando un database di problemi passati e relative procedure di risoluzione.

L'impiego di documenti tecnici strutturati permette di valutare oggettivamente l'utilità delle informazioni rilasciate. Una risposta utile deve contenere passaggi procedurali specifici o indicazioni risolutive presenti nei documenti locali e non generabili dal modello cloud basandosi unicamente sulla conoscenza generale. Nei test, il corpus viene trattato come sintetico e non viene esposto, conformemente alle regole di protezione dei dati, ma rappresenta fedelmente le caratteristiche lessicali e la densità informativa di un archivio aziendale.

## 3.3 Configurazioni a confronto e protocollo degli esperimenti

Gli esperimenti mirano a confrontare le prestazioni del sistema operante con lo scheduler adattivo rispetto a configurazioni in cui il numero di generazioni locali $N$ è fissato in modo statico (baseline sperimentali). 

Il protocollo sperimentale prevede l'esecuzione di interrogazioni analoghe in tre scenari distinti:
1. **Configurazione statica a basso carico:** impiega un numero fisso minimo di generazioni, riducendo i tempi ma compromettendo la solidità dell'istogramma.
2. **Configurazione statica ad alto carico:** impiega un numero elevato di generazioni per massimizzare la probabilità di rilascio, fornendo un limite superiore per i tempi di risposta.
3. **Configurazione adattiva:** demanda allo scheduler il calcolo di $N$ per rispettare un determinato SLA (es. risposta entro pochi secondi). Con il parametro `--sforamento-k` (default 0), lo scheduler può accettare uno sforamento previsto entro la tolleranza $k \times E2E\_cloud\_ms$ pianificando comunque $N=5$; con `--force-zero-shot` si impone esplicitamente $N=0$.

Il retrieval è deterministico a parità di query e corpus: gli stessi documenti producono le stesse selezioni. Il parametro `--seed` resta disponibile per compatibilità con le versioni precedenti del prototipo.

## 3.4 Metriche, raccolta delle misure e osservabilità con Langfuse

L'analisi sperimentale si basa sulla misurazione congiunta di parametri prestazionali e qualitativi.

Dal punto di vista architetturale, vengono rilevati il tempo stimato dallo scheduler e il tempo di elaborazione effettivamente misurato sul nodo locale. Il tempo di prefill (time to first token, TTFT) è disponibile in due forme: una stima euristica basata su un fattore costante (`tempo_prefill_stimato_sec`), sempre disponibile, e una misura reale ottenuta via streaming da llama.cpp (`tempo_prefill_reale_sec`), disponibile quando il modello è attivo. La stima euristica è quella utilizzata dallo scheduler per le decisioni; la misura reale è diagnostica sperimentale. Il tempo totale di richiesta (`request_ms`) comprende retrieval, filtro, inferenza ed eventuale setup del modello, ma esclude l'ingestione del corpus e il probe di sessione. Il tempo CLI complessivo (`cli_total_ms`) include anche questi ultimi.

La calibrazione automatica delle velocità locali, eseguita all'avvio della sessione, produce i valori `prefill_tps` e `generation_tps` effettivamente usati dallo scheduler. Il suo costo (`calibration_ms`) è riportato separatamente dal tempo delle singole richieste. Il probe cloud E2E (`cloud_probe_ms`) misura la latenza end-to-end di una sola chiamata pubblica e alimenta la tolleranza dello scheduler; il suo costo entra in `cli_total_ms` ma non in `request_ms`.

Per valutare l'utilità, si osserva la quantità e la pertinenza dei termini che riescono a superare il test Propose-Test-Release dell'algoritmo DP-KSA. Le etichette sperimentali (`core.etichette`) classificano ogni risultato come `insufficienti` (rilascio vuoto o zero-shot), `errore` (provider non disponibile), `completo` (keyword rilasciate e riutilizzate nella risposta) o `degradato` (rilascio presente ma euristiche di completezza non soddisfatte). Queste label sono metadati di analisi, non meccanismi di controllo del flusso.

La telemetria hardware (`core.telemetry_hw`) raccoglie snapshot del dispositivo prima e dopo ogni run (temperatura CPU/GPU, utilizzo, RAM, VRAM, Watt, memory pressure) e, opzionalmente, campioni continui durante l'esecuzione su thread separato.

La raccolta delle metriche e l'osservabilità del sistema sono supportate dall'integrazione di Langfuse. Per gli scopi di questa tesi e nell'esclusivo ambito di dati di prova autorizzati, Langfuse cattura i tempi di esecuzione, gli istogrammi intermedi e le decisioni del filtro di privacy. Questa telemetria diagnostica, benché non partecipi alla sicurezza del meccanismo differenziale, è indispensabile per la validazione sperimentale delle stime e per la dimostrazione del comportamento dello scheduler adattivo.

## 3.5 Verifiche di correttezza e riproducibilità

Una parte rilevante del lavoro sperimentale consiste nella verifica di correttezza delle assunzioni, garantita attraverso una suite di test automatizzati. La suite completa comprende 181 test che coprono tutti i moduli del prototipo, con una copertura del modulo `core.scheduler` superiore al 97%. I controlli statici (`ruff`) sono sempre a zero warning.

Le invarianti fondamentali includono la verifica empirica della scala del rumore Gumbel introdotto nel meccanismo FindBestK (confermata tramite test statistici su 10.000 campioni), il corretto funzionamento del meccanismo di reiezione (fallback zero-shot) quando l'algoritmo di stabilità fallisce o il budget è esaurito, e l'invariante di conservazione del budget privacy ($\epsilon_{consumato} + \epsilon_{rimasto} = \epsilon_{budget}$) dopo ogni invocazione del filtro.

Un audit formale condotto il 9 settembre 2026 ha verificato 38 punti di controllo sulla correttezza del meccanismo DP, sull'isolamento dei dati privati e sulla qualità del software, senza rilevare non conformità.

Queste verifiche assicurano che i risultati prestazionali discussi successivamente poggino su una solida base formale, garantendo che i tempi di risposta registrati non siano ottenuti a discapito dell'integrità del sistema di privacy.
