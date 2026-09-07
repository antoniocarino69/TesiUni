# DP-KSA con scheduler adattivo

Il PoC studia il compromesso fra latenza, numero di risposte locali e utilità
delle keyword rilasciate a un modello cloud. Supporta documenti locali TXT,
Markdown e PDF testuali, oltre a un benchmark pubblico di 100 contesti SQuAD
originali distinti. Il percorso supportato è `poc/run_pipeline.py`.

Il sistema usa una query pubblica, recupera documenti locali, genera una bozza
per documento e costruisce un istogramma in cui ogni risposta conta al massimo
una volta per parola. FindBestK e TopKWithPTR selezionano le keyword da inviare
al cloud. L'adattamento del paper e le ipotesi della garanzia sono descritti in
[Privacy accounting](poc/docs/PRIVACY_ACCOUNTING.md).

## Avvio

Dalla directory `poc/`, nell'ambiente virtuale del progetto:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python run_pipeline.py --dry-run
```

Per documenti propri, specificare un percorso e una query:

```bash
.venv/bin/python run_pipeline.py --documents ./private_documents \
  --query "Qual è la scadenza del progetto?" --dry-run

.venv/bin/python run_pipeline.py --documents ./private_documents \
  --query "Qual è la scadenza del progetto?" --max-latency-ms 60000 \
  --offline-cloud --no-telemetry --output reports/request.json
```

`--dry-run` non esegue modello, provider o telemetria. La seconda esecuzione
usa il modello locale (con download automatico se manca) e simula il cloud.
Per un provider reale configurare `.env` seguendo
[Configurazione](poc/docs/CONFIGURATION.md) e omettere `--offline-cloud`.
Non vengono caricati automaticamente documenti dal vault.

## Scelte sperimentali

Lo scheduler usa limiti pubblici del prompt e stime di throughput/RTT. Se lo
SLA stimato non consente cinque inferenze, va in zero-shot senza consultare i
documenti. Non promette un limite rigido sulla latenza reale. `--fixed-n` consente
una baseline a N fisso; `benchmark_scheduler.py` confronta le due modalità a
parità di calibrazione, con un account privacy cumulativo e report locali.

FindBestK usa il dominio pubblico 1..10 e conteggi zero impliciti; la scala
Gumbel è 4/epsilon, scelta conservativa ricondotta alla Definizione A.7 del
PDF rispetto alla scala 2/epsilon dello pseudocodice. I token rilasciati sono
in ordine alfabetico, così non espongono l'ordine delle frequenze private.
Query diverse sullo stesso corpus non azzerano il budget. La CLI singola
contabilizza una richiesta; un servizio reale deve persistere l'account.

Langfuse serve alla visibilità degli esperimenti e alla dimostrazione degli
assunti della tesi. L'uso cloud con dati autorizzati è previsto; non serve ora
un'istanza locale. Per un deployment con documenti riservati si userebbe una
istanza locale nel perimetro fidato. La diagnostica, anche redatta, non viene
presentata come output DP.

I tempi della richiesta sono misurati, il prefill rimane stimato e i byte
riguardano il volume del testo, non il traffico effettivo. Le simulazioni cloud
sono esplicite e non ricevono punteggi di qualità.

## Verifiche

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -v
.venv/bin/python -m coverage run --source=core -m pytest -q tests/test_scheduler.py -p no:cov
.venv/bin/python -m coverage report --include='*/scheduler.py' -m
```

Il benchmark pubblico si rigenera con
`.venv/bin/python scripts/fetch_real_dataset.py` (SQuAD 1.1, un record per
contesto, campione distribuito nel corpus).

Moduli e confine di fiducia sono documentati in
[Architettura](poc/ARCHITECTURE.md). `poc/poc_real_dp_ksa.py` è un wrapper di
compatibilità; `poc/archive/` contiene soltanto i prototipi storici.
