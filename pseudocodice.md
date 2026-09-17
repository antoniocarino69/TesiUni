# Pseudocodice del sistema

Questo documento spiega il funzionamento attuale con parole leggibili. Non è codice da eseguire e non sostituisce le formule e le ipotesi di `poc/docs/PRIVACY_ACCOUNTING.md`.

Una **inferenza locale** è una volta in cui il modello sul computer legge una domanda e un estratto e genera una breve risposta. **N** indica quante inferenze pianificare; **k** indica quante parole proporre al filtro. Sono due numeri diversi.

## Setup di sessione: calibrazione delle velocità e probe cloud

All'avvio della sessione sperimentale, prima di elaborare le domande, il
sistema misura le velocità reali del modello locale con prove su testi
pubblici. Se sono configurate credenziali cloud, esegue anche una sola
generazione pubblica di probe per misurare `E2E_cloud_ms` end-to-end.

```text
ALL'AVVIO DELLA SESSIONE (una sola volta):

    SE la calibrazione è attiva (default):
        carica il modello locale

        PER OGNI lunghezza rappresentativa (256, 512, 1024 token):
            prepara un testo pubblico di quella lunghezza
            esegui una inferenza di prova con il testo
            misura il tempo totale e i token elaborati
            stima la velocità di lettura (prefill) e di scrittura (generazione)

        velocità_prefill = media delle velocità di lettura misurate
        velocità_generazione = media delle velocità di scrittura misurate
        tempo_calibrazione = tempo totale delle prove

    ALTRIMENTI (--no-calibration):
        usa le velocità di default (prefill=250, generazione=50 tok/s)
        tempo_calibrazione = 0

    SE credenziali cloud configurate e non --offline-cloud:
        esegui una generazione pubblica di probe
            (prompt fisso, max 16 token, niente contenuti privati)
        misura il tempo complessivo della chiamata
        E2E_cloud_ms = tempo misurato dal probe
        cloud_probe_skipped = falso
    ALTRIMENTI:
        E2E_cloud_ms = RTT + tempo_cloud_ms (stima manuale)
        cloud_probe_skipped = vero

    # Il probe alimenta la tolleranza A2 al posto della stima manuale;
    # il suo costo entra in cli_total_ms, mai in request_ms.

    mantieni il modello e le misure in memoria per tutta la sessione
```

Le misure valgono per la macchina, il regime termico e la versione del modello della sessione corrente. Il tempo di calibrazione è riportato separatamente dal tempo delle singole richieste. Il costo del probe entra in `cli_total_ms` ma non in `request_ms`: il probe è setup di sessione, non lavoro utile.

## Percorso generale

```text
QUANDO ARRIVA UNA DOMANDA:

    # setup di sessione già eseguito: velocità locali e (se disponibili)
    # E2E_cloud_ms dal probe. Le velocità restano in memoria per tutta la
    # sessione; il probe non viene rieseguito per ogni domanda.

    leggi il tempo massimo desiderato
    leggi le velocità locali (calibrate all'avvio o di default)
    leggi il tempo previsto per rete e cloud

    stima il tempo di una inferenza locale:
        tempo per leggere il massimo testo consentito
        + tempo per scrivere il massimo output consentito

tempo_disponibile =
        tempo_massimo - tempo_rete - tempo_cloud
 
     N = quante inferenze entrano nel tempo_disponibile
     limita N al numero di posti pubblici disponibili e al massimo di 40
 
     SE N è minore di 5:
         SE k_sforamento > 0:
             calcola sforamento_previsto = tempo_per_5_inferenze - tempo_massimo
             # tolleranza usa E2E_cloud_ms: probe A1 se disponibile, altrimenti
             # fallback manuale (tempo_rete + tempo_cloud) come qui sotto.
             tolleranza = k_sforamento × (tempo_rete + tempo_cloud)
             SE sforamento_previsto <= tolleranza:
                 N = 5
                 sforamento_accettato = vero
             ALTRIMENTI:
                 N = 0
                 sforamento_accettato = falso
         ALTRIMENTI:
             N = 0
             sforamento_accettato = falso
 
     SE flag force_zero_shot:
         N = 0
         sforamento_accettato = falso

    parole_da_inviare = lista vuota

    SE N è maggiore di 0:

        SE il budget privacy non basta:
            interrompi e segnala il problema

        documenti = cerca N documenti pertinenti alla domanda
        risposte_locali = lista vuota

        PER OGNI posto pianificato, uno dopo l'altro:

            SE manca un documento:
                aggiungi una risposta vuota
                passa al posto successivo

            estratto = scegli una parte pertinente del documento
            limita il testo alla dimensione consentita

            risposta = chiedi al modello locale:
                "Rispondi a questa domanda usando questo estratto"

            aggiungi risposta a risposte_locali

        conteggi = conta in quante risposte compare ogni parola
        conta ogni parola al massimo una volta per risposta

        applica il filtro privacy:
            k = FindBestK(conteggi)
            parole_da_inviare = TopKWithPTR(conteggi, k)
            contabilizza il consumo del budget privacy,
            anche quando non vengono rilasciate parole

    SE parole_da_inviare non è vuota:
        chiedi al cloud di rispondere usando:
            domanda + parole_da_inviare
    ALTRIMENTI:
        chiedi al cloud di rispondere alla sola domanda

    SE il provider segnala un errore:
        registra e segnala l'errore
    ALTRIMENTI:
        restituisci la risposta finale

    registra tempi e risultati della prova
```

Lo scheduler sceglie N **prima della ricerca dei documenti** e non cambia decisione durante le inferenze. Usa limiti pubblici del testo, non le lunghezze misurate nei documenti privati. Se mancano documenti, non duplica quelli esistenti per raggiungere N.

Il percorso sopra descrive la modalità adattiva. Negli esperimenti si può anche imporre un N fisso per confrontarlo con lo scheduler, accettando che superi il tempo stimato.

## FindBestK: scegliere quante parole proporre

Esempio di conteggi ordinati:

| Parola | Risposte che la contengono |
| --- | ---: |
| Roma | 10 |
| capitale | 9 |
| Italia | 8 |
| città | 3 |
| storia | 2 |

Il distacco fra la terza e la quarta parola è 8 − 3 = 5. Questo suggerisce di proporre tre parole. FindBestK rende casuale la scelta per limitarne la dipendenza dal singolo documento.

```text
FUNZIONE FindBestK(conteggi):

    ordina i conteggi dal più alto al più basso
    considera zero i conteggi mancanti

    PER OGNI k consentito dalla configurazione pubblica:

        distacco = conteggio in posizione k
                   - conteggio in posizione successiva

        punteggio = distacco
                    + eventuale preferenza pubblica per k
                    + rumore casuale Gumbel

    restituisci il k con il punteggio più alto
```

Il dominio predefinito è k da 1 a 10. Il codice usa rumore Gumbel con scala **4/ε**, dove ε è il budget assegnato a FindBestK. È l'adattamento conservativo documentato rispetto all'Algoritmo 3 del paper; la motivazione completa è in `poc/docs/PRIVACY_ACCOUNTING.md`.

## TopKWithPTR: decidere se rilasciare le parole

```text
FUNZIONE TopKWithPTR(conteggi, k):

    individua le k parole più frequenti

    calcola il distacco tra:
        il conteggio in posizione k
        e il conteggio in posizione successiva

    esegui il test sul distacco:
        applica la formula prevista
        usando rumore gaussiano e una soglia di privacy

    SE il test passa:
        restituisci soltanto le parole osservate selezionate,
        ordinate alfabeticamente
    ALTRIMENTI:
        restituisci una lista vuota
```

Gumbel interviene nella scelta di **quante** parole proporre. Il test con rumore gaussiano decide **se** rilasciare quel gruppo. Il passaggio del test non equivale a una certezza assoluta di sicurezza: la garanzia dipende dalla formula, dal budget e dalle ipotesi documentate.

## Che cosa riceve il cloud

Il provider della risposta finale riceve la domanda e le parole rilasciate. Non riceve gli estratti o le risposte locali. Quando il filtro non rilascia parole, attualmente il cloud risponde usando la propria conoscenza generale.

Non è garantito che le parole siano sufficienti per una risposta utile: questo va verificato negli esperimenti. Il filtro privacy non controlla la correttezza della risposta. Senza provider configurato, oppure in modalità offline, il programma usa una simulazione che non permette di misurare la qualità della risposta cloud.

Report e telemetria sono diagnostica sperimentale separata dalla garanzia DP; la modalità di diagnostica completa autorizzata può contenere informazioni sensibili, come specificato in `AGENTS.md`.

## Setup implementato
 
- La calibrazione automatica delle velocità di inferenza è implementata nel modulo `core/calibration.py` e attivata di default nella CLI. Il flag `--no-calibration` la disattiva e ripristina i valori di default.
- **Soglia di sforamento accettabile (A2):** lo scheduler espone `--sforamento-k`. Con `k>0`, se il piano minimo non entra nello SLA, lo sforamento previsto per `N_MIN` viene confrontato con `k × E2E_cloud_ms`; se rientra nella tolleranza pianifica `N=N_MIN` e segnala `sforamento_accettato`. Con `k=0` (default) resta il comportamento prudente. `--force-zero-shot` forza `N=0` ignorando SLA e tolleranza.
- **Probe cloud E2E (A1):** la CLI esegue una sola generazione pubblica di sessione (`core/cloud.py::CloudGenerator.probe`) e usa il valore misurato di `E2E_cloud_ms` per alimentare la tolleranza A2 al posto della somma manuale `RTT + tempo_cloud_ms`. Il costo del probe (`cloud_probe_ms`) entra in `cli_total_ms`, mai in `request_ms`. Con `--offline-cloud` o senza credenziali il probe viene saltato e `cloud_probe_skipped=True`.
- **Etichette sperimentali (A3):** dopo la risposta cloud, `core/etichette.py::classifica_risultato` calcola una label (`insufficienti`, `errore`, `completo`, `degradato`) su `(decisione, dp, risposta)` con la variante stretta per ticket quando il `RequestConfig` include `riferimenti_ticket`. Sono metadati di analisi: non cambiano prompt, sequenza di chiamate né comportamento. Disattivabili con `--no-etichette`.
- **Estensioni benchmark (A4):** `benchmark_scheduler.py` calibra automaticamente le velocità locali all'avvio (default) e propaga i valori misurati a ogni `RequestConfig`. CLI e REPL accettano `--no-calibration`, `--tok-per-sec-prefill`, `--tok-per-sec-generazione`. Allineato con `run_pipeline.py`.
- **Telemetria hardware (A5):** `core/telemetry_hw.py` raccoglie snapshot del "ferro" (temperatura CPU/GPU, util, RAM, VRAM, Watt, memory pressure) via `powermetrics`/`nvidia-smi`/`sensors`/`top`/`vm_stat`. CLI e REPL accettano `--hw-metrics` (istantanei) e `--hw-sample-period N` (sampler continuo su thread). `LocalNeuralEngine.genera_bozza` misura il TTFT reale via stream llama-cpp (`tempo_prefill_reale_sec`), distinto dalla stima euristica (`tempo_prefill_stimato_sec`). Report JSON: `prefill_real_ms`, `hw_before`, `hw_after`, `hw_samples`. 

## Storico sviluppi (chiusi al 16/09/2026)

Tutte le funzionalità concordate A1–A5 risultano implementate e coperte dai
test al commit di audit. L'elenco originale degli sviluppi previsti si è
esaurito; questa sezione resta come riferimento storico. Eventuali
sviluppi futuri vanno aggiunti qui sotto, con data e branch di lavoro.


