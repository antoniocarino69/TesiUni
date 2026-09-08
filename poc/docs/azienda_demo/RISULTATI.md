# Prove sul corpus salariale — 8 settembre 2026

Eseguite sul computer locale, con Qwen 2.5 0.5B Instruct Q4_K_M tramite
llama.cpp. Il modello era già presente: nessun download, nessuna chiamata
provider e nessun trace Langfuse. Il cloud è stato simulato.

Impronta SHA-256 del GGUF:
`74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.
Sistema registrato: macOS 26.6.2 arm64. Prompt e generazione condivisi con
`core.model_config`: temperatura 0.2, massimo 30 token; cap pubblico prompt
1000 token. Le misure non sono un confronto tra modelli o macchine.

## Estrazione locale

Prima prova: 40 documenti per query, 160 inferenze reali complessive.

| Query | Bozze con la risposta attesa | Risposte effettive | Tempo richiesta a modello caricato |
| --- | ---: | --- | ---: |
| Base Tecnologia T2 | 40/40 | 40 volte `42000` | 13,83 s |
| Base Amministrazione A1 | 20/40 | 20 `36000`, 13 `42000`, 7 `30000` | 13,50 s |
| Base Commerciale C2 | 20/40 | 20 `30000`, 13 `42000`, 7 `36000` | 13,44 s |
| Netto mensile non presente | 8/40 | 8 astensioni, 32 risposte con importi non giustificati | 14,21 s |

Il retrieval porta in testa i documenti del reparto richiesto. Tecnologia ne
ha 40, gli altri reparti 20: per N=40 questi ultimi vengono completati da
documenti di altri reparti. Il piccolo modello risponde anche sulla base dei
documenti non pertinenti, senza rispettare sempre il vincolo della domanda.

Sul netto, le 32 risposte sbagliate comprendono importi annuali lordi e due
frasi che li presentano come netto mensile; una propone `3000 euro`. Le
schede non contengono alcun dato da cui ricavare il netto. Questo è un errore
fattuale del generatore. La garanzia DP non garantisce la verità delle risposte.

## Probabilità empirica di recuperare l'importo corretto

Per ogni combinazione sono state effettuate 500 prove del filtro sulle bozze
reali già ottenute: 4 query × 4 N × 3 epsilon × 500 = 24000 prove.
Le latenze della tabella precedente non derivano da queste repliche. Il dominio
pubblico di k è 1..10, delta PTR 1e-4 e delta totale per prova 2e-4.

Per Tecnologia, tutte le bozze contengono lo stesso importo `42000`:

| N | ε=1: recupero importo | ε=4: recupero importo | ε=8: recupero importo |
| ---: | ---: | ---: | ---: |
| 5 | 0,0% | 0,2% | 0,6% |
| 10 | 0,0% | 3,2% | 34,2% |
| 20 | 0,0% | 59,8% | 100,0% |
| 40 | 5,8% | 100,0% | 100,0% |

Con ε=1 il filtro resta prudente anche con 40 risposte corrette e concordi.
Un valore di epsilon più alto facilita il rilascio ma indebolisce la protezione;
non viene consigliato come impostazione per salari reali.

L'effetto di N cambia quando i documenti pertinenti sono soltanto 20:

| Reparto | N=20, ε=4 | N=40, ε=4 | N=20, ε=8 | N=40, ε=8 |
| --- | ---: | ---: | ---: | ---: |
| Amministrazione | 61,2% | 0,4% | 100,0% | 5,2% |
| Commerciale | 61,6% | 0,2% | 100,0% | 4,4% |

Aggiungere documenti non pertinenti riduce il gap fra le frequenze e peggiora
il rilascio dell'importo richiesto. Il risultato non implica che lo scheduler
possa leggere il gap privato per scegliere N gratuitamente: l'attuale scelta
usa soltanto segnali pubblici, come richiesto dall'analisi di privacy.

Nel controllo sul netto, con N=40 il filtro rilascia almeno una parola nel
34,0% delle prove a ε=4 e nel 99,4% a ε=8. L'istogramma include `euro` 32 volte:
rilasciare parole frequenti non significa ottenere una risposta corretta o
completa. Non attribuiamo al cloud simulato un punteggio di qualità.

Queste sono frequenze osservate, non probabilità esatte: zero eventi su 500
prove non significa probabilità matematica zero. Le repliche usano seed
diagnostici su dati pubblici fittizi e non costituiscono una sessione DP
pubblicabile per un corpus riservato. Le quattro richieste della pipeline
usano invece un account comune: ε cumulativo 12,128915, delta 0,0005.

## Adattivo e N fisso: richieste realmente ripetute

Seconda prova: query Tecnologia, epsilon di calibrazione 4, SLA configurato
30 secondi, tre richieste per variante in ordine mescolato. Queste sono nuove
inferenze reali, non il riuso delle bozze: 213 inferenze aggiuntive e 373 totali
fra i due esperimenti. Modello precaricato, cloud simulato.

| Variante | N scelto | Tempo medio | Min–max | Richieste con rilascio |
| --- | ---: | ---: | ---: | ---: |
| Adattivo | 6 | 1,995 s | 1,992–1,997 s | 0/3 |
| Fisso 5 | 5 | 1,672 s | 1,665–1,679 s | 0/3 |
| Fisso 20 | 20 | 6,687 s | 6,653–6,722 s | 1/3 |
| Fisso 40 | 40 | 13,416 s | 13,366–13,465 s | 3/3 |

Nessuna richiesta ha superato 30 secondi in questa configurazione offline.
Tre ripetizioni sono una prima descrizione, non una stima robusta della
frequenza di rilascio né una prova di superiorità dell'adattivo. L'account
dell'intero confronto riporta ε=31,359738 e delta=0,0013, senza arresti per
budget. Le sessioni diagnostiche restano distinte e il corpus è sintetico.

Lo scheduler è conservativo: assume prompt da 1000 token e 30 token di output,
mentre nella prima prova le medie misurate sono circa 386,2 e 5,4. Con i
throughput configurati stima quindi tempi molto superiori a quelli osservati.
Questa è una ragione per progettare una calibrazione su workload pubblici
rappresentativi, non per adattare N alle lunghezze private del singolo corpus.

È stato verificato anche lo SLA predefinito di 1,5 secondi: fallback N=0,
nessuna inferenza aggiuntiva e consumo epsilon zero.

## Ripetere e ispezionare

La [guida](README.md) contiene i comandi. I report dettagliati della prova sono
in `poc/reports/azienda_demo_filter.json` e
`poc/reports/azienda_demo_scheduler.json`, locali e ignorati da Git. Questo
riepilogo e i documenti fittizi sono versionati. Le bozze nel primo report
permettono di verificare direttamente gli errori di estrazione.

Verifica software: 69 test superati, Ruff pulito. Sono inclusi controlli sulla
coerenza della fixture, sul retrieval per reparto, sulla preservazione di
modifiche manuali, sulla corrispondenza degli importi e sui trial del filtro.
