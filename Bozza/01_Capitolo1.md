# Capitolo 1: Sistemi RAG, architetture ibride e privacy differenziale

## 1.1 Modelli linguistici e recupero di informazioni: il funzionamento della RAG

La Retrieval-Augmented Generation (RAG) è un'architettura progettata per fornire ai modelli linguistici un contesto informativo aggiornato e specifico, non presente nei loro dati di addestramento originali. Il processo si articola in due fasi principali. In primo luogo, a fronte di una richiesta dell'utente, il sistema interroga un archivio documentale per individuare i frammenti di testo più pertinenti. In secondo luogo, questi testi vengono forniti al modello linguistico insieme alla richiesta iniziale, permettendo la formulazione di una risposta basata su informazioni precise. Questo approccio riduce il rischio di informazioni errate o inventate e permette al modello di ragionare su conoscenze private.

## 1.2 Elaborazione locale, cloud e architetture ibride

L'impiego della RAG in contesti aziendali o personali solleva interrogativi sull'opportunità di affidare documenti sensibili a infrastrutture esterne. I modelli eseguiti in cloud offrono elevate capacità di calcolo, ma richiedono il trasferimento dei dati al di fuori del perimetro di controllo dell'utente. Al contrario, l'elaborazione puramente locale garantisce la riservatezza, ma è limitata dalle risorse hardware disponibili sul singolo elaboratore, il che si traduce spesso in tempi di risposta maggiori o nell'uso di modelli di capacità inferiore.

Le architetture ibride cercano di unire i vantaggi di entrambi gli approcci. In un sistema ibrido, il nodo locale e il cloud collaborano: la macchina dell'utente gestisce i dati sensibili ed esegue i compiti più leggeri o critici per la riservatezza, mentre delega al cloud le elaborazioni che richiedono maggiore capacità, avendo cura di filtrare o proteggere le informazioni trasmesse.

## 1.3 Esposizione dei documenti e principi della privacy differenziale

Quando un nodo locale comunica con un servizio cloud per completare una richiesta, esiste il rischio che i dati trasmessi rivelino il contenuto dei documenti privati. Per gestire questo rischio, si ricorre alla privacy differenziale, un quadro matematico che quantifica e limita la quantità di informazioni che l'output di un algoritmo può rivelare sui dati di ingresso.

In sintesi, la privacy differenziale assicura che l'assenza o la presenza di un singolo elemento (nel nostro caso, un singolo documento originale) non modifichi in modo significativo la probabilità di ottenere un certo risultato. Questa garanzia viene fornita introducendo rumore statistico calibrato nel processo. I parametri principali sono il budget di privacy $\epsilon$ (epsilon), che misura la perdita di riservatezza tollerata, e $\delta$ (delta), che rappresenta la probabilità che la garanzia rigorosa non sia rispettata. 

## 1.4 Il metodo DP-KSA di Tang et al.

Questa tesi si basa sul metodo DP-KSA (Differentially Private Keyword Selection Algorithm) proposto da Tang et al. (YYYY(X)). Il metodo protegge il contenuto dei documenti privati durante l'interazione con un modello cloud. Invece di inviare i documenti grezzi, il sistema locale li elabora e seleziona un insieme di parole chiave (token) da inviare al cloud, garantendo che la loro presenza sia differenzialmente privata.

Il meccanismo si compone di due algoritmi principali:
1. **FindBestK:** determina quanti token ($k$) rilasciare. Viene applicato rumore statistico (distribuzione di Gumbel) per decidere se la differenza (gap) tra la frequenza del token $k$-esimo e del token successivo giustifica il rilascio.
2. **TopKWithPTR (Propose-Test-Release):** verifica la stabilità locale del risultato prima di procedere. Se il test passa, i $k$ token vengono rilasciati in ordine alfabetico (per non rivelare informazioni tramite l'ordinamento). Se il test fallisce, il sistema restituisce un risultato vuoto, impedendo la fuga di informazioni.

## 1.5 Il problema prestazionale e il posizionamento della tesi

L'applicazione del DP-KSA richiede che il sistema locale valuti le frequenze dei token su molteplici campioni generati a partire da sottoinsiemi del corpus documentale. Per ottenere distribuzioni statistiche solide, è necessario eseguire decine di inferenze sul nodo locale per ogni singola richiesta.

Dal punto di vista dell'Architettura degli Elaboratori, questa necessità impone un carico di lavoro che può saturare facilmente la capacità di calcolo locale, portando a tempi di elaborazione inaccettabili per un utilizzo interattivo. Il posizionamento di questa tesi si concentra sulla risoluzione di tale collo di bottiglia: come regolare il carico computazionale della fase di campionamento locale per rispettare obiettivi di latenza ragionevoli, senza compromettere le garanzie formali del meccanismo DP-KSA e mantenendo l'utilità delle informazioni estratte.
