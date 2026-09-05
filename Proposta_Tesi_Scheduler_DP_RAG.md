# Proposta di Tesi di Laurea

**Cattedra di riferimento:** Architetture e Reti di Calcolatori  
**Titolo di lavoro:** *Allocazione Adattiva e Modellazione Prestazionale in Architetture Ibride Edge-Cloud per RAG a Privacy Differenziale*  
**Paper di riferimento principale:** *Differentially Private Retrieval-Augmented Generation* (framework DP-KSA)

---

## 1. Motivazione e Inquadramento Accademico

I sistemi di generazione aumentata dal recupero di dati (*Retrieval-Augmented Generation*, RAG) consentono ai modelli linguistici di consultare archivi documentali privati per formulare risposte aggiornate e prive di allucinazioni. Tuttavia, quando i documenti contengono informazioni riservate o sensibili, inviare tali contenuti a servizi di generazione remoti ospitati in Cloud introduce un rischio concreto di fuga di dati (*data leakage*).

La letteratura recente (in particolare lo studio su *DP-KSA*) propone di risolvere questo problema applicando la **Privacy Differenziale (DP)** prima della trasmissione:
1. Un modello linguistico compatto eseguito in locale legge i documenti sensibili e genera un gruppo di risposte preliminari (*ensemble*).
2. Un algoritmo statistico estrae le parole chiave più frequenti applicando un meccanismo di rumore controllato (*Propose-Test-Release*).
3. Solo le parole chiave così purificate vengono inviate al Cloud, garantendo matematicamente l'anonimato del documento d'origine.

### Perché riguarda Architetture e Reti di Calcolatori?
Il collo di bottiglia di questo approccio non è teorico, ma prettamente **sistemistico e architetturale**:
- **A livello di Calcolatori:** Generare decine di risposte preliminari con un modello locale sottopone l'hardware a uno sforzo intensivo. Sui dispositivi di fascia consumer, ciò comporta una rapida saturazione della memoria (RAM di sistema o memoria grafica) e un decadimento delle prestazioni dovuto all'innalzamento della temperatura nei carichi prolungati (*thermal throttling*).
- **A livello di Reti:** Il tempo totale necessario per rispondere all'utente è la somma del tempo di calcolo locale e del tempo di comunicazione di rete verso il Cloud. Trasferire poche parole chiave riduce drasticamente il volume di dati scambiati rispetto all'invio di testi completi, ma l'elaborazione locale introduce un ritardo significativo.

La tesi non si concentra sulla dimostrazione matematica della privacy, ma sulla **progettazione e validazione sperimentale di uno scheduler adattivo**, supportato da un modello analitico, capace di decidere la configurazione di calcolo ottimale in base alle risorse dell'hardware locale e allo stato della connessione di rete.

---

## 2. Il Modello Analitico e la Logica dello Scheduler

### Obiettivo
Determinare dinamicamente il numero di risposte da generare in locale ($N$, dimensione dell'ensemble) e il modello da impiegare, in modo da massimizzare la protezione dei dati rispettando un vincolo prefissato sul tempo di attesa dell'utente ($T_{\text{max}}$).

### Componenti del Tempo Totale
Il tempo complessivo di completamento di una richiesta è formulato come:

$$T_{\text{totale}} = T_{\text{recupero}} + T_{\text{calcolo\_locale}}(N, M, A) + T_{\text{filtro\_DP}}(N) + T_{\text{rete}}(\text{dati}, R) + T_{\text{cloud}}$$

Dove:
- $T_{\text{recupero}}$: tempo per reperire i documenti rilevanti dall'archivio locale.
- $T_{\text{calcolo\_locale}}(N, M, A)$: tempo impiegato dal calcolatore locale per generare $N$ risposte preliminari, funzione del modello $M$ (es. 1B o 3B parametri a 4-bit) e dell'architettura hardware $A$.
- $T_{\text{filtro\_DP}}(N)$: tempo necessario per conteggiare i termini, aggiungere il rumore statistico e verificare il superamento della soglia di rilascio.
- $T_{\text{rete}}(\text{dati}, R)$: tempo di trasmissione attraverso la rete, determinato dalla dimensione del messaggio (poche decine di byte per le sole parole chiave) e dallo stato della linea $R$ (latenza di andata e ritorno e larghezza di banda).
- $T_{\text{cloud}}$: tempo impiegato dal servizio remoto per formulare la risposta finale a partire dalle parole chiave ricevute.

### Logica Decisionale
Lo scheduler valuta prima di ogni richiesta:
1. **Lo stato della rete ($R$):** rileva la latenza corrente verso il server remoto. Se la rete è lenta o instabile, il margine temporale per il calcolo locale si riduce.
2. **Lo stato del dispositivo ($A$):** monitora la memoria libera disponibile e l'eventuale riduzione di frequenza dei processori dovuta al calore accumulato.
3. **La selezione del parametro $N$:** calcola il valore massimo di $N$ compatibile con il vincolo:

$$T_{\text{totale}} \le T_{\text{max}}$$

Garantendo che all'aumentare delle risorse disponibili venga eseguito un ensemble più numeroso (che migliora la precisione del filtraggio privato), mentre in condizioni di rete congestionata o surriscaldamento del dispositivo il carico venga ridotto in modo controllato.

---

## 3. Metodologia Sperimentale

### Piattaforme Hardware a Confronto
I test verranno condotti su due architetture con caratteristiche costruttive diametralmente opposte:
1. **Architettura SoC con Memoria Unificata (Apple Silicon M1):**
   - 8 GB di memoria condivisa tra processore centrale e acceleratore grafico.
   - Raffreddamento passivo senza ventole: ideale per studiare il decadimento progressivo delle frequenze di calcolo su serie prolungate di generazioni.
2. **Architettura Tradizionale x86 con Acceleratore Dedicato:**
   - Processore Intel/AMD con scheda video Nvidia RTX 2070 Mobile (8 GB di memoria grafica dedicata).
   - Raffreddamento attivo ad aria con ventole: separazione netta tra memoria di sistema e memoria grafica, con potenziale collo di bottiglia nel trasferimento dati sul bus PCIe.

### Motore di Esecuzione Locale
Per garantire che il confronto tra le due piattaforme sia rigoroso e imparziale, i modelli verranno eseguiti tramite **`llama.cpp`** (o interfaccia Python correlata):
- Utilizzo degli stessi identici file binari di modello con quantizzazione a 4-bit (formato GGUF).
- Sfruttamento dell'accelerazione nativa su entrambi i sistemi: Metal su Apple Silicon e CUDA su Nvidia.
- Misurazione al millisecondo del tempo per il primo token (*Time-To-First-Token*, TTFT) e della velocità di generazione successiva.

### Modelli e Carico di Lavoro
- **Taglie di modello:** 1 miliardo (1B) e 3 miliardi (3B) di parametri (es. famiglie Qwen 2.5 o Llama 3.2 quantizzate a 4-bit).
- **Curva di scalabilità:** variazione della dimensione dell'ensemble da 5 a 30 generazioni sequenziali o in lotti, per tracciare con precisione il punto in cui la memoria si satura e si innesca il rallentamento termico.

### Banco di Prova dei Dati
- Selezione di un campione compatto e riproducibile di 50-100 quesiti estratti da dataset accademici standard (es. SQuAD o HotpotQA).
- La dimensione contenuta del campione permette di ripetere i cicli di test più volte per ottenere medie stabili e quantificare la deviazione standard senza richiedere tempi di calcolo proibitivi.

### Simulazione della Rete
- Profilazione del comportamento del sistema sotto tre scenari di connettività simulata:
  1. *Rete ottimale:* bassa latenza e banda elevata (fibra/Wi-Fi aziendale).
  2. *Rete media:* latenza moderata e variazioni occasionali (connessione mobile 4G/5G ordinaria).
  3. *Rete degradata:* latenza alta e pacchetti ritardati, per verificare la capacità dello scheduler di ridurre il carico locale per restare nei tempi previsti.

---

## 4. Metriche Rilevate

1. **Prestazioni dell'Hardware:**
   - Tempo di avvio della generazione (TTFT) per ogni elemento dell'ensemble.
   - Velocità di emissione dei token (token al secondo).
   - Picco di memoria fisica e virtuale occupata durante l'esecuzione.
   - Variazione dei tempi di risposta tra la prima e l'ultima iterazione di cicli intensivi (indice di rallentamento per calore).
2. **Parametri di Rete:**
   - Volume complessivo di dati trasmessi (confronto tra il peso dei documenti integrali e quello delle sole parole chiave).
   - Latenza di andata e ritorno verso il servizio remoto.
   - Tempo complessivo percepito (*end-to-end*).
3. **Qualità ed Efficacia:**
   - Livello teorico di privacy garantito in base al numero di risposte e alla soglia di estrazione.
   - Conservazione delle informazioni necessarie affinché la risposta finale risulti corretta.

---

## 5. Indice Provvisorio della Tesi

- **Capitolo 1: Introduzione e Obiettivi**
  - Il compromesso tra riservatezza delle informazioni e risorse di calcolo.
  - Motivazioni architetturali e distribuzione del carico tra periferia e centro.
  - Contributo originale del lavoro.
- **Capitolo 2: Stato dell'Arte e Fondamenti**
  - Pipeline di generazione aumentata dal recupero (RAG).
  - Principi di base della Privacy Differenziale applicata all'elaborazione del testo.
  - Caratteristiche delle moderne architetture per l'esecuzione locale di modelli linguistici (SoC con memoria unificata vs sistemi con acceleratore dedicato).
- **Capitolo 3: Modello Analitico e Progettazione dello Scheduler**
  - Scomposizione dei tempi del sistema distribuito.
  - Formulazione della funzione di costo e dei vincoli temporali.
  - Algoritmo di decisione per la scelta della taglia del modello e dell'ampiezza dell'ensemble.
- **Capitolo 4: Allestimento dell'Ambiente Sperimentale**
  - Specifiche delle piattaforme hardware utilizzate.
  - Configurazione dell'ambiente di esecuzione con `llama.cpp` e modelli a 4-bit.
  - Metodologia per l'emulazione dei profili di rete e la raccolta dei dati di telemetria.
- **Capitolo 5: Risultati Sperimentali e Analisi Comparativa**
  - Comportamento a confronto tra Apple M1 e x86/RTX 2070 (tempi, memoria, stabilità termica).
  - Validazione sul campo dello scheduler al variare della connettività.
  - Discussione del bilanciamento tra tempo di attesa, traffico risparmiato e livello di protezione.
- **Capitolo 6: Conclusioni e Sviluppi Futuri**
  - Sintesi delle conclusioni operative.
  - Possibili estensioni ad ambienti distribuiti federati o dispositivi a bassissimo consumo.

---

## 6. Piano Operativo di Lavoro

| Fase | Attività Principali | Risultato Atteso |
| :--- | :--- | :--- |
| **1. Configurazione ambiente** | Installazione di `llama.cpp` con Metal su Mac e CUDA su PC; conversione e download dei modelli 1B e 3B in formato GGUF a 4-bit. | Ambiente operativo e test iniziale di generazione eseguito con successo su entrambe le macchine. |
| **2. Pipeline del filtro locale** | Scrittura dello script per l'esecuzione dell'ensemble, estrazione dei termini e applicazione della procedura di conteggio con rumore statistico. | Modulo software funzionante in grado di produrre le parole chiave private a partire da un testo di prova. |
| **3. Raccolta dati hardware** | Esecuzione dei cicli di test variando l'ampiezza dell'ensemble (5-30) e registrazione di tempi, memoria e temperature su entrambe le macchine. | Serie storiche e tabelle comparative sulle prestazioni e sull'impatto termico dei due sistemi. |
| **4. Integrazione dello scheduler** | Implementazione della logica decisionale con test sotto i diversi scenari di latenza di rete simulata. | Verifica del rispetto dei tempi massimi prefissati al variare della connessione. |
| **5. Stesura finale** | Elaborazione dei grafici riassuntivi e redazione dei singoli capitoli della tesi. | Tesi completata e pronta per la revisione del relatore. |
