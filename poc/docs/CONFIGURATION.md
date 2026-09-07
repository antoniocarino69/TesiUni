# Configurazione ed esperimenti

Eseguire i comandi dalla directory `poc/` con `.venv/bin/python`.

## Documenti locali

```bash
.venv/bin/python run_pipeline.py --documents ./private_documents \
  --query "Qual è la scadenza del progetto?" --dry-run

.venv/bin/python run_pipeline.py --documents ./private_documents \
  --query "Qual è la scadenza del progetto?" \
  --max-latency-ms 60000 --prompt-token-budget 1000 \
  --offline-cloud --no-telemetry --output reports/request.json
```

`--documents` accetta un file o una directory TXT, Markdown, PDF testuali.
La query è obbligatoria. Sono letti soltanto i percorsi indicati; i contenuti
restano sul computer. `--dry-run` valida corpus e piano senza modello, provider
o trace. `--offline-cloud` forza la simulazione anche se `.env` contiene chiavi;
l'inferenza locale, se pianificata, richiede comunque il modello GGUF.
Con pochi documenti non vengono inventati voti: gli slot mancanti sono vuoti,
e il filtro può spesso scegliere di non rilasciare keyword.

Senza `--documents`, si usa il benchmark pubblico incluso, oppure il JSON
indicato con `--dataset`. La query predefinita è pubblica e fissa:
`Who won Super Bowl 50?`. `--seed` è mantenuto per compatibilità ma non cambia
il retrieval deterministico. L'API di campionamento del dataset conserva
invece il seed opzionale.

## Parametri del piano

| Opzione | Default | Interpretazione |
| --- | ---: | --- |
| `--ensemble-size` | 40 | Slot pubblici candidati, fra 5 e 40 |
| `--prompt-token-budget` | 1000 | Cap del prompt completo, inclusi query e template |
| `--max-tokens` | 30 | Massimo output per documento |
| `--max-latency-ms` | 1500 | SLA confrontato con stima e tempo misurato della richiesta |
| `--rtt-ms`, `--tempo-cloud-ms` | 50, 150 | Stime di rete e cloud, non sonde automatiche |
| `--tok-per-sec-prefill`, `--tok-per-sec-generazione` | 250, 50 | Throughput configurati pubblicamente |
| `--epsilon` | 1 | Budget epsilon della singola richiesta |
| `--delta` | 1e-4 | Delta PTR; default delta totale 2e-4 |
| `--r-min-k`, `--r-max-k` | 1, 10 | Dominio pubblico per risposte brevi |
| `--fixed-n` | assente | Baseline sperimentale che esegue N anche oltre lo SLA stimato |

Con i default, cinque prompt da 1000 token non entrano in 1,5 secondi:
l'adattivo va in zero-shot. Aumentare lo SLA in modo coerente con l'hardware
oppure misurare throughput migliori, senza inventare valori per ottenere N.
La probabilità PTR per gap=3 è un riferimento analitico, non una previsione.

## Modello e provider

`core.model_config` contiene prompt, `n_ctx`, stop, generazione e stima prefill.
`--model-path` sceglie il GGUF locale; se manca viene scaricato da `--model-url`
(default Qwen su Hugging Face). Usare un URL versionato per esperimenti
ripetibili. Il download è atomico e verifica la lunghezza HTTP disponibile.

Il provider riceve query e keyword alfabetiche. La scelta avviene con:

| CLI | Ambiente |
| --- | --- |
| `--api-key` | `CLOUD_API_KEY`, poi `OPENAI_API_KEY` |
| `--cloud-base-url` | `CLOUD_BASE_URL`, poi `OPENAI_BASE_URL` |
| `--cloud-model` | `CLOUD_MODEL`, poi `OPENAI_MODEL` (default `gpt-4o-mini`) |

Senza endpoint e chiavi il cloud è simulato. `--offline-cloud` prevale su tutti
questi valori. Errori del provider producono un report con `provider_error` e
codice di uscita 4. Le simulazioni sono identificate e non contengono una
risposta fattuale da valutare.

## Langfuse per la tesi

Il tracing è opzionale e richiede `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY`.
`LANGFUSE_HOST` può essere il servizio cloud o un endpoint locale. In questa
fase serve visibilità sperimentale: l'utente può dimostrare gli assunti su dati
pubblici o autorizzati anche con Langfuse cloud. Non viene richiesta adesso
un'installazione locale. In un deployment riservato si userebbe Langfuse locale.

La modalità predefinita è redatta. Per la diagnostica completa usare
`LANGFUSE_CAPTURE_SENSITIVE=true` oppure `--langfuse-capture-sensitive`.
Contiene informazioni non privatizzate: questo è dichiarato nei trace e non
estende la garanzia DP alle misure sperimentali. `--no-telemetry` disabilita
il tracer per la richiesta. Non versionare `.env` o i report riservati.

## Confronto adattivo / fisso

Preparare un JSON di casi pubblici con risposte attese:

```json
[{"query": "Who won Super Bowl 50?", "references": ["Denver Broncos"]}]
```

```bash
.venv/bin/python benchmark_scheduler.py --documents ./private_documents \
  --cases examples/evaluation.json --fixed-sizes 5 10 20 40 --repeats 3 \
  --epsilon 1 --session-epsilon 10 --max-latency-ms 30000 \
  --output reports/comparison.json
```

Le query devono corrispondere ai documenti scelti. Il modello viene precaricato;
il seed controlla l'ordine dei confronti per ridurre l'effetto dell'ordine di
esecuzione. N, rilascio, tempi, violazioni dello SLA, errori ed exact match/F1
normalizzati sono salvati per ogni prova. Il riepilogo riporta frequenza di
rilascio, media e intervallo delle latenze, violazioni e F1 medio. La metrica
F1 è lessicale, non una valutazione completa della qualità semantica.
Con `--offline-cloud` la qualità vale `null`: non è una misura sul provider.

Ogni variante usa la stessa calibrazione per richiesta; l'account cumulativo
copre la sessione intera. Se il limite totale non basta, il report è parziale
ed espone `stopped_budget`; non va confrontato come se fosse completo.
Una sessione successiva sullo stesso corpus richiede composizione ulteriore.
I report sono diagnostica locale, non artefatti pubblicabili con garanzia DP.

`benchmark_tokens.py` resta uno studio su testo ripetuto artificialmente:
riporta tempi totali reali e prefill stimato. Il rapporto fra ultimo e primo
profilo è calcolato dalle misure; non è una conclusione generale sul TTFT.
