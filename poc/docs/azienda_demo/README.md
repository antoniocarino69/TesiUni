# Documenti salariali per prove locali

Questa cartella contiene 80 schede di una società inventata, **Aurora Demo
Srl**. Sono file locali utilizzabili dalla pipeline, ma tutti i dati sono
sintetici: non sono cedolini reali e non descrivono dipendenti esistenti.

| Reparto | Livello | Documenti | Retribuzione annua lorda base |
| --- | --- | ---: | ---: |
| Tecnologia | T2 | 40 | 42000 euro |
| Amministrazione | A1 | 20 | 36000 euro |
| Commerciale | C2 | 20 | 30000 euro |

Ogni scheda rappresenta un dipendente fittizio distinto, con identificativo,
sede, anno di assunzione, progetto e bonus. La base è costante nel reparto;
bonus e totale annuo variano. Questo serve a distinguere l'importo richiesto
dagli altri importi presenti. Il netto non compare: è un controllo negativo
per verificare se il modello sa astenersi.

La distribuzione è intenzionale. Tecnologia ha abbastanza documenti pertinenti
per N=40; gli altri reparti ne hanno 20. Si può quindi osservare cosa accade
quando aumentare N introduce documenti non pertinenti. Questi risultati non
stimano la distribuzione degli stipendi o la qualità su un'azienda reale.

## File da usare

- `documenti/`: solo le 80 schede Markdown da dare al retriever.
- `cases.json`: tre domande sulla base lorda e una domanda sul netto assente.
- `manifest.json`: risposte note, appartenenza ai reparti e impronte dei file.
- `RISULTATI.md`: risultati e limiti delle prove effettuate.

Passare **solo `documenti/`** a `--documents`. Questo README e i risultati non
devono entrare nell'ensemble. Non inserire qui cedolini personali: questa è
una fixture pubblica versionata nel repository. I documenti privati hanno la
cartella separata `poc/private_documents/`, esclusa da Git.

## Prova dalla CLI

Eseguire i comandi da `poc/`:

```bash
.venv/bin/python run_pipeline.py \
  --documents docs/azienda_demo/documenti \
  --query "Qual è la retribuzione annua lorda base del personale del reparto Tecnologia, livello T2, di Aurora Demo Srl? Scrivi soltanto l’importo intero in euro senza separatori." \
  --max-latency-ms 30000 --dry-run
```

Per una richiesta completa con inferenza locale reale e cloud simulato:

```bash
.venv/bin/python run_pipeline.py \
  --documents docs/azienda_demo/documenti \
  --query "Qual è la retribuzione annua lorda base del personale del reparto Tecnologia, livello T2, di Aurora Demo Srl? Scrivi soltanto l’importo intero in euro senza separatori." \
  --fixed-n 40 --epsilon 4 --max-latency-ms 30000 \
  --offline-cloud --no-telemetry --output reports/azienda_demo_request.json
```

Con N fisso si esegue la baseline anche quando la stima supera lo SLA: il
report dichiara la non fattibilità stimata. Senza `--fixed-n`, lo scheduler
decide N usando i suoi parametri pubblici. Ai default di 1,5 secondi va in
zero-shot; alzare lo SLA o utilizzare la baseline esplicita consente di
esercitare il modello. Aumentare epsilon indebolisce la protezione: i valori
di prova servono a studiare il compromesso, non sono consigli per dati reali.

## Esperimento locale ripetibile

Il runner dedicato controlla che i file corrispondano al corpus sintetico,
non carica `.env`, non inizializza Langfuse e forza il cloud offline. Richiede
il GGUF già presente, senza scaricarlo automaticamente.

```bash
.venv/bin/python benchmark_salary_demo.py --mode filter --trials 500 \
  --output reports/azienda_demo_filter.json

.venv/bin/python benchmark_salary_demo.py --mode scheduler --repeats 3 \
  --output reports/azienda_demo_scheduler.json
```

La modalità `filter` fa 160 inferenze reali: 40 documenti per quattro query.
Riutilizza poi queste bozze per 500 estrazioni del filtro per ciascuna
combinazione di N=5/10/20/40 ed epsilon=1/4/8. Sono 24000 prove del filtro,
**non** 24000 richieste complete o misure di latenza. I seed servono soltanto
alla diagnostica locale su dati pubblici. Non si rivendica una garanzia DP
complessiva per le repliche diagnostiche. Le quattro richieste della pipeline
condividono invece il proprio account cumulativo.

La modalità `scheduler` usa la query Tecnologia e confronta adattivo,
N=5, N=20 e N=40, ciascuno con tre richieste reali a modello precaricato.
La calibrazione è epsilon=4 per richiesta; l'account è unico per la sessione.
L'ordine è mescolato con seed fisso, ma il rumore delle richieste resta casuale.
I tempi possono cambiare tra esecuzioni. Il cloud è simulato: la qualità della
risposta finale rimane `null` e le latenze non comprendono un provider reale.

I report dettagliati in `reports/` restano locali e ignorati da Git. Contengono
anche le bozze, utili per distinguere un errore del modello da un mancato
rilascio. La copertura delle risposte attese è una ricerca testuale di token
completi, non una valutazione semantica.

## Rigenerazione

```bash
.venv/bin/python scripts/create_salary_demo.py
```

La generazione è deterministica. Una seconda esecuzione lascia invariati i
file uguali e si interrompe se trova una scheda modificata manualmente. Per
una variante, usare `--output` con una nuova cartella e aggiornare insieme
domande e risposte attese; il runner dedicato resta riservato alla fixture
originale, mentre `run_pipeline.py` accetta un percorso locale a scelta.
