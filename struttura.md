# Struttura proposta della tesi triennale

Bozza di lavoro — 13 settembre 2026. Indice e descrizioni da rivedere con il relatore.

## Titolo di lavoro

**Progettazione e valutazione di uno scheduler adattivo per sistemi RAG a privacy differenziale in architetture edge-cloud**

Il titolo mette al centro il contributo progettuale: decidere quanto lavoro eseguire sul dispositivo locale prima di interrogare il modello remoto. Il filtro DP-KSA di Tang et al. costituisce la base scientifica adottata; il contributo della tesi riguarda la sua integrazione nel prototipo, il modello dei tempi, lo scheduler e la valutazione sperimentale.

La domanda che guida il lavoro è:

> In un sistema RAG con filtro a privacy differenziale, come cambia il compromesso tra tempo di risposta e utilità delle informazioni rilasciate quando il numero di generazioni locali viene adattato a un vincolo temporale, rispetto a una configurazione fissa?

La risposta dovrà emergere dagli esperimenti. Un numero maggiore di documenti o generazioni non implica automaticamente maggiore utilità o una garanzia di privacy più forte.

## Dimensione e impostazione

Propongo **quattro capitoli**, preceduti da un’introduzione e seguiti dalle conclusioni. La parte teorica serve a comprendere il progetto; la maggior parte dello spazio va alle scelte architetturali e agli esperimenti. Il collegamento con Architetture e Reti di Calcolatori passa attraverso la distribuzione del calcolo fra dispositivo locale e cloud, i costi dell’inferenza e la modellazione della latenza.

Il regolamento Mercatorum indicato dall’Ateneo come valido dalla sessione di giugno 2026 prevede, all’art. 3, un elaborato finale indicativamente compreso fra **20 e 40 cartelle**, accompagnato da una **sinossi separata di 3–5 cartelle**, pari a 6.000–10.000 caratteri, bibliografia esclusa. La sinossi non deve contenere note, formule, tabelle o grafici. Sono indicazioni del regolamento, mentre la ripartizione seguente è una proposta editoriale. Le cartelle non coincidono necessariamente con le pagine impaginate: il formato definitivo andrà adeguato al modello in piattaforma e alle indicazioni del relatore. [Regolamento ufficiale Mercatorum, art. 3](https://assets.ctfassets.net/5bcqzxwt09xw/6BVdgRSFTesWCTmxcH5nfx/e7d4dc7f186f13a5880a488b77b4c1e5/Regolamento_della_prova_finale_e_della_tesi_di_laurea.pdf)

| Parte                                                       | Spazio orientativo in cartelle |
| ----------------------------------------------------------- | ------------------------------:|
| Introduzione                                                | 2                              |
| 1. Sistemi RAG, architetture ibride e privacy differenziale | 5–6                            |
| 2. Progettazione del sistema e dello scheduler adattivo     | 8–9                            |
| 3. Realizzazione del prototipo e metodologia sperimentale   | 6–7                            |
| 4. Risultati sperimentali e discussione                     | 7–8                            |
| Conclusioni                                                 | 2                              |
| Bibliografia e sitografia                                   | 2–3                            |
| **Totale orientativo**                                      | **32–37**                      |

La sinossi è un documento distinto. Frontespizio, indice e poche figure essenziali vanno gestiti mantenendo il lavoro compatto. Eventuali appendici non devono diventare un modo per trasferire fuori dal testo una seconda tesi: codice e report completi possono restare nel repository, secondo le indicazioni del relatore.

## Indice proposto

### Introduzione

- Il problema: consultare documenti locali attraverso un modello linguistico remoto.
- Obiettivo del lavoro e domanda di ricerca.
- Contributo del prototipo e organizzazione dell’elaborato.

### Capitolo 1 — Sistemi RAG, architetture ibride e privacy differenziale

1.1 Modelli linguistici e recupero di informazioni: il funzionamento della RAG  
1.2 Elaborazione locale, cloud e architetture ibride  
1.3 Esposizione dei documenti e principi della privacy differenziale  
1.4 Il metodo DP-KSA di Tang et al.  
1.5 Il problema prestazionale e il posizionamento della tesi

### Capitolo 2 — Progettazione del sistema e dello scheduler adattivo

2.1 Requisiti, ipotesi e confini di fiducia  
2.2 Flusso della richiesta e selezione dei documenti locali  
2.3 Generazione delle bozze e integrazione del filtro DP-KSA  
2.4 Modello di stima del tempo di risposta  
2.5 Scelta adattiva del numero di generazioni e gestione dei vincoli  
2.6 Richieste ripetute e gestione del budget di privacy

### Capitolo 3 — Realizzazione del prototipo e metodologia sperimentale

3.1 Ambiente di esecuzione e organizzazione del software  
3.2 Dati di prova: ticket IT sintetici e corpus di controllo  
3.3 Configurazioni a confronto e protocollo degli esperimenti  
3.4 Metriche, raccolta delle misure e osservabilità con Langfuse  
3.5 Verifiche di correttezza e riproducibilità

### Capitolo 4 — Risultati sperimentali e discussione

4.1 Tempi stimati e tempi osservati  
4.2 Scheduler adattivo e configurazioni a numero fisso di generazioni  
4.3 Effetto del numero di documenti e dei parametri di privacy sul rilascio  
4.4 Caso dei ticket IT: informazioni utili, dettagli individuali ed errori  
4.5 Limiti del prototipo e interpretazione dei risultati

### Conclusioni

- Risposta alla domanda di ricerca e contributo realizzato.
- Condizioni d’impiego emerse dagli esperimenti.
- Sviluppi futuri.

### Bibliografia e sitografia

### Eventuali appendici brevi

A. Parametri e comandi per riprodurre gli esperimenti  
B. Dettagli della contabilizzazione della privacy, se necessari alla lettura

## Descrizione delle parti

### Introduzione

Aprire con un esempio concreto: un assistente che risponde a domande su ticket di assistenza conservati in azienda. Il modello remoto può aiutare a formulare la risposta, ma l’invio dei testi originali espone i contenuti al provider. L’elaborazione locale con filtro DP-KSA limita ciò che viene rilasciato, al prezzo di più generazioni sul dispositivo.

Da qui nasce il problema dello scheduler: scegliere il numero di generazioni compatibile con il tempo disponibile e osservare quanta informazione utile rimane. Presentare subito il carattere applicativo e sperimentale della tesi, distinguendo il metodo ripreso dalla letteratura dalle scelte sviluppate nel progetto.

### Capitolo 1 — Sistemi RAG, architetture ibride e privacy differenziale

Fornire al lettore le nozioni necessarie per seguire il progetto: che cosa fa un modello linguistico, come il recupero documentale integra la generazione e quali differenze esistono fra esecuzione locale, remota e ibrida. Bastano pochi richiami a token, dimensione del modello e quantizzazione per spiegare il costo dell’inferenza. Evitare una lunga storia dell’intelligenza artificiale o una trattazione completa dei Transformer.

Introdurre la privacy differenziale come limite all’influenza di un singolo documento sul risultato rilasciato. Spiegare in modo accessibile i parametri ε e δ e la necessità di contabilizzare interrogazioni ripetute. Il testo deve chiarire che questa garanzia non equivale alla cancellazione di ogni informazione riservata, né alla correttezza della risposta.

Presentare poi DP-KSA: una bozza per documento, aggregazione delle parole, scelta privata di quante parole selezionare con FindBestK e verifica rumorosa del rilascio con TopKWithPTR. Una figura della pipeline è sufficiente per introdurre il metodo. Il riferimento tecnico resta Tang et al., *Differentially Private Retrieval-Augmented Generation*, Algoritmi 1–3 e Appendice A, nella versione presente nel progetto; i metadati editoriali del PDF sono provvisori e non vanno trasformati in un’attribuzione PoPETS 2025 verificata.

Chiudere il capitolo individuando il problema affrontato: il costo delle generazioni locali rende utile una politica di allocazione del lavoro sensibile ai vincoli temporali. I lavori affini servono a collocare questa scelta nel contesto dei sistemi RAG locali e ibridi.

### Capitolo 2 — Progettazione del sistema e dello scheduler adattivo

È il capitolo centrale. Descrivere l’architettura con un diagramma che mostri dove risiedono i documenti, quali componenti operano localmente e quali informazioni raggiungono il provider. Query e configurazione sono pubbliche; il documento originale normalizzato è l’unità protetta. Ogni documento contribuisce con una sola bozza e gli slot mancanti sono vuoti pubblici. Queste scelte collegano l’implementazione alle ipotesi del filtro.

Nella parte dedicata a DP-KSA spiegare gli adattamenti effettivamente implementati: dominio pubblico di FindBestK, calibrazione conservativa del rumore e rilascio delle parole in ordine alfabetico. Richiamare esplicitamente il legame con gli algoritmi del paper e con l’Appendice A. In particolare, la scala Gumbel adottata è 4/ε, con ε riferito alla fase FindBestK, e la differenza rispetto allo pseudocodice originale è documentata. Il mancato superamento del test produce un rilascio vuoto; il superamento rumoroso non certifica da solo la stabilità dell’insieme. Le derivazioni più lunghe possono stare in una breve appendice.

Presentare il modello dei tempi utilizzato dallo scheduler e distinguerlo dalla scomposizione completa dei costi osservabili. La stima corrente usa limiti pubblici dei prompt e della generazione, velocità di elaborazione configurate, latenza di rete e tempo cloud stimato. Non misura in tempo reale tutti i costi di una richiesta.

Spiegare quindi la scelta di N fra 5 e 40 e il caso N=0 quando il piano minimo non rientra nel vincolo stimato: in quel percorso non vengono avviati retrieval e inferenza locale e si ricorre alla risposta senza informazioni documentali, detta zero-shot. Includere uno pseudocodice breve e un esempio numerico. La scelta di N deve rimanere indipendente da lunghezze, frequenze o altri contenuti privati.

Chiudere con il budget cumulativo: più domande sullo stesso corpus condividono l’account di privacy. Descrivere il supporto alla sessione interattiva e il limite della mancata persistenza fra riavvii. Il risultato progettuale da sostenere è una scelta del carico entro una stima temporale e un budget dichiarato; il rispetto effettivo dei tempi viene valutato nel capitolo 4.

### Capitolo 3 — Realizzazione del prototipo e metodologia sperimentale

Descrivere l’ambiente realmente utilizzato: hardware, sistema operativo, modello locale, quantizzazione e motore llama.cpp. Presentare in modo sintetico i moduli del software e i percorsi per la singola richiesta, la sessione interattiva e il confronto dello scheduler. Il capitolo deve consentire di comprendere e riprodurre le prove, senza commentare ogni funzione del codice.

Usare i ticket IT sintetici come caso applicativo principale. Le domande distinguono una procedura ricorrente, un identificativo individuale, un’informazione interna condivisa e un errore assente dal corpus. Il corpus salariale fittizio è un controllo utile per studiare che cosa accade quando aumentano i documenti non pertinenti. SQuAD può restare un riferimento complementare, se vengono presentati esperimenti effettivamente eseguiti su quel benchmark.

Definire il confronto fra scheduler adattivo e configurazioni fisse, mantenendo uguali modello, query, limiti dei prompt e calibrazione. Specificare numero di ripetizioni, ordine delle prove e stato del modello, distinguendo avvio a freddo e modello già caricato. Separare le richieste complete, con nuove inferenze, dalle repliche del solo filtro su bozze congelate: queste ultime descrivono la variabilità del rilascio condizionata a quelle bozze.

Le metriche principali sono tempo di richiesta, scarto fra stima e misura, eventuali superamenti del vincolo, N scelto, frequenza di rilascio, conservazione delle informazioni attese e budget consumato. Per il caso ticket valutare anche la completezza e l’ordine della procedura nella risposta finale, quando tale risposta è prodotta da un modello reale. La dimensione del testo inviato può essere un indicatore aggiuntivo, con una definizione esplicita.

Langfuse serve a rendere osservabili le fasi della pipeline e a documentare gli esperimenti su dati pubblici o autorizzati. Distinguere i trace diagnostici dal contenuto protetto rilasciato al provider. Concludere con una sintesi delle verifiche software sulle invarianti del filtro, sullo scheduler e sulla separazione dei dati, rimandando i dettagli ripetitivi al repository.

### Capitolo 4 — Risultati sperimentali e discussione

Organizzare i risultati attorno alla domanda di ricerca. Mostrare prima quanto le stime si avvicinano ai tempi osservati, poi confrontare adattivo e N fisso. Un grafico dei tempi e una tabella con N, rilascio e superamenti del vincolo permettono di valutare insieme costo e utilità. Includere anche il caso in cui lo scheduler rinuncia al lavoro locale.

Studiare poi l’effetto di N ed ε sulle parole rilasciate. I risultati già documentati suggeriscono due aspetti da approfondire: una stima conservativa può ridurre molto il carico locale e il rilascio; aggiungere documenti poco pertinenti può peggiorare la conservazione dell’informazione richiesta. Presentarli come osservazioni nelle configurazioni provate, senza dedurne una superiorità generale di una variante.

Nel caso ticket distinguere la presenza delle parole necessarie dalla correttezza della risposta finale. Discutere anche l’informazione interna ripetuta in molti documenti, che può essere rilasciata, e il consenso su risposte sbagliate quando la domanda riguarda un errore inesistente. Sono risultati utili per definire il campo di applicazione del prototipo.

La discussione deve mantenere alcune distinzioni:

- Le frequenze ottenute ripetendo il filtro sono risultati empirici; zero eventi osservati non significa probabilità nulla.
- La protezione è riferita al documento, senza estenderla automaticamente al cliente o a tutte le informazioni aziendali.
- Il prefill riportato dal prototipo è una stima euristica, non una misura diretta del tempo al primo token.
- I byte del testo non misurano il traffico effettivo comprensivo dei protocolli di rete.
- Il cloud simulato permette di verificare il flusso, ma non fornisce una misura della qualità di un modello remoto reale.
- I trace, la console e i report sperimentali restano fuori dalla garanzia del rilascio DP.

Le prove già presenti sono una base iniziale. Il confronto salariale contiene tre richieste per variante: è sufficiente per una prima osservazione dei tempi, ma non per affermazioni robuste sulla frequenza di rilascio o sulla superiorità dello scheduler. Eventuali nuove prove andranno descritte soltanto dopo la loro esecuzione.

### Conclusioni

Riprendere la domanda iniziale e rispondere usando i risultati del capitolo 4. Riassumere che cosa è stato realizzato, quali scelte sono risultate utili e quali limiti rimangono. Il contributo può essere valido anche se gli esperimenti mostrano che l’adattamento è troppo conservativo o che il rilascio di parole non conserva sempre una procedura completa.

Come sviluppi futuri indicare soprattutto la validazione su hardware diverso (x86 con e senza acceleratore GPU, confronto con Apple Silicon), una valutazione della sintesi con modelli più capaci e la persistenza del budget fra riavvii. La calibrazione automatica è già implementata e attiva di default; il confronto Apple Silicon–x86/NVIDIA è parte della fase E pianificata e va aggiunto se eseguito.

## Tesi consultate come riferimento per la struttura

Ricerca web svolta il 13 settembre 2026. I riferimenti seguenti orientano l’organizzazione dell’elaborato; non sostituiscono gli articoli scientifici come fonti del metodo. I suggerimenti su cosa riprendere sono valutazioni per questa proposta.

### Mercatorum: un riferimento vicino al tema della privacy

**Cristiano Coccanari — _AI generative: privacy, trasparenza e sicurezza dei dati, l’approccio dell’Artificial Intelligence Act e il quadro internazionale_**, Universitas Mercatorum, 2023, corso in Scienze giuridiche per la criminologia, l’investigazione e la sicurezza. Consultati l’indice pubblicato dall’autore e il testo accessibile su Academia.edu; non si tratta di un deposito istituzionale verificato.

L’indice presenta un’introduzione, tre capitoli che passano dal contesto al tema centrale e al confronto internazionale, e la bibliografia. È utile come esempio Mercatorum di trattazione compatta su IA e privacy. L’impostazione giuridica è distante dal nostro contributo sperimentale: ne riprenderei la focalizzazione, senza aggiungere un capitolo normativo alla tesi. [Documento dell’autore](https://www.academia.edu/112421016/AI_generative_privacy_trasparenza_e_sicurezza_dei_dati_l_approccio_dell_Artificial_Intelligence_Act_e_il_quadro_internazionale)

Nella ricerca svolta non ho individuato una tesi triennale Mercatorum pubblicamente consultabile con un indice specificamente dedicato a RAG, DP-KSA e scheduling. Questo limite della ricerca non implica che non esistano lavori simili presso l’Ateneo.

### Padova: organizzare il contributo realizzativo di una triennale

**Matteo Bando — _Progettazione e Realizzazione di SyncRAG AI: Un Chatbot con Funzionalità di Retrieval-Augmented Generation (RAG)_**, Università di Padova, laurea triennale in Informatica, a.a. 2023–2024. Consultati frontespizio e indice nel PDF del repository istituzionale, in particolare le pagine numerate viii–ix.

Il lavoro procede dal contesto dello stage ai requisiti, alla progettazione e codifica, fino alla verifica degli obiettivi nelle conclusioni. È un riferimento per dare spazio alle scelte del prototipo. Per la nostra tesi conviene riunire i requisiti nella progettazione e dedicare un capitolo autonomo ai risultati sperimentali. [Tesi nel repository di Padova](https://thesis.unipd.it/retrieve/4560a34b-2c9f-4835-8c59-df1ec07b7b98/Bando_Matteo.pdf)

### Bari: separare metodo, realizzazione e sperimentazione

**Giannantonio Sanrocco — _Large Language Models e Retrieval-Augmented Generation: un caso di studio per l’accesso ai bandi regionali della Puglia_**, Università di Bari “Aldo Moro”, laurea triennale in Informatica, a.a. 2023–2024. Consultati frontespizio e indice nel testo reso pubblico dall’autore su ResearchGate.

La struttura distingue introduzione, stato dell’arte, metodologia, implementazione, sperimentazione e conclusioni. La parte sperimentale comprende tempi di recupero, tempi di risposta e risultati. È il riferimento più utile per la progressione del nostro elaborato: basi teoriche, soluzione proposta, protocollo, evidenze. Nella proposta riduco lo spazio teorico e accorpo realizzazione e metodologia sperimentale per rispettare la dimensione Mercatorum. [Tesi resa disponibile dall’autore](https://doi.org/10.13140/RG.2.2.29929.56167)

### Padova: un confronto tematico sui ticket aziendali, di livello magistrale

**Hannane Habibi — _Offline LLM-Powered RAG Chatbot for Enterprise Knowledge Retrieval: Design and Evaluation_**, Università di Padova, tesi magistrale in Computer Science, anno indicato nel frontespizio: 2025. Consultati frontespizio, abstract e indice nel repository istituzionale.

La tesi riguarda un assistente RAG locale su documentazione aziendale e ticket Znuny/OTRS. Distingue architettura, scelta degli strumenti e valutazione, con misure separate per recupero, generazione e latenza. È utile per motivare il caso ticket e separare le dimensioni della valutazione. La sua ampiezza magistrale non è il modello dimensionale da seguire. Inoltre, l’esecuzione interamente locale è un’impostazione diversa dal nostro rilascio filtrato verso il cloud. [Tesi nel repository di Padova](https://thesis.unipd.it/retrieve/59466234-fd25-4189-912a-9999d4f8843f/Habibi_Hannane.pdf)

## Materiali del progetto da usare durante la stesura

| Materiale                                                                                                                                                     | Uso nella tesi                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [Proposta iniziale](</Users/toni/Documents/ObsidianMainVault/MainVault/UNI/Tesi/Studi di Partenza/Proposta_Tesi_Scheduler_DP_RAG.md>)                         | Motivazione e collegamento con Architetture e Reti; aggiornare gli obiettivi allo stato effettivo del lavoro. |
| [Architettura del PoC](</Users/toni/Documents/ObsidianMainVault/MainVault/UNI/Tesi/Studi di Partenza/poc/ARCHITECTURE.md>)                                    | Flusso, confini di fiducia e definizioni delle misure per i capitoli 2 e 3.                                   |
| [Meccanismo e contabilizzazione della privacy](</Users/toni/Documents/ObsidianMainVault/MainVault/UNI/Tesi/Studi di Partenza/poc/docs/PRIVACY_ACCOUNTING.md>) | Ipotesi, adattamenti rispetto al paper e limiti della garanzia.                                               |
| [Configurazione](</Users/toni/Documents/ObsidianMainVault/MainVault/UNI/Tesi/Studi di Partenza/poc/docs/CONFIGURATION.md>)                                    | Parametri e riproducibilità delle prove.                                                                      |
| [Risultati sui ticket sintetici](</Users/toni/Documents/ObsidianMainVault/MainVault/UNI/Tesi/Studi di Partenza/poc/docs/ticket_demo/RISULTATI.md>)            | Caso applicativo e limiti osservati del rilascio e della sintesi.                                             |
| [Risultati sul corpus salariale fittizio](</Users/toni/Documents/ObsidianMainVault/MainVault/UNI/Tesi/Studi di Partenza/poc/docs/azienda_demo/RISULTATI.md>)  | Primo confronto adattivo/fisso ed effetto dei documenti non pertinenti.                                       |

## Scelte da mantenere nella prossima revisione

Tenere lo scheduler al centro, con i ticket sintetici come caso applicativo e il corpus salariale come controllo. Limitare lo stato dell’arte ai concetti utilizzati e discutere la privacy al livello necessario per motivare l’architettura e i risultati. Non serve trasformare la triennale in una nuova dimostrazione teorica di DP-KSA.

La struttura resta utilizzabile anche con gli attuali esperimenti locali, dichiarandone i limiti. Le estensioni a nuovi modelli, hardware o provider possono ampliare le evidenze del capitolo 4 senza richiedere nuovi capitoli. La sinossi andrà scritta alla fine, quando domanda, metodo e conclusioni saranno definitivi.
