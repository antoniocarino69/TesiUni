# Optimizing and Evaluating Enterprise Retrieval-Augmented Generation (RAG): A Content Design Perspective

## 1. Traduzione Letterale

**Abstract:**
La generazione aumentata dal recupero (RAG) è una tecnica popolare per utilizzare modelli linguistici di grandi dimensioni (LLM) per costruire soluzioni di supporto clienti e di risposta alle domande. In questo articolo, condividiamo l'esperienza pratica del nostro team nella costruzione e nel mantenimento di soluzioni RAG su scala aziendale che rispondono alle domande degli utenti sul nostro software basandosi sulla documentazione del prodotto. La nostra esperienza non ha sempre coinciso con i pattern più comuni nella letteratura RAG. Questo articolo si concentra su strategie di soluzione che sono modulari e agnostiche rispetto ai modelli. Ad esempio, la nostra esperienza negli ultimi anni - utilizzando diversi metodi di ricerca e LLM, e molte collezioni di basi di conoscenza - è stata che semplici cambiamenti al modo in cui creiamo i contenuti della base di conoscenza possono avere un impatto enorme sul successo delle nostre soluzioni RAG. In questo articolo, discutiamo anche di come monitoriamo e valutiamo i risultati. Le comuni tecniche di valutazione di benchmark RAG non si sono rivelate utili per valutare le risposte a domande nuove degli utenti, quindi abbiamo scoperto che è necessario un approccio flessibile, con "l'essere umano alla guida".

**1. Introduzione:**
La generazione aumentata dal recupero (RAG) è un modo efficace per utilizzare modelli linguistici di grandi dimensioni (LLM) per rispondere a domande evitando allucinazioni e inesattezze fattuali [12, 20, 46]. Il RAG di base è semplice: 1) cercare in una base di conoscenza i contenuti rilevanti; 2) comporre un prompt ancorato nei contenuti recuperati; e 3) sollecitare un LLM a generare output. Per la fase di recupero, un approccio domina la letteratura: 1) segmentare il testo del contenuto in frammenti (chunks); 2) indicizzare i frammenti vettorializzati per la ricerca in un database vettoriale; e 3) quando si generano le risposte, ancorare i prompt in un sottoinsieme dei frammenti recuperati [13]. Le nostre soluzioni RAG non usano sempre database vettoriali per la ricerca.

Wikipedia è stata a lungo influenzata e ha avuto un'influenza sulla ricerca scientifica [21, 41]. Rispetto alla RAG, Wikipedia è una fonte dominante di contenuti per le basi di conoscenza per i dati di addestramento e i benchmark [...]. La base di conoscenza per le soluzioni RAG del nostro team è la nostra documentazione di prodotto, che è strutturata diversamente rispetto agli articoli di Wikipedia.

L'uso di benchmark comuni per testare la tua implementazione RAG coinvolge questi passaggi: 1) indicizzare i contenuti dati della base di conoscenza nel tuo componente di recupero; 2) sollecitare la tua soluzione a rispondere alle domande date; e 3) confrontare le risposte generate con le risposte attese, usando metodi come la corrispondenza esatta, la similarità del coseno, BLEU, ROUGE, METEOR, BertScore, o usando gli LLM come giudici [49]. Tali metriche di valutazione non si sono rivelate utili per valutare i nostri risultati RAG per domande nuove da parte di utenti reali.

In questo articolo, condividiamo la nostra esperienza nella costruzione di soluzioni RAG su scala aziendale, con un focus su tre aspetti:
- **Implementazione RAG** – Le nostre soluzioni sono modulari. I nostri componenti di recupero e generativi sono scatole chiuse, accessibili tramite API, con una limitata capacità di fine-tuning.
- **Contenuto della base di conoscenza** – Siamo in grado di migliorare i risultati ottimizzando il contenuto della base di conoscenza stesso. Abbiamo sviluppato linee guida per la strategia dei contenuti e per la scrittura per la RAG.
- **Valutazione dei risultati** – Testiamo le nostre soluzioni RAG con vere domande degli utenti prima di rendere le soluzioni disponibili ad utenti esterni. Valutiamo le risposte in tempo di esecuzione dopo che le soluzioni sono state lanciate.

**Core - Implementazione RAG (Estratto della Soluzione Architetturale):**
La Fig. 4 mostra i componenti della soluzione RAG menzionata in precedenza. La base di conoscenza è la documentazione del prodotto costituita da "argomenti" (topics), utilizzando il paradigma Darwin Information Typing Architecture (DITA). [...]
**(A) Pre-elaborazione dell'input dell'utente** – L'input dannoso, come iniezioni JavaScript e prompt avversariali, viene respinto; le informazioni personali rimosse; i pregiudizi così come l'odio, gli abusi e la volgarità (HAP) parafrasati. L'input viene tradotto in inglese e classificato per determinare se si tratta di una domanda e per rilevare il tipo di domanda [...].
**(C) Aumentare la domanda** – Se la domanda dell'utente non corrisponde a una FAQ, la domanda viene ulteriormente elaborata per migliorare le prestazioni di ricerca: domande ambigue riscritte; gergo sostituito con termini di dominio; sinonimi aggiunti.
**(D) Ricerca come scatola chiusa** – Chiamiamo un'API di ricerca che restituisce una lista classificata di argomenti rilevanti alla nostra query. Alcuni risultati di ricerca potrebbero essere riclassificati o filtrati dalla nostra soluzione RAG.
**(E) Argomenti interi invece di frammenti (chunks)** – Una volta che abbiamo una lista di argomenti rilevanti, estraiamo il testo completo di quegli argomenti per ancorare il nostro prompt. A volte chiamata "small2big" o "recupero del documento padre", questa strategia funziona bene per noi perché i nostri argomenti sono ottimizzati per il RAG. Sono brevi, completi, accurati e aggiornati. Il nostro componente di estrazione del testo trae vantaggio dalla struttura affidabile dei nostri argomenti.
**(F) Prompt semplici** – La nostra soluzione non è un dialogo, quindi non abbiamo bisogno di mantenere la cronologia della chat. L'LLM ha un solo compito: riscrivere i contenuti dagli argomenti di base in una risposta succinta. 

**6. Conclusioni (Scaling an Enterprise Solution):**
Quando si costruisce una soluzione RAG per supportare un portafoglio di decine o centinaia di prodotti software, sorgono nuove sfide:
- *Le domande variano per prodotto* - Mentre le domande comuni per un prodotto potrebbero essere fattuali, per un altro potrebbero essere domande sulla sintassi della riga di comando.
- *I contenuti variano per prodotto* - La documentazione potrebbe essere concettuale, mentre un'altra potrebbe essere basata su riferimenti API. La ricerca che funziona per uno potrebbe non funzionare per l'altro.
- *Ottenere adesione* - Ottenere adesione per un'iniziativa a livello aziendale può essere impegnativo.
- *Una taglia unica potrebbe non andar bene per tutti* - Assicurare che la soluzione sia configurabile e flessibile dà potere ai team individuali di trarre vantaggio dall'infrastruttura centralizzata facendo anche ciò che funziona meglio per loro.
- *Test di regressione automatizzati* - Man mano che i team riscrivono i loro contenuti e aggiornano i componenti, hanno bisogno di un modo per testare le prestazioni senza dover valutare manualmente i risultati.

---

## 2. Riassunto Esteso
L'articolo documenta le esperienze pratiche del team IBM nello sviluppo di sistemi RAG (Retrieval-Augmented Generation) su scala aziendale per fornire risposte precise basandosi sulla documentazione dei software. A differenza della letteratura accademica dominante, che punta tutto sulla divisione in "chunk" (frammenti) e sui database vettoriali usando benchmark basati su Wikipedia, il team IBM ha scoperto che in produzione le regole cambiano. Hanno constatato che un'architettura pragmatica modulare con chiamate ad API di ricerca esterne chiuse, ma soprattutto incentrata sul **Content Design**, fornisce risultati nettamente superiori. Ottimizzare i documenti prima (es. creando interi "topic" leggibili sia per esseri umani che per l'LLM, strutturando le tabelle linearmente e inserendo riassunti procedurali) elimina molti fallimenti. Si evidenzia infine la necessità di un approccio valutativo "human in the lead" per superare l'inefficacia delle metriche di valutazione automatizzate su domande reali nuove.

---

## 3. Spiegazione Semplificata
Immagina un'IA come uno studente che deve sostenere un esame "a libro aperto" per rispondere ai clienti di un'azienda. Gli accademici spesso suggeriscono di strappare le pagine del libro in migliaia di pezzetti (chunking) e di organizzarli in complessi schedari matematici (database vettoriali). 
Questo studio condotto in IBM, invece, afferma una cosa molto più intuitiva: **se il libro è scritto bene in partenza, lo studente non fatica.** Se strutturiamo la documentazione aziendale in capitoli brevi e autosufficienti ("interi argomenti"), eliminiamo le tabelle incomprensibili, spieghiamo a parole le immagini e rimuoviamo in anticipo parolacce e offese dalle domande, l'IA farà molto meno sforzo (e meno errori). Il segreto, in sintesi, non è avere l'algoritmo di ricerca più all'avanguardia, ma fornire "pappa pronta", ovvero documenti ordinati e chiari in ingresso.

---

## 4. Considerazioni Critiche
- **Punti di forza:** Il paper è straordinariamente pratico e smonta i dogmi accademici portando metriche operative di un colosso come IBM. La prospettiva incentrata sul "Content Design" è una ventata d'aria fresca che sposta il problema dall'ingegneria algoritmica ai processi organizzativi. Inoltre, la descrizione della pre-elaborazione (sicurezza e controlli sui bias) prima dell'accesso in rete è eccellente.
- **Limiti:** L'articolo è molto qualitativo e basato su osservazioni sul campo. Manca di dati quantitativi su parametri hardware, latenza di rete, consumo di memoria per contesti estesi (passando l'intero "topic" invece del chunk) e impatto energetico, i quali sarebbero fondamentali per un'ingegnerizzazione di basso livello o una valutazione economica. Essendo basato su API proprietarie, il modello esatto o le impostazioni interne del retrieve restano oscure.

---

## 5. Spunti per Tesi Triennale (Architetture di Reti e Calcolatori)
Data l'impostazione "Architetture di reti e calcolatori", i concetti di questo paper possono essere declinati per affrontare tematiche infrastrutturali, di efficienza e di rete in un ambiente on-premises/enterprise:

1. **Impatto del "Content Design" sui Payload di Rete (Chunking vs. Whole Topic):**
   Il paper abbandona il micro-chunking vettoriale per l'approccio "small2big" (Whole topics). In una rete aziendale tra il nodo del database documentale e il cluster GPU in cui risiede l'LLM, trasferire interi capitoli invece di pochi vettori aumenta la dimensione del payload di rete. La tesi potrebbe misurare il trade-off architetturale: quanta latenza di rete extra genera il trasferimento di interi *topic* testuali? E come questo impatta la VRAM (Context Window) delle GPU locali?

2. **Ottimizzazione I/O e Caching a Livello di Rete per RAG Distribuito:**
   Il framework intercetta domande sensibili o legali restituendo *Hard-coded FAQ*. In un'architettura di rete distribuita (Edge Computing), si può progettare un *Reverse Proxy* (es. Redis o NGINX) che funga da strato di caching. Se una query ricorrente viene riconosciuta dal nodo proxy, si risponde senza dover fare la chiamata REST all'infrastruttura di retrieval o all'LLM. La tesi potrebbe valutare l'abbattimento della latenza e l'alleggerimento del carico sul calcolo.

3. **Architetture a Microservizi e Data Processing Pipeline:**
   Il sistema è diviso in blocchi funzionali: *Pre-processing*, *Search API*, *Post-processing*. Ognuno richiede chiamate di rete in pipeline (multipli network hops). Come si può ottimizzare questa catena in un data center aziendale? Esempio: implementare protocolli di comunicazione veloci tra container (es. gRPC vs REST) per evitare colli di bottiglia latenti prima che la query arrivi al modello generativo.

4. **Sicurezza di Rete e Data Filtering (On-Premises Privacy):**
   Il paper rimuove IP, e-mail e informazioni personali (PII) durante il pre-processing (*Privacy and Security block*). In architetture di rete aziendali ibride, in cui l'LLM risiede nel cloud, una tesi potrebbe analizzare un nodo Edge locale dedicato unicamente al "Data Sanitization". Ciò impedirebbe il data leak: i payload inviati attraverso le WAN escono già puliti, sgravando i modelli LLM da filtri costosi computazionalmente e garantendo conformità GDPR a livello topologico.
