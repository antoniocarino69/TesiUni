# Pseudocodice del sistema

Questo documento spiega il funzionamento attuale con parole leggibili. Non è codice da eseguire e non sostituisce le formule e le ipotesi di `poc/docs/PRIVACY_ACCOUNTING.md`.

Una **inferenza locale** è una volta in cui il modello sul computer legge una domanda e un estratto e genera una breve risposta. **N** indica quante inferenze pianificare; **k** indica quante parole proporre al filtro. Sono due numeri diversi.

## Setup di sessione: calibrazione delle velocità

All'avvio della sessione sperimentale, prima di elaborare le domande, il sistema misura le velocità reali del modello locale con prove su testi pubblici.

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

    mantieni il modello e le misure in memoria per tutta la sessione
```

Le misure valgono per la macchina, il regime termico e la versione del modello della sessione corrente. Il tempo di calibrazione è riportato separatamente dal tempo delle singole richieste.

## Percorso generale

```text
QUANDO ARRIVA UNA DOMANDA:

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
        N = 0

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

## Sviluppi concordati, ancora da implementare

- Riesaminare il passaggio a N=0 per mancanza di tempo: lo SLA è un obiettivo flessibile e privacy e utilità hanno la precedenza. Il comportamento attuale resta quello descritto sopra.
- Favorire una dichiarazione di informazioni insufficienti quando mancano elementi per rispondere, senza presentare una risposta generale come fondata sui documenti.

