# Architettura del PoC

Il percorso supportato è `run_pipeline.py`; l'orchestrazione testabile è in
`core.pipeline.run_request`. I prototipi in `archive/` restano storici.

## Flusso della richiesta

1. L'utente indica una query pubblica e, per documenti propri, un percorso esplicito.
   L'ingestione avviene localmente. Non viene scandito automaticamente il vault.
2. Lo scheduler riceve un numero pubblico di slot e lo stesso limite pubblico
   di token per ogni prompt. Non riceve le lunghezze dei documenti recuperati.
3. Se le stime non consentono almeno cinque inferenze, la decisione è `zero_shot`,
   con `n_ensemble=0`: niente retrieval, modello locale o consumo del filtro.
   `sla_fattibile` indica se almeno la chiamata cloud entra nella stima.
4. Altrimenti il retriever sceglie N documenti originali distinti. Ogni documento
   contribuisce con un solo estratto e una sola risposta. Slot mancanti producono
   risposte vuote pubbliche; non si duplicano documenti per raggiungere N.
5. L'engine limita il prompt completo con il tokenizer reale, includendo query
   e template, e genera le bozze in sequenza.
6. FindBestK sceglie k sul dominio pubblico configurato; TopKWithPTR rilascia
   keyword in ordine alfabetico o una lista vuota.
7. Il cloud riceve soltanto query e keyword. Nel caso vuoto risponde usando la
   conoscenza generale, senza un'istruzione che lo vincoli a concetti assenti.

## Documenti e adiacenza

`core.documents` supporta TXT e Markdown UTF-8 e PDF con testo estraibile.
I PDF cifrati o senza testo producono un errore esplicito; l'OCR deve essere
eseguito localmente a monte. I file nascosti e i symlink nelle directory non
sono acquisiti. La normalizzazione degli spazi identifica copie esatte dello
stesso contenuto. Copie quasi identiche, versioni e fonti correlate richiedono
una definizione dell'unità protetta a monte: la deduplicazione non le risolve.

Il punteggio è il numero di termini della query presenti nell'estratto migliore
di ciascun documento. Gli estratti sono finestre di 400 parole; i pareggi sono
risolti con identificatori deterministici. Non vengono usati IDF del corpus,
embedding remoti o modelli addestrati sul corpus. Cambiare un documento non
cambia il punteggio né l'estratto degli altri. Con query e N fissi, il top-N
può sostituire al massimo un membro. L'ordine di esecuzione non entra
nell'istogramma; si assume generazione indipendente per ciascun prompt.

L'unità protetta è un documento originale normalizzato. I chunk non sono unità
indipendenti e più domande SQuAD sullo stesso contesto non sono più voti.
`DatasetLoader` conserva anche l'API di campionamento, ma la pipeline usa il
retrieval per query. Il benchmark incluso contiene 100 contesti distinti di
SQuAD 1.1, distribuiti nel corpus pubblico, rigenerabili con lo script dedicato.

## Scheduler e tempi

La stima sequenziale usa il limite pubblico del prompt e il massimo output:
`N * (prompt_cap / prefill_tps + max_tokens / generation_tps) + RTT + cloud`.
È una stima conservativa del workload, non una garanzia di latenza reale:
throughput, rete, caricamento del modello e costi accessori possono variare.
Le lunghezze effettive restano diagnostica locale e non cambiano N.
La modalità `fixed_n` è una baseline sperimentale: esegue N anche quando
`sla_fattibile=False`, per misurare le violazioni e confrontarle con l'adattivo.

Il campo storico `ptr_pass_rate_attesa` contiene soltanto `P(pass | gap=3)`.
Non è una previsione sul corpus e non descrive l'effetto di N. La frequenza di
rilascio effettiva si misura con esperimenti ripetuti.

`request_ms` misura il tempo dall'ingresso nello scheduler al ritorno del
cloud: comprende retrieval, filtro, inferenza e l'eventuale setup del modello.
Esclude ingestione del corpus e flush finale Langfuse. `cli_total_ms` comprende
anche questi ultimi, fino a prima della scrittura del report/stampa finale.
Il benchmark di confronto precarica il modello e dichiara misure a modello
caricato. `prefill_estimated_ms` resta un'euristica, non TTFT misurato.
I byte riportati misurano il testo del prompt e degli estratti usati, non JSON,
header, TLS, retry o traffico effettivo. Il cloud simulato ha durata provider
zero ed è sempre identificato come simulazione.

## Confine di fiducia

La garanzia del filtro riguarda il contenuto rilasciato al cloud sotto le
ipotesi documentate in `docs/PRIVACY_ACCOUNTING.md`. Non protegge automaticamente
report, console, tempi o trace. Langfuse è uno strumento di osservazione degli
esperimenti della tesi: l'istanza cloud è utilizzabile con i dati autorizzati
per la dimostrazione. Non è richiesta ora un'istanza locale. In un deployment
reale con dati riservati si userebbe Langfuse locale nel perimetro fidato.

La modalità redatta omette contenuti e statistiche dirette come dimensione
dell'istogramma e volume dei contesti. Conserva metriche operative e tempi:
non è presentata come un meccanismo DP. La diagnostica completa è disponibile
con `LANGFUSE_CAPTURE_SENSITIVE=true`. Errori di tracing non cambiano il
meccanismo. Nessun test deve utilizzare credenziali reali o inviare documenti.
