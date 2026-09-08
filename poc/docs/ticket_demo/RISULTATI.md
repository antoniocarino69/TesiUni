# Prova locale dell'8 settembre 2026

80 ticket sintetici, Qwen2.5 0.5B Instruct Q4_K_M, macOS ARM64.
160 bozze reali e due sintesi locali aggiuntive, nessuna chiamata esterna.
Durata complessiva: 82,28 secondi. Configurazione, hash e misure aggregate
sono in [risultati.json](risultati.json); il report diagnostico completo
rimane in `poc/reports/ticket_demo.json`, ignorato da Git.

Le prime tre query recuperano 40 ticket E42 di 40 clienti distinti.
Per E99 non esistono ticket pertinenti. Il corpus contiene complessivamente
71 clienti, con un massimo di dieci ticket per cliente: nessuna garanzia
a livello di cliente viene attribuita a questo esperimento.

## Rilascio condizionale sulle bozze osservate

Ogni cella deriva da 500 prove indipendenti del rumore, su bozze congelate.
Sono frequenze empiriche, non probabilità esatte né misure su altri corpus.

| Caso, N=40 | epsilon=1 | epsilon=4 | epsilon=8 |
|---|---:|---:|---:|
| Procedura: presenza dei termini di tutti e tre i passaggi | 0% | 51,4% | 99,8% |
| Codice unico: rilascio di un identificativo unico | 0% | 0% | 0% |
| Identificativo interno condiviso: rilascio | 5,6% | 100% | 100% |
| Errore assente: rilascio di keyword | 0,2% | 23% | 98,2% |

Per la procedura, N=5 e N=10 non hanno prodotto rilasci nei campioni;
N=20 raggiunge il 13,6% con epsilon=8 e zero con epsilon=1 o 4.
23 bozze su 40 contengono i termini di tutti i passaggi; alcune sono troncate
o aggiungono una raccomandazione di rivolgersi al tecnico.

Nell'intera griglia del codice unico è avvenuto **un rilascio di identificativo
unico**, con N=5 ed epsilon=1 (1/500 in quella cella). Non si può quindi
affermare che i dettagli unici non escano mai. Il meccanismo ha un failure
event PTR non nullo; una singola frequenza su 500 prove non ne stima bene
la probabilità rara. Anche le celle con zero eventi non dimostrano rischio zero.

L'identificativo `clusterinternoaurora`, presente in tutti i ticket E42,
compare in tutte le 40 bozze della relativa domanda e viene conservato
frequentemente. Il filtro limita l'influenza individuale, ma non oscura
automaticamente un'informazione interna ampiamente condivisa.

Il caso E99 evidenzia un altro limite: nessuna delle 40 bozze si astiene con
«non disponibile». Il modello riutilizza procedure di E42 o inventa risposte.
Il consenso su una risposta sbagliata può passare il filtro: DP non certifica
pertinenza o correttezza. Il singolo rilascio vuoto osservato nella pipeline
E99 non basta quindi a dichiarare risolto questo problema.

## Risposte effettive della pipeline

Le quattro richieste reali usano N=40, epsilon nominale 4 e un account comune.
Accounting finale: epsilon circa 12,1289 e delta 0,0005. Non si sommano a
questo valore le repliche diagnostiche con account nuovi. La configurazione
fissa eccede lo SLA stimato di 30 secondi (stima: 184,2 secondi per richiesta).

Per E42 sono state rilasciate `arrestare, cache, cancellare, ferrosync, locale,
riavviare, ricorrere, servizio, tecnico`. La successiva sintesi locale ha
menzionato solo il riavvio e prodotto una frase troncata: **la procedura finale
non è completa**, anche se tutte le parole necessarie erano disponibili.
Per il cluster sono state rilasciate le keyword corrette, ma la sintesi locale
ha inventato «E42, 1144000000». Per codice unico ed E99 il rilascio effettivo
era vuoto e la sintesi si è astenuta.

Questa prima baseline rende il caso ticket utile alla tesi, ma non dimostra
ancora un assistente affidabile. Servono una valutazione separata del modello
di sintesi con prompt adeguato, controllo manuale di sequenza e correttezza,
e prove con ticket linguisticamente più vari e risoluzioni in conflitto.
Il prompt breve dell'estrattore e il modello da 0,5B sono limiti espliciti
della sintesi locale qui misurata; la qualità di un cloud reale non è stata testata.
