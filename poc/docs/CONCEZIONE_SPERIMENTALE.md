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
sforamento_previsto_ms = max(0, stima_totale_ms - SLA_ms)
tolleranza_ms = k · E2E_cloud_ms
accetta_sforamento = sforamento_previsto_ms <= tolleranza_ms
```

dove `stima_totale_ms = stima_locale_ms + E2E_cloud_ms` e `stima_locale_ms`
è calcolata come nell'implementazione esistente di `core/scheduler.py`.
La formula confronta la quantità di sforamento **previsto** con la
tolleranza, entrambe espresse in millisecondi e mai negative.

`E2E_cloud_ms` è la latenza end-to-end misurata dal probe (§2.2). Non si
aggiunge separatamente un RTT: il probe misura già l'intera chiamata
cloud, e una seconda componente di rete nella formula sarebbe un doppio
conteggio. Anche `TTFT_cloud_ms`, quando esposto dal client, viene
registrato a parte per analisi ma non rientra nella soglia.

Quando `accetta_sforamento` è vero, lo scheduler non rinuncia al piano
minimo: sceglie comunque `n_ensemble = N_MIN` e marca la decisione con
`sforamento_accettato=True` e con il valore di `sforamento_previsto_ms`
nel campo `motivazione`. Lo sforamento è quindi visibile nei report e
discusso nel capitolo 4, non mascherato da un fallback.

Quando `accetta_sforamento` è falso, lo scheduler adotta il valore
`n_ensemble` determinato dal modello dei tempi entro l'SLA. `N=0` resta una
**opzione esplicita** della CLI (`--force-zero-shot`) e un **fallback
automatico** quando il budget privacy è esaurito (`PrivacyBudgetExhaustedError`).
Non è più il comportamento di default per SLA incompatibile.

Il coefficiente `k` è il parametro sperimentale della concezione. Una sola
chiamata di probe non è sufficiente a caratterizzare la variabilità del
provider, quindi `k` non è calibrato in modo chiuso: è oggetto di sweep
sperimentale su `k ∈ {0, 0.1, 0.25, 0.5}`. Per `k = 0` la tolleranza è
zero e lo scheduler non accetta mai sforamento spontaneamente; serve
`--force-zero-shot` o un budget privacy esaurito per arrivare a `N = 0`.
Per `k > 0` la tolleranza cresce linearmente con `E2E_cloud_ms`,
riflettendo l'ipotesi che la variabilità naturale del sistema sia
proporzionale alla parte cloud della catena. I risultati dello sweep
andranno riportati in `poc/docs/esplorazione_soglia/` e discussi nel
capitolo 4 prima di scegliere un valore definitivo.

## 4. Etichette sperimentali

Quattro etichette affiancano il risultato della richiesta nei report JSON
e nei trace Langfuse. Sono **calcolate a posteriori** da euristiche locali
non-DP, applicate sul testo già ricevuto dal provider o sulla risposta
cloud non ancora prodotta. Non modificano il prompt, la query, la
sequenza di chiamate o il comportamento del prototipo: sono metadati di
analisi per la discussione del capitolo 4.

Le euristiche che le calcolano sono:

- `insufficienti`: il filtro DP-KSA non ha rilasciato keyword. È una
  pura osservazione del rilascio: se la lista è vuota, l'etichetta è
  `insufficienti`. Non altera il prompt cloud;
- `errore`: il provider cloud non era disponibile o ha restituito una
  risposta vuota;
- `completo`: il filtro ha rilasciato keyword **e** la risposta cloud le
  riutilizza in modo coerente. L'euristica è operativa: almeno una delle
  keyword rilasciate compare nel testo della risposta, **e** la risposta
  non contiene pattern di astensione noti (frasi del tipo "non lo so",
  "non è possibile rispondere con queste informazioni", "informazioni
  insufficienti"). Per il caso ticket l'euristica è più stretta: deve
  essere presente almeno un passaggio della procedura attesa e i
  passaggi devono comparire nell'ordine previsto dal riferimento;
- `degradato`: il filtro ha rilasciato keyword e la risposta cloud è
  arrivata, ma le euristiche di `completo` non sono soddisfatte. È il
  caso in cui il rilascio non basta a produrre una risposta utilizzabile.

Queste euristiche sono disattivabili da CLI e i loro parametri sono
dichiarati in `CONFIGURATION.md`. La tesi non rivendica per esse alcuna
proprietà di privacy, di correttezza o di garanzia di qualità. Possono
produrre falsi positivi e falsi negativi; servono a raggruppare i
risultati per discuterli, non a certificare lo stato della risposta.

## 5. Cosa resta invariato e cosa va aggiornato

La concezione non modifica l'indice dei capitoli, il ruolo del prototipo
come strumento di misura, la garanzia del filtro DP-KSA, le ipotesi di
adiacenza, la calibrazione del rumore Gumbel a scala `4/ε` documentata
in `PRIVACY_ACCOUNTING.md`, il rifiuto di inviare contesti grezzi al
cloud e la distinzione fra traccia diagnostica e rilascio protetto.

I test esistenti vanno aggiornati per riflettere il nuovo default
operativo:

- `tests/test_scheduler.py::test_impossible_sla_skips_retrieval_and_engine`
  documenta il comportamento "SLA incompatibile → N = 0". Il nuovo
  default accetta lo sforamento entro la tolleranza, quindi il test va
  aggiornato al nuovo significato e il comportamento precedente va
  conservato in un test distinto che lo verifica esplicitamente quando
  `k = 0` o quando è attiva la baseline di confronto;
- eventuali altri test che si appoggiano al fallback automatico vanno
  riesaminati con lo stesso criterio.

Le modifiche al codice sono additive: nuovi parametri opzionali, nuovi
campi nei dataclass esistenti, nuovi report in `run_request`. Nessuna
funzione esistente cambia semantica senza un ramo di confronto che
conservi esplicitamente il comportamento precedente.

## 6. Effetti sulla base di codice e sulla documentazione esistente

Per ogni punto della concezione, il punto di intervento previsto è:

| Punto | File principali | Documenti da aggiornare |
| --- | --- | --- |
| Calibrazione locale | nuovo `poc/core/calibration.py`; `core/scheduler.py` per il fallback ai default; `run_pipeline.py` per `--no-calibration` | `CONFIGURATION.md`, `Bozza/02_Capitolo2.md` §2.4, `Bozza/03_Capitolo3.md` §3.1 |
| Probe cloud | `core/cloud.py` per il metodo di probe; `core/pipeline.py` o modulo analogo per il caching di sessione; `run_pipeline.py` per i flag | `CONFIGURATION.md`, `Bozza/03_Capitolo3.md` §3.1 |
| Soglia di sforamento | `core/scheduler.py` per la formula; nuovo modulo `poc/docs/esplorazione_soglia/` per lo sweep su `k` | `Bozza/02_Capitolo2.md` §2.5, `Bozza/04_Capitolo4.md` §4.2 |
| Etichette sperimentali | `core/cloud.py` per il campo `esito` in `RisultatoCloud`; `core/pipeline.py` per il calcolo a posteriori | `Bozza/03_Capitolo3.md` §3.4, `Bozza/04_Capitolo4.md` §4.4 |
| Aggiornamento testi di sintesi | `pseudocodice.md`, `schemaablocchi.md` (sezione "Sviluppi concordati" → "Setup di sessione") | i due file stessi |

Nessun file in `poc/archive/` viene toccato. Nessun test viene rimosso;
i test esistenti vengono aggiornati come descritto al §5. Il workflow
git documentato in `AGENTS.md` (branch dedicato, merge `--no-ff`) resta la
procedura operativa per ciascuno dei punti sopra.

## 8. Stato delle funzionalità

I cinque punti della concezione (calibrazione locale, probe cloud,
formula della soglia di sforamento, etichette sperimentali, sweep su `k`)
sono interventi **previsti dalla metodologia sperimentale** della tesi.
Finché non risultano implementati nel codice e verificati dai test,
vanno descritti nella tesi come previsti, non come funzionalità
disponibili. La narrativa del capitolo 4 deve restare coerente con
questa distinzione: i risultati del prototipo attuale sono quelli delle
campagne descritte in `poc/docs/azienda_demo/RISULTATI.md` e
`poc/docs/ticket_demo/RISULTATI.md`; i risultati degli interventi
previsti saranno oggetto di una campagna successiva, da eseguire prima
di qualsiasi conclusione che li riguardi.

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
