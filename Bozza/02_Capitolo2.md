# Capitolo 2: Progettazione del sistema e dello scheduler adattivo

## 2.1 Requisiti, ipotesi e limite di fiducia

Il sistema ibrido analizzato opera in uno scenario in cui la macchina locale dell'utente costituisce il limite di fiducia (trust boundary). I documenti originali risiedono esclusivamente nel file system locale e non devono mai essere inviati al provider cloud nella loro forma grezza. Il provider cloud, considerato "onesto ma curioso", riceve unicamente la query iniziale dell'utente e un insieme di termini filtrati e approvati dal meccanismo di privacy differenziale.

Il sistema assume che la garanzia di privacy risieda nelle proprietà matematiche degli algoritmi implementati e non in euristiche opache. Un requisito fondamentale è la salvaguardia dell'utilità delle risposte: ridurre drasticamente il tempo di elaborazione fornendo risposte generiche o non pertinenti ai documenti non costituisce un esito di successo. Pertanto, la progettazione deve bilanciare tre dimensioni: garanzia formale di privacy, carico di lavoro locale (latenza) e utilità pratica della risposta finale.

## 2.2 Flusso della richiesta e selezione dei documenti locali

Quando l'utente sottopone una query, il sistema identifica i documenti locali più pertinenti. La selezione avviene tramite un meccanismo di recupero basato su metriche di similarità eseguito localmente. L'unità fondamentale da proteggere è il singolo documento originale. È importante sottolineare che né la query iniziale, né il numero di bozze da generare, né la configurazione dei parametri del modello dipendono dal contenuto privato dei documenti, preservando così l'indipendenza richiesta per una corretta analisi della privacy.

I documenti selezionati vengono utilizzati per costruire differenti contesti parziali. Questo campionamento serve a simulare l'assenza o la presenza di ciascun documento, creando la variabilità necessaria su cui il meccanismo DP-KSA andrà a misurare la sensibilità dei termini prodotti.

## 2.3 Generazione delle bozze e integrazione del filtro DP-KSA

La fase centrale prevede l'esecuzione di $N$ inferenze locali mediante un modello linguistico compatto. Ciascuna inferenza utilizza uno dei contesti parziali preparati e genera una "bozza" di risposta. L'insieme di queste bozze produce un istogramma delle frequenze dei termini candidati.

Su questo istogramma si applica il filtro DP-KSA. Come discusso nel capitolo precedente, l'algoritmo FindBestK stima il numero ideale di termini da rilasciare introducendo un rumore controllato, la cui scala dipende dal budget di privacy $\epsilon$. Successivamente, l'algoritmo TopKWithPTR verifica se le condizioni consentono un rilascio sicuro. Se l'esito è positivo, i termini filtrati vengono organizzati in ordine alfabetico e inviati al modello cloud insieme alla richiesta originale, permettendo a quest'ultimo di redigere la risposta finale avvalendosi di tali elementi di contesto protetti.

## 2.4 Modello di stima del tempo di risposta

Al fine di governare il carico computazionale, il sistema impiega un modello euristico per la stima del tempo necessario a completare l'elaborazione locale. Il tempo totale è approssimato come somma del tempo di preparazione del contesto (prefill) e del tempo di decodifica (generazione dei token).

Il modello stima i costi in base a fattori noti a priori, quali i limiti di token imposti nel prompt e le caratteristiche configurate per il modello locale, evitando di misurare le lunghezze effettive basate sui testi estratti per non invalidare le assunzioni di privacy. Le velocità di elaborazione utilizzate sono quelle misurate dalla calibrazione automatica all'avvio della sessione: il sistema esegue inferenze di prova su testi pubblici a lunghezze rappresentative (256, 512, 1024 token) per determinare i valori reali di prefill e generazione del modello sulla macchina corrente. In assenza di calibrazione, si usano valori di default conservativi (250 token/s in prefill, 50 token/s in generazione). Questa stima, benché euristica, è essenziale per fornire un parametro decisionale che permetta al sistema di adattarsi alle prestazioni hardware attese dalla macchina dell'utente, senza richiedere esecuzioni preventive sui documenti reali.

## 2.5 Scelta adattiva del numero di generazioni e gestione dei vincoli

L'innovazione architetturale proposta risiede nello scheduler adattivo. Nelle implementazioni di base, il numero di bozze locali $N$ è un valore fisso. Un $N$ elevato migliora la solidità statistica delle frequenze, aumentando la probabilità che il filtro DP rilasci informazioni utili, ma penalizza severamente i tempi di risposta.

Lo scheduler adattivo ha il compito di calcolare dinamicamente un valore di $N$ che rientri in un obiettivo temporale predefinito (soft SLA). L'algoritmo confronta la stima dei tempi con l'SLA richiesto. Se l'SLA stimato non consente almeno cinque inferenze, lo scheduler dispone di due percorsi. Con il parametro di tolleranza `--sforamento-k` al valore di default (0), il comportamento è conservativo: il sistema rinuncia alla fase di estrazione locale e inoltra la richiesta al cloud senza contesto privato ($N=0$), azzerando l'esposizione e rispettando la scadenza temporale. Con $k > 0$, lo scheduler confronta lo sforamento previsto per il piano minimo ($N=5$) con la tolleranza $k \times E2E_{cloud}$ (dove $E2E_{cloud}$ è la latenza misurata dal probe di sessione o, in sua assenza, una stima manuale). Se lo sforamento rientra nella tolleranza, pianifica comunque $N=5$ e marca la decisione come sforamento accettato; altrimenti ricade in $N=0$. Il parametro `--force-zero-shot` forza esplicitamente $N=0$ ignorando sia l'SLA sia la tolleranza.

Questo obiettivo temporale è inteso come flessibile; occasionali sforamenti sono tollerati poiché l'SLA rappresenta una direttiva prestazionale e non un limite rigido che prevale sulla privacy.

## 2.6 Richieste ripetute e gestione del budget di privacy

Nel contesto della privacy differenziale, ogni interazione che coinvolge i dati sensibili consuma una frazione del budget di privacy complessivo. Il sistema traccia questo consumo calcolando l'accumulo della privacy in logica di Rényi Differential Privacy (RDP).

Le richieste ripetute sullo stesso insieme di documenti riducono progressivamente il budget residuo. Lo scheduler monitora lo stato del budget e, in caso di esaurimento, impedisce ulteriori rilasci informativi interrompendo la pipeline, sollevando un'eccezione dedicata (Privacy Budget Exhausted Error). La garanzia formale di riservatezza, pertanto, viene salvaguardata lungo l'intero ciclo di vita delle interazioni dell'utente con il corpus documentale.
