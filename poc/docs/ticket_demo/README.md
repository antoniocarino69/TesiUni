# Assistente sui ticket IT

Questo è il caso applicativo principale del PoC: ricavare una procedura comune
da incidenti distinti limitando l'influenza del singolo ticket. È un'ipotesi
applicativa da verificare, non un risultato del paper. Le schede salariali
restano disponibili come esperimento sui limiti.

In `documenti/` ci sono 80 file Markdown interamente sintetici:

| Problema inventato | Ticket | Procedura prevista |
|---|---:|---|
| FerroSync E42 dopo aggiornamento | 48 | Arrestare servizio, cancellare cache, riavviare servizio |
| TunnelDemo E17 | 16 | Importare certificato aggiornato, riconnettere client |
| StampaDemo E55 | 16 | Svuotare coda, riavviare servizio |

Clienti, referenti, domini `.example`, IP di esempio, host e codici pratica
sono fittizi. Queste procedure non sono istruzioni per prodotti reali.
I file sono distinti ma generati da pochi modelli testuali: questa semplicità
controllata non riproduce la varietà linguistica di un archivio reale.

Ogni ticket vale un voto. Dieci ticket E17 appartengono allo stesso cliente:
proteggere un documento non implica proteggere quel cliente in tutti i ticket.
Il manifest registra questa relazione e gli hash; `cases.json` contiene le
domande e i criteri di valutazione. Il modello non riceve manifest o risposte attese.

Le quattro prove riguardano la procedura E42, un codice unico per pratica,
un identificativo interno condiviso e l'errore E99 assente. L'identificativo
condiviso serve a verificare che frequente non significa non sensibile.
Il filtro DP non riconosce semanticamente i dati personali.

## Esecuzione

Dalla directory `poc/`, usare esclusivamente `documenti/` come corpus:

```bash
.venv/bin/python scripts/create_ticket_demo.py
.venv/bin/python run_pipeline.py --documents docs/ticket_demo/documenti \
  --query "Come si risolve l'errore E42 dopo aggiornamento di FerroSync?" \
  --fixed-n 40 --epsilon 4 --offline-cloud --no-telemetry \
  --output reports/ticket_request.json
.venv/bin/python benchmark_ticket_demo.py --trials 500
```

Il generatore è ripetibile e rifiuta di sovrascrivere file modificati.
La CLI può scaricare il modello; il benchmark richiede che sia già presente.
Il benchmark non legge `.env` e non chiama provider o Langfuse. Esegue 160
inferenze locali, quattro richieste con un account privacy condiviso e
24.000 prove del filtro sulle bozze memorizzate (N=5,10,20,40; epsilon=1,4,8).
Queste repliche su dati sintetici sono diagnostica condizionale, non nuove
richieste protette da un unico budget. Cambiando N si usano prefissi delle
stesse bozze, senza rigenerarle.

Una sintesi aggiuntiva usa il modello locale nel ruolo del cloud, ricevendo
solo domanda e keyword effettivamente rilasciate. Riutilizza il prompt breve
dell'estrattore (30 token): è una baseline limitata, non una valutazione di
un provider cloud. Con rilascio vuoto si astiene senza inferenza.

La copertura dei passaggi controlla parole e sinonimi, non ordine, negazione
o validità della procedura. I domini e gli IP vengono tokenizzati in frammenti:
la metrica degli identificativi non è un rilevatore completo di dati personali.
L'ordine alfabetico delle keyword non conserva la sequenza delle operazioni.
Una futura valutazione della risposta deve controllarla esplicitamente.

N fisso è una baseline che può eccedere lo SLA stimato. I tempi della sintesi
aggiuntiva sono separati da quelli della pipeline. Vedere i
[risultati osservati](RISULTATI.md) prima di interpretare il rilascio come successo.
