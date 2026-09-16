# Concezione sperimentale del prototipo

Questo documento fissa il taglio operativo della tesi per i cinque punti di
chiusura elencati in `AGENTS.md` ("Priorità del progetto e obiettivo di
latenza"). Non introduce un capitolo nuovo né modifica l'indice approvato del
relatore, descritto in `struttura.md`. Si limita a dichiarare in modo
operativo il carattere sperimentale del prototipo e i punti di intervento
sulla base di codice esistente.

## 1. Premessa

La tesi è uno **studio sperimentale** del costo computazionale e temporale
del filtro DP-KSA di Tang et al. in un'architettura edge-cloud, e del ruolo
di uno scheduler adattivo come variabile di controllo. Il prototipo è lo
strumento di misura della tesi, non un sistema destinato alla produzione.

Conseguenze immediate:

- non esiste un'utenza finale da proteggere con un comportamento di servizio.
  Le etichette "risposta degradata", "insufficienti", "errore" sono
  **metadati di analisi**, non branching del flusso utente;
- le funzioni descritte come "Sviluppi concordati, ancora da implementare"
  in `pseudocodice.md` e in `schemaablocchi.md` (calibrazione delle stime,
  riesame del fallback N=0, preferenza per una dichiarazione di insufficienza
  delle informazioni) entrano nella **metodologia sperimentale** del
  capitolo 3 e diventano oggetto di misura nel capitolo 4. Non sono più
  sviluppi futuri;
- il setup di sessione (calibrazione locale e probe cloud) è parte della
  procedura di misura, distinto dal costo delle singole richieste. Viene
  eseguito una volta per sessione sperimentale e il suo tempo viene riportato
  a parte, non nascosto dentro `cli_total_ms`.

L'indice dei capitoli rimane quello di `struttura.md`. Le sezioni toccate
dalla concezione sono elencate al punto 6 di questo documento; nessuna di
esse richiede un nuovo capitolo.

## 2. Setup di sessione

Per sessione si intende l'insieme delle prove che condividono lo stesso
modello locale precaricato e le stesse misure di latenza cloud. Il setup
viene eseguito una sola volta all'inizio della sessione e produce due valori
pubblici che alimentano lo scheduler.

### 2.1 Calibrazione locale delle velocità di inferenza

Vengono eseguite alcune generazioni di prova (tre-cinque) su testi pubblici
non derivati dal corpus sotto esame, a lunghezze rappresentative dei prompt
previsti (256, 512, 1024 token). Da queste generazioni si calcolano:

- `prefill_tps`: token di prompt al secondo, distinti per classe di lunghezza
  se la variabilità lo richiede;
- `generation_tps`: token di completamento al secondo.

Le misure sono mantenute in memoria per tutta la sessione e non vengono
riusate fra sessioni diverse: la calibrazione ha senso solo sulla stessa
macchina, nello stesso regime termico e con la stessa versione del modello.

Il costo del setup viene riportato come `calibration_ms`, distinto da
`request_ms` e da `cli_total_ms`. La CLI lo stampa in una riga separata.

Disattivazione esplicita: `--no-calibration` ripristina i valori di default
(`prefill=250 t/s`, `generation=50 t/s`) documentati in `CONFIGURATION.md`.
Serve a verificare l'effetto della calibrazione sui risultati, non a essere
usato di routine.

### 2.2 Probe cloud di latenza

Viene eseguita una sola generazione breve pubblica per sessione, con un
prompt che non contiene contenuti privati. La misura registra la latenza
end-to-end della chiamata (`E2E_cloud_ms`) e, quando il client lo espone, il
tempo al primo token (`TTFT_cloud_ms`). Nessun retry, nessuna somma
separata di rete e generazione: il valore è quello che il client vede.

Il probe va sempre eseguito in presenza di credenziali e di un endpoint
configurato. Con `--offline-cloud` il probe è saltato e il valore di
`tempo_cloud_ms` è esplicitamente assunto come stima, marcato nel report
JSON come `cloud_probe_skipped: true`.

Il costo del probe entra in `cli_total_ms` ma non in `request_ms` delle
singole richieste successive, e viene riportato come `cloud_probe_ms`. Anche
il valore della query di probe entra solo in modalità `capture_sensitive`
di Langfuse, e comunque è un prompt pubblico scelto a priori.

## 3. Soglia di sforamento accettabile

L'obiettivo è distinguere uno sforamento "significativo" da una variabilità
naturale del sistema, senza imporre un vincolo rigido che il prototipo non
può garantire. La formula di partenza, da validare sperimentalmente con
uno sweep su `k`, è:

```
budget_sforamento_ms = k · (RTT_ms + E2E_cloud_ms)
margine_ms = SLA_ms - (RTT_ms + E2E_cloud_ms + stima_locale_ms)
accetta_sforamento = margine_ms < budget_sforamento_ms
```

`RTT_ms` ed `E2E_cloud_ms` provengono dal setup di sessione (§2.2);
`stima_locale_ms` è la somma dei tempi stimati per le inferenze locali del
piano corrente, calcolata come nell'implementazione esistente di
`core/scheduler.py`. `SLA_ms` è il vincolo temporale configurato per la
sessione.

Quando `accetta_sforamento` è vero, lo scheduler non rinuncia al piano
minimo: sceglie comunque `n_ensemble = N_MIN` e marca la decisione con
`sforamento_accettato=True` e con il valore di `margine_ms` nel campo
`motivazione`. Lo sforamento è quindi visibile nei report e discusso nel
capitolo 4, non mascherato da un fallback.

Quando `accetta_sforamento` è falso, lo scheduler adotta il valore
`n_ensemble` determinato dal modello dei tempi entro l'SLA. `N=0` resta una
**opzione esplicita** della CLI (`--force-zero-shot`) e un **fallback
automatico** quando il budget privacy è esaurito (`PrivacyBudgetExhaustedError`).
Non è più il comportamento di default per SLA incompatibile.

Il coefficiente `k` è il parametro sperimentale della concezione. Valori
ragionevoli per una prima esplorazione sono `k ∈ {0, 0.1, 0.25, 0.5}`.
Per `k = 0` il comportamento coincide con l'attuale: l'unico modo per
accettare lo sforamento è forzarlo con `--force-zero-shot` disattivato.
Per `k > 0` la soglia cresce linearmente con la somma di `RTT_ms` ed
`E2E_cloud_ms`, riflettendo l'idea che la variabilità naturale del sistema
è proporzionale alla parte più rumorosa della catena.

## 4. Etichette sperimentali

Tre etichette affiancano il risultato della richiesta nei report JSON e nei
trace Langfuse, calcolate a posteriori da euristiche locali non-DP:

- `completo`: il filtro ha rilasciato keyword e il cloud ha restituito un
  testo coerente con la query;
- `insufficienti`: il filtro non ha rilasciato keyword. In questo caso il
  cloud non riceve contenuti utili per rispondere e il suo output, quando
  presente, è dichiarato come **non fondato sui documenti**. Il prompt
  cloud include una nota esplicita su questa condizione;
- `errore`: provider cloud non disponibile o risposta vuota;
- `degradato`: il filtro ha rilasciato keyword ma la risposta cloud non le
  utilizza in modo coerente. Rilevato da un controllo locale (numero di
  keyword presenti nel testo, presenza di frasi "non lo so" o equivalenti).

Queste etichette **non modificano il flusso del prototipo**. Non sono
branching condizionali sul prompt, non cambiano la query al provider, non
producono risposte diverse per l'utente. Servono alla discussione del
capitolo 4 sull'effetto del rilascio sull'utilità percepita.

Le euristiche che le calcolano sono disattivabili da CLI e dichiarate
esplicitamente in `CONFIGURATION.md`. La tesi non rivendica per esse alcuna
proprietà di privacy o di qualità.

## 5. Cosa resta invariato

La concezione non modifica nessuno dei seguenti elementi:

- l'indice e l'articolazione dei capitoli di `struttura.md`;
- il ruolo del prototipo come strumento di misura del capitolo 4;
- l'interfaccia pubblica dei moduli in `poc/core/`, in particolare
  `run_pipeline.py`, `run_request`, `AdaptiveScheduler.schedule`;
- i 86 test esistenti (`pytest -v` deve restare verde senza modifiche);
- la garanzia del filtro DP-KSA, le ipotesi di adiacenza, la calibrazione
  del rumore Gumbel a scala `4/ε` documentata in `PRIVACY_ACCOUNTING.md`;
- il rifiuto di inviare contesti grezzi al cloud;
- la distinzione fra traccia diagnostica e rilascio protetto.

Le modifiche al codice sono additive: nuovi parametri opzionali, nuovi
campi nei dataclass esistenti, nuovi report in `run_request`. Nessuna
funzione esistente cambia semantica senza un branch esplicito.

## 6. Effetti sulla base di codice e sulla documentazione esistente

Per ogni punto della concezione, il punto di intervento previsto è:

| Punto | File principali | Documenti da aggiornare |
| --- | --- | --- |
| Calibrazione locale | nuovo `poc/core/calibration.py`; `core/scheduler.py` per il fallback ai default; `run_pipeline.py` per `--no-calibration` | `CONFIGURATION.md`, `Bozza/02_Capitolo2.md` §2.4, `Bozza/03_Capitolo3.md` §3.1 |
| Probe cloud | `core/cloud.py` per il metodo di probe; `core/pipeline.py` o modulo analogo per il caching di sessione; `run_pipeline.py` per i flag | `CONFIGURATION.md`, `Bozza/03_Capitolo3.md` §3.1 |
| Soglia di sforamento | `core/scheduler.py` per la formula; nuovo modulo `poc/docs/esplorazione_soglia/` per lo sweep su `k` | `Bozza/02_Capitolo2.md` §2.5, `Bozza/04_Capitolo4.md` §4.2 |
| Etichette sperimentali | `core/cloud.py` per il campo `esito` in `RisultatoCloud`; `core/pipeline.py` per il calcolo a posteriori | `Bozza/03_Capitolo3.md` §3.4, `Bozza/04_Capitolo4.md` §4.4 |
| Aggiornamento testi di sintesi | `pseudocodice.md`, `schemaablocchi.md` (sezione "Sviluppi concordati" → "Setup di sessione") | i due file stessi |

Nessun file in `poc/archive/` viene toccato. Nessun test viene rimosso.
Il workflow git documentato in `AGENTS.md` (branch dedicato, merge `--no-ff`)
resta la procedura operativa per ciascuno dei punti sopra.

## 7. Limiti dichiarati

La concezione non promette quanto non può mantenere:

- la calibrazione delle velocità misura la macchina della sessione, non
  una classe di dispositivi. Riprodurre le misure su hardware diverso
  richiede una nuova calibrazione;
- il probe cloud misura il provider e l'endpoint configurati, non un
  modello di latenza universale. Cambiare provider o modello richiede un
  nuovo probe;
- la formula della soglia di sforamento è un'ipotesi di lavoro. Lo sweep
  su `k` produce i primi dati sperimentali per discuterla, non una scelta
  definitiva. Il capitolo 4 riporterà i risultati e le eventuali revisioni;
- le etichette sperimentali sono descrittive, non normative. Non è
  ragionevole dire che una risposta "degradata" non possa essere utile, né
  che una risposta "completa" sia corretta.
