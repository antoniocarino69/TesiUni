# Spunti per Tesi di Laurea in Architetture e Reti di Calcolatori

Sulla base dell'analisi dei 6 studi forniti, sono emersi diversi "nodi irrisolti" e "lavori futuri" (Future Work) particolarmente rilevanti per l'ambito delle **Architetture e Reti di Calcolatori**. Di seguito sono proposti 6 spunti di tesi, ciascuno derivato dalle criticità di uno specifico paper.

---

## 1. Ottimizzazione del Trade-off Latenza-Sicurezza in Infrastrutture RAG On-Premises
**Derivato da:** _AI Engineering Blueprint for On-Premises_
* **Nodo Irrisolto / Future Work:** I sistemi RAG aziendali on-premises richiedono continui controlli di sicurezza (guardrails, verifica degli accessi, sanitizzazione). Essendo questi servizi spesso disaccoppiati (es. tramite API RESTful), introducono un severo collo di bottiglia a livello di rete e aumentano drasticamente la latenza (Time-To-First-Token). Manca inoltre un'orchestrazione hardware specifica per il deployment locale.
* **Proposta di Tesi:** Progettare e valutare un'architettura di rete ottimizzata (utilizzando protocolli più efficienti come gRPC o la shared memory) e sviluppare un modulo proxy/middleware a livello Edge. L'obiettivo è parallelizzare i controlli di sicurezza e ridurre l'overhead di latenza delle comunicazioni interne nel cluster on-premises, misurando le prestazioni su risorse computazionali vincolate.

## 2. Architetture Ibride Edge-Cloud con Allocazione Adattiva per RAG a Privacy Differenziale
**Derivato da:** _Differentially Private Retrieval-Augmented Generation_
* **Nodo Irrisolto / Future Work:** L'applicazione della Privacy Differenziale (DP) e del paradigma _Propose-Test-Release_ (PTR) per le query RAG richiede la generazione di multipli "ensemble" locali. Questo satura rapidamente la memoria dei dispositivi hardware consumer (Edge) e porta a rendimenti decrescenti in termini di prestazioni e tempo di computazione.
* **Proposta di Tesi:** Sviluppare uno "scheduler adattivo" hardware-aware per nodi Edge. Il sistema dovrebbe calibrare dinamicamente il numero di ensemble da generare in base alla latenza di rete rilevata verso il Cloud e allo stato hardware del dispositivo (RAM disponibile, carico GPU/NPU), ottimizzando il bilanciamento tra garanzie di privacy matematiche, risorse computazionali impiegate e latenza complessiva.

## 3. Smart Edge-Router: Ottimizzazione del Traffico di Rete tramite Valutazione dell'Incertezza Locale
**Derivato da:** _When Retrieval Succeeds and Fails - Rethinking Retrieval-Augmented Generation for LLMs_
* **Nodo Irrisolto / Future Work:** I sistemi RAG attuali spesso innescano interrogazioni di rete verso database vettoriali o API esterne anche quando il modello possiede già la conoscenza per rispondere. Questo approccio "statico" spreca preziosa larghezza di banda e risorse computazionali, aumentando inutilmente l'overhead architetturale.
* **Proposta di Tesi:** Progettare un'architettura Edge in cui un modello estremamente leggero (Small Language Model) funga da "Smart Router". Il sistema calcolerebbe una metrica di incertezza locale per decidere dinamicamente se risolvere la query in locale (risparmiando rete) o attivare la pipeline RAG verso il Cloud. La tesi misurerebbe l'abbattimento del traffico di rete, i costi di API e il guadagno in termini di latenza.

## 4. Pre-Elaborazione Edge e Firewall per RAG Aziendali
**Derivato da:** _Optimizing and Evaluating Enterprise Retrieval-Augmented Generation (RAG)_
* **Nodo Irrisolto / Future Work:** In contesti enterprise, i sistemi RAG dipendono pesantemente da API Cloud per l'indicizzazione e l'inferenza, ma sono vulnerabili a prompt avversariali e fughe di dati sensibili (PII, IP, email). La pre-elaborazione centralizzata impone carichi enormi sulla rete interna e aumenta la complessità del Cloud.
* **Proposta di Tesi:** Ideare e implementare un "Firewall e Pre-processore Edge" dedicato alle applicazioni basate su LLM. Il modulo, posizionato sui nodi perimetrali della rete aziendale, si occuperebbe della sanitizzazione real-time dei dati e dell'ottimizzazione (chunking adattivo) dei payload prima del loro invio all'API Cloud. Lo studio valuterebbe l'impatto sulla riduzione del traffico di rete (payload size) e sui tempi di elaborazione end-to-end.

## 5. Architetture di Caching Gerarchico e Speculative Pipelining su Nodi Edge
**Derivato da:** _Retrieval-Augmented Generation - A Comprehensive Survey..._
* **Nodo Irrisolto / Future Work:** Le pipeline RAG soffrono di latenze enormi dovute alla sequenzialità delle operazioni (recupero dati $\rightarrow$ lettura $\rightarrow$ generazione). Soluzioni come il caching non bastano per gestire le query "long-tail". Inoltre, in reti distribuite, il fetching di conoscenze da più fonti causa colli di bottiglia severi.
* **Proposta di Tesi:** Progettare un'infrastruttura di memoria ("RAG-Cache" gerarchica) abbinata a tecniche di _speculative pipelining_ (sovrapposizione a livello architetturale tra le chiamate di rete per il retrieval e la generazione dei primi token). Il lavoro valuterà come queste tecniche possano massimizzare la reattività di sistema su architetture hardware limitate, diminuendo drasticamente l'impatto della latenza di rete distribuita.

## 6. Mitigazione dell'Overhead di Rete in Sistemi RAG Federati (Federated Learning)
**Derivato da:** _Privacy-Preserving Federated Embedding Learning_
* **Nodo Irrisolto / Future Work:** L'utilizzo del Federated Learning per addestrare sistemi RAG decentralizzati, unito all'applicazione della Crittografia Omomorfa (Fully Homomorphic Encryption), genera un costo di comunicazione estremo (payload criptati di grandi dimensioni) e colli di bottiglia computazionali sui dispositivi client, minandone la scalabilità su reti geografiche.
* **Proposta di Tesi:** Analizzare e ottimizzare la topologia di rete per lo scambio di gradienti e vettori criptati in un ambiente Federated-RAG. La tesi potrebbe esplorare strategie di compressione del payload di rete, sparsificazione dei gradienti o l'uso di accelerazione hardware per mitigare il bottleneck di comunicazione, garantendo una sincronizzazione efficiente tra nodi Edge e server centrale senza compromettere i requisiti di sicurezza.
