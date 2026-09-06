# Configuration And External Providers

## Modello locale

`core.model_config` è la fonte unica per il workload locale condiviso da
`LocalNeuralEngine` e `benchmark_tokens.py`: nome file, URL predefinito,
prompt, `n_ctx`, `n_gpu_layers`, `max_tokens`, stop sequence e rapporto della
stima prefill/generazione.

`model_path` è una destinazione locale, non un identificativo del modello. Se
il file esiste, viene usato senza download. Se manca, il file viene scaricato
da `model_url` e sostituito atomicamente solo dopo il controllo dello stream.
Per un modello diverso bisogna fornire entrambi:

```bash
.venv/bin/python run_pipeline.py \
  --model-path models/custom.gguf \
  --model-url https://models.example/custom.gguf
```

L’URL `main` di Hugging Face è il default del PoC e può cambiare nel tempo.
Per esperimenti riproducibili è preferibile un URL versionato e, in
produzione, un controllo SHA-256 aggiuntivo del file.

## Provider cloud

`CloudGenerator` parla il protocollo Chat Completions compatibile con OpenAI;
non assume che il provider sia OpenAI. Sono supportati provider SaaS,
gateway aziendali e server locali compatibili.

Priorità delle configurazioni:

| Opzione | Argomento CLI | Variabile ambiente | Default |
| --- | --- | --- | --- |
| Chiave | `--api-key` | `CLOUD_API_KEY`, poi `OPENAI_API_KEY` | simulazione se assente |
| Endpoint | `--cloud-base-url` | `CLOUD_BASE_URL`, poi `OPENAI_BASE_URL` | endpoint SDK |
| Modello | `--cloud-model` | `CLOUD_MODEL`, poi `OPENAI_MODEL` | `gpt-4o-mini` |

Un endpoint locale senza autenticazione può essere usato indicando soltanto
`CLOUD_BASE_URL`; il client riceve una chiave tecnica `not-needed` perché
alcune implementazioni OpenAI-compatible la richiedono sintatticamente.

Quando non è presente né una chiave né un endpoint, il PoC usa la risposta
simulata offline. Gli errori del provider vengono registrati nei log con la
causa completa, ma l’API restituisce un messaggio generico e
`errore="provider_error"`, evitando di esporre dettagli interni nel risultato.
`KeyboardInterrupt` e `SystemExit` non vengono intercettati.

## Langfuse

Il tracer è opzionale e si attiva soltanto con entrambe le credenziali:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_CAPTURE_SENSITIVE=false
```

`LANGFUSE_HOST` può puntare a una installazione self-hosted. La modalità
redatta è il default anche quando il tracer remoto è attivo. Per un ambiente
locale fidato si può abilitare la diagnostica completa:

```env
LANGFUSE_HOST=http://langfuse.local:3000
LANGFUSE_CAPTURE_SENSITIVE=true
```

In alternativa, per una singola esecuzione:

```bash
.venv/bin/python run_pipeline.py --langfuse-capture-sensitive
```

La diagnostica completa include query, bozze locali, conteggi istogramma,
token scartati e risposta finale. Non va abilitata verso un servizio remoto
non incluso nel perimetro di fiducia della tesi.
