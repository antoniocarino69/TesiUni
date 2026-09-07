# Interventi sulla review del 7 settembre 2026

Il lavoro è stato avviato in un fork della task prima di qualsiasi modifica,
poi su un branch dedicato da main aggiornato. Nessun push è previsto.

| Rilievo | Intervento |
| --- | --- |
| Dominio di FindBestK dipendente dai token osservati | Dominio pubblico e padding implicito di conteggi zero, incluso ultimo gap |
| Ordine privato dei token nel prompt cloud | Ordinamento alfabetico dopo la selezione, anche nell'adapter cloud |
| Risposte brevi incompatibili con k=15..30 | Default pubblico 1..10 e regressione su cinque keyword concordi |
| Calibrazione Gumbel ambigua nel paper | Scala conservativa 4/epsilon ricondotta ad Appendice A.7, con test di distribuzione |
| Budget azzerabile fra richieste | Limite cumulativo delta, controllo prima dell'inferenza, stesso account nel confronto sperimentale; limite fra processi documentato |
| Cento righe ma quattro documenti | Deduplicazione e benchmark rigenerato: 100 contesti distinti, 48 argomenti, SQuAD 1.1 |
| Assenza di documenti reali e retrieval per query | TXT/MD/PDF locali, query esplicita, score per documento, un estratto e un voto per originale |
| Scheduler basato su lunghezze private | Cap pubblico del prompt completo e slot pubblici; tokenizzazione reale per rispettare il cap |
| SLA impossibile | Decisione zero-shot N=0 senza retrieval/inferenza; baseline fissa segnala non fattibilità |
| Pass-rate empirico non validato | Solo probabilità condizionata a gap=3, distinta dalla frequenza misurata |
| Misure ambigue | Timer richiesta completo e timer CLI; prefill etichettato come stima; volumi testo distinti dalla rete |
| Benchmark con conclusione fissa | Rapporto calcolato dai tempi osservati, limiti del testo ripetuto espliciti |
| Langfuse e dati privati | Ruolo sperimentale e confine di fiducia in AGENTS e docs; redazione delle statistiche dirette; nessun obbligo di istanza locale ora |
| Confronto adattivo/fisso | Runner con ordine randomizzato, ripetizioni, qualità lessicale, rilascio, latenza, SLA e account cumulativo |

## Verifica e limiti

La suite copre i controesempi di privacy, parsers TXT/MD/PDF con file sintetici,
deduplicazione, stabilità del retrieval su sostituzione di un documento,
cap del prompt, fallback e confronto con dipendenze simulate. La CLI è stata
eseguita in dry-run e in modalità cloud offline senza telemetria.
Il benchmark pubblico è stato scaricato dalla distribuzione SQuAD 1.1.

Non sono state effettuate inferenze con GGUF né chiamate a provider o Langfuse
con documenti dell'utente. Non si presentano quindi guadagni misurati di latenza
o qualità su hardware reale. Il runner è predisposto per raccoglierli.

La protezione documentale presuppone un'unità originale ben definita: copie
quasi identiche e documenti correlati richiedono una politica a monte. Il
retrieval è lessicale e non usa embedding. I PDF scansiti richiedono OCR locale.
La garanzia del filtro non include diagnostica, tempi, trace o report e assume
la validità di TopKWithPTR del paper. Un servizio persistente richiederebbe
anche un account condiviso fra processi e riavvii, oggi non implementato.
