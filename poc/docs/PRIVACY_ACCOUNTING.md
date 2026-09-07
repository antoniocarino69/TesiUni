# Privacy: meccanismo, adattamenti e limiti

Riferimento: Tang et al., *Differentially Private Retrieval-Augmented
Generation*, PDF presente nella root, Algoritmi 1–3 e Appendice A. Il PDF
riporta metadati editoriali provvisori `YYYY(X)`: non va attribuita una
pubblicazione PoPETS 2025 verificata. Il testo online disponibile è anche
consultabile su [arXiv](https://arxiv.org/html/2602.14374v1).

## Ipotesi necessarie

La query, il dominio di k, N, i limiti dei prompt e i parametri di privacy
sono pubblici e fissati indipendentemente dal contenuto privato. L'adiacenza
riguarda la sostituzione di un documento originale normalizzato. Il retrieval
deve modificare al massimo un membro dell'ensemble; una risposta dipende da
un solo documento e ogni parola vi contribuisce al massimo una volta.

Il retriever locale soddisfa questa proprietà perché punteggi ed estratti sono
calcolati separatamente per documento, con pareggi stabili. Mancanze nel top-N
sono riempite da slot vuoti pubblici. Cambiare N in funzione delle lunghezze
private, usare IDF globale o voti indipendenti per chunk invaliderebbe questa
analisi. Errori di ingestione, tempi, contatori e diagnostica non sono output
protetti dal filtro. La correttezza dei parser e l'indipendenza del generatore
sono assunzioni del sistema, non dimostrate dai test statistici.

## FindBestK: dominio pubblico e calibrazione

L'intervallo predefinito è `1 <= k <= 10`, adatto a risposte brevi. Può essere
configurato prima della richiesta. H include implicitamente conteggi zero:
si calcolano tutti i gap del dominio pubblico, anche se ci sono pochi token,
e anche il gap tra l'ultimo token osservato e zero. Non si decide mai se
eseguire FindBestK contando i token distinti privati.

Per istogrammi adiacenti ogni conteggio ordinato cambia al massimo di 1,
quindi `d_k = H(k)-H(k+1)` ha sensibilità globale al massimo 2. Il codice usa:

```text
Pr[k] proporzionale a exp(epsilon_find * (d_k + r(k)) / 4)
score_k = d_k + r(k) + Gumbel(scale=4/epsilon_find)
```

Questa è una scelta conservativa esplicita rispetto allo pseudocodice
Algoritmo 3, che scrive scala `2/epsilon`. La Definizione A.7 nello stesso PDF
usa `exp(epsilon*q/(2*Delta(q)))`; con Delta=2 implica scala 4/epsilon.
Si applicano quindi A.8 e A.9 all'effettivo epsilon configurato, senza
assumere un miglioramento non dimostrato della costante. La centratura del
Gumbel non cambia l'argmax. I test verificano scala e distribuzione di scelta.

## TopKWithPTR

```text
g = H(k) - H(k+1)
Z ~ Normal(0, 4 sigma²)
tau = 2 sigma Phi^-1(1-delta_ptr)
g_hat = max(2, g) + Z - tau
rilascia se g_hat > 2
P(pass | g) = 1 - Phi((tau + 2 - max(2,g)) / (2 sigma))
```

Con `g <= 2` la probabilità di passaggio è delta_ptr, non zero (Teorema A.10).
Il calcolo della quantile usa `-Phi^-1(delta_ptr)` per evitare la perdita di
precisione di `1-delta_ptr` quando delta è piccolo.

Quando il test passa, il codice seleziona i top-k e li ordina alfabeticamente.
Il gap rende stabile l'insieme, non l'ordine interno delle frequenze private:
quest'ultimo non deve essere esposto. Se k supera il numero di token osservati,
g=0 e l'eventuale rilascio appartiene al failure event contabilizzato da delta;
si restituiscono soltanto token osservati, mai segnaposto o conteggi zero.

`strict_gap_guard=True` resta una modalità sperimentale separata, disattivata:
sopprime i rilasci con gap <=2 e non è usata per rivendicare la prova del paper.

## Account RDP e richieste ripetute

Per ordine alpha, i Teoremi A.9 e A.10 danno:

```text
epsilon_RDP(alpha) = epsilon_EM(alpha, epsilon_find) + alpha/(2*sigma²)
epsilon_DP = min_alpha(epsilon_RDP(alpha) + log(1/delta_conversion)/(alpha-1))
delta_totale = delta_ptr + delta_conversion
```

La conversione segue A.6. Di default `delta_conversion=delta_ptr`, quindi
`--delta 1e-4` significa delta totale `2e-4` per una chiamata. Il limite epsilon
è quello totale della conversione, non la semplice somma di due quote nominali.

Per m chiamate sulla stessa istanza, si sommano prima le componenti RDP per
ordine (A.3), poi si converte una volta. Il delta diventa
`m*delta_ptr + delta_conversion`. Il filtro rifiuta una chiamata che superi
il limite epsilon o `delta_budget`, prima di consumare nuova casualità.
Il delta_budget predefinito consente una chiamata; per una sessione va
configurato esplicitamente. L'account è in memoria e per uso sequenziale.

Una query diversa sullo stesso corpus **non azzera il budget**. La CLI singola
rende esplicito `account_scope=single_request`; avvii ripetuti non implementano
un account persistente di deployment. Per più richieste nel processo passare
lo stesso filtro a `run_request`. `benchmark_scheduler.py` lo fa per tutta la
sessione, inclusi i diversi N. Una nuova istanza non ripristina privacy già
spesa: un servizio reale deve conservare l'account anche fra riavvii.
Seed noti del rumore non vanno usati per rilasci riservati; il seed del benchmark
di confronto controlla soltanto l'ordine degli esperimenti.

## Telemetria e risultati della tesi

Langfuse serve a osservare e dimostrare cosa accade nelle fasi della pipeline.
L'attuale uso sperimentale può avvenire sul servizio cloud con dati autorizzati;
non è necessario predisporre ora un'istanza locale. In produzione con documenti
riservati si userebbe un'istanza locale nel perimetro fidato.

`capture_sensitive` abilita bozze, conteggi, gap, query, risposta e statistiche
sui documenti. La modalità redatta rimuove questi contenuti ma contiene ancora
tempi e contatori operativi: nessuna delle due modalità viene dichiarata DP.
Ogni trace espone questa distinzione nei metadati. I report JSON e la console
sono diagnostica locale, anch'essi esterni all'accounting del rilascio cloud.
L'esecuzione `--no-telemetry` permette di non creare trace.

Questi adattamenti rimuovono i controesempi della review. Non costituiscono
una certificazione della pipeline: valgono le ipotesi sopra, e la prova
assunta di TopKWithPTR resta quella del paper.
