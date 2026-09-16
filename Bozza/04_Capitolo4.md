# Capitolo 4: Risultati sperimentali e discussione

## 4.1 Cosa è stato misurato

I risultati riportati derivano da tre prove locali eseguite sul nodo di
sviluppo, con il modello Qwen 2.5 0.5B Instruct Q4_K_M via llama.cpp e
cloud simulato in modalità offline. Le prove sono:

- una campagna di 160 inferenze reali sul corpus salariale fittizio
  (`poc/docs/azienda_demo/RISULTATI.md`), seguita da 24 000 repliche del
  solo filtro sulle bozze già ottenute;
- 160 inferenze reali sul corpus di ticket sintetici
  (`poc/docs/ticket_demo/RISULTATI.md`), con prove condizionali del filtro
  su bozze congelate;
- un confronto adattivo/fisso sul corpus salariale con 213 inferenze reali
  e modello precaricato, organizzato in ordine casuale e tre ripetizioni
  per variante.

I numeri sono specifici della macchina, del modello e delle date di
esecuzione. Sono una base per discutere il comportamento del prototipo, non
una stima generale di prestazioni.

## 4.2 Comportamento del prototipo attuale

Nel confronto sul corpus salariale con SLA di 30 secondi e calibrazione
ε = 4 per richiesta, i risultati sono:

| Variante | N scelto | Tempo medio | Richieste con rilascio |
| --- | ---: | ---: | ---: |
| Adattivo (N_MIN = 5) | 6 | 2,0 s | 0/3 |
| Fisso 5 | 5 | 1,7 s | 0/3 |
| Fisso 20 | 20 | 6,7 s | 1/3 |
| Fisso 40 | 40 | 13,4 s | 3/3 |

Tutte le varianti restano sotto l'SLA. Nessuna delle tre richieste
adattive è riuscita a rilasciare keyword, mentre `N = 40` fisso riesce
nelle tre. A ε = 1 il rilascio è ancora più raro: con 40 bozze concordi
sull'importo corretto, la probabilità empirica di recuperarlo è circa
5,8%.

Il prototipo attuale è quindi **troppo conservativo**: la stima interna
dello scheduler usa prompt da 1000 token e output da 30, mentre le
misure reali mostrano prompt medi di circa 386 token e output di circa
5,4. La sovrastima è di circa quattro-cinque volte. Di conseguenza lo
scheduler rinuncia a lavoro locale che potrebbe essere svolto entro l'SLA
e il filtro non riceve abbastanza segnale per rilasciare.

Questa osservazione è il punto di partenza delle ipotesi sperimentali
della tesi. La narrativa della versione precedente del capitolo, che
presentava l'adattivo come collocato "nel mezzo" tra fissi bassi e alti,
non era supportata dai dati: nel confronto misurato l'adattivo si comporta
come la baseline minima, non come un buon compromesso.

## 4.3 Effetto di N e di ε sul rilascio

Le 24 000 repliche del filtro sulle bozze reali del corpus salariale
mostrano l'andamento atteso della probabilità di rilascio in funzione di
N e di ε, limitatamente al caso "40 documenti pertinenti e concordi":

| N | ε = 1 | ε = 4 | ε = 8 |
| ---: | ---: | ---: | ---: |
| 5 | 0,0% | 0,2% | 0,6% |
| 10 | 0,0% | 3,2% | 34,2% |
| 20 | 0,0% | 59,8% | 100,0% |
| 40 | 5,8% | 100,0% | 100,0% |

A ε = 1 il filtro resta prudente anche con tutte le bozze corrette e
concordi. Aumentare ε facilita il rilascio ma indebolisce la garanzia;
aumentare N migliora la situazione solo se i documenti sono pertinenti
alla query. Quando i documenti pertinenti sono 20 su 40, aggiungere i
restanti 20 abbassa la probabilità di recupero dell'importo corretto:
per Amministrazione e Commerciale a ε = 4, `N = 20` raggiunge circa il
61% mentre `N = 40` scende sotto l'1%. L'effetto è coerente con la
natura del test PTR: aggiungere documenti non pertinenti riduce il
distacco fra le frequenze dei termini rilevanti.

Questi numeri non implicano che lo scheduler possa scegliere N in base
al gap privato: la scelta di N resta basata su segnali pubblici, come
richiesto dall'analisi di privacy.

## 4.4 Caso dei ticket sintetici

Il caso ticket è stato scelto per valutare il prototipo in un contesto
applicativo realistico. Le bozze reali mostrano che il piccolo modello
0.5B non è sufficiente come estrattore: spesso tronca la procedura,
aggiunge raccomandazioni generiche ("rivolgersi al tecnico"), oppure
riutilizza termini di un ticket diverso. In una prova con `N = 40`,
epsilon nominale 4 e account condiviso fra quattro richieste:

- sulla procedura E42 sono state rilasciate nove keyword coerenti con i
  passaggi attesi. La sintesi locale successiva, che riceveva solo
  domanda e keyword, ha menzionato un solo passaggio e ha prodotto una
  frase troncata: la procedura finale **non è ricostruibile** con il
  solo prompt dell'estrattore;
- su un codice unico, previsto in un solo ticket, il rilascio è stato
  vuoto nelle quattro richieste e la sintesi si è correttamente
  astenuta;
- su un identificativo interno condiviso fra molti ticket E42
  (`clusterinternoaurora`), il filtro ha rilasciato il termine perché
  la sua frequenza era molto alta. La sintesi locale lo ha citato
  accanto a un numero inventato (`E42, 1144000000`);
- sull'errore E99, assente dal corpus, nessuna delle 40 bozze si è
  astenuta. Il modello ha riutilizzato procedure di E42 o ha inventato
  risposte; in alcuni esperimenti il filtro ha rilasciato keyword e la
  sintesi ha prodotto un'affermazione non fondata sui documenti. DP non
  certifica pertinenza o correttezza: il consenso su una risposta
  sbagliata può passare il filtro.

Sulle 500 prove condizionali del filtro per identificativo unico, si è
osservato **un singolo rilascio** (1/500). Una simile frequenza non
consente di affermare che dettagli individuali non escano mai; al
contrario, il fallimento del test PTR ha una probabilità non nulla e
l'osservazione singola non ne stima bene il valore. Anche le celle con
zero eventi non dimostrano probabilità nulla. Il limite dichiarato di
`docs/PRIVACY_ACCOUNTING.md` su `g ≤ 2` resta valido.

La qualità del cloud reale non è stata valutata in queste prove: il
provider era simulato e il modello di sintesi adottato era lo stesso 0.5B
con il prompt dell'estrattore. Una valutazione della sintesi cloud resta
un'operazione aperta.

## 4.5 Margine di miglioramento

I risultati del §4.2 suggeriscono due interventi, descritti nel
documento di concezione sperimentale (`poc/docs/CONCEZIONE_SPERIMENTALE.md`):

1. **Calibrazione delle stime di tempo** con misure locali a inizio
   sessione. La sovrastima di quattro-cinque volte indica che la
   configurazione di default è lontana dal comportamento osservato. Una
   calibrazione su prompt pubblici a lunghezze rappresentative dovrebbe
   permettere allo scheduler di scegliere N più alto a parità di SLA,
   migliorando il segnale a disposizione del filtro senza modificare la
   garanzia DP.
2. **Soglia di sforamento accettabile** definita da una formula basata
   sulla misura cloud di sessione, con sweep sul coefficiente `k`. La
   tesi non afferma che una formula chiusa risolva il problema: lo
   sweep su `k ∈ {0, 0.1, 0.25, 0.5}` produce i primi dati sperimentali
   per discuterla, in capitolo 4 stesso.

Questi interventi sono previsti dalla metodologia sperimentale della
tesi e vengono descritti come tali finché non saranno implementati e
verificati.

## 4.6 Limiti dell'interpretazione

I risultati discussi vanno letti con alcune cautele, già documentate in
`poc/ARCHITECTURE.md` e in `poc/docs/PRIVACY_ACCOUNTING.md`:

- le frequenze di rilascio sono empiriche. Zero eventi su 500 prove non
  equivale a probabilità nulla; una singola frequenza osservata non è
  una stima robusta del fallimento del test PTR;
- la protezione del filtro è riferita al singolo documento originale.
  Non si estende automaticamente al cliente o ad altre unità di
  aggregazione; il caso ticket ha mostrato che informazioni condivise
  da molti documenti possono essere rilasciate;
- i tempi osservati dipendono dalla macchina, dal sistema operativo e
  dalla versione del modello. Le misure assolute non sono generalizzabili
  ad altri contesti; le tendenze relative sono indicative ma non
  costituiscono una prova di superiorità di una variante;
- il prefill riportato è una stima euristica, non una misura del tempo
  al primo token; i byte di testo non misurano il traffico di rete
  effettivo;
- il cloud simulato permette di verificare il flusso della pipeline ma
  non fornisce una misura della qualità di un provider reale;
- i trace, la console e i report sperimentali non sono coperti dalla
  garanzia del rilascio DP. La modalità `capture_sensitive` di Langfuse
  contiene contenuti non privatizzati e va usata solo con dati pubblici
  o autorizzati, su un endpoint fidato.

Il confronto a tre ripetizioni per variante è sufficiente per una prima
osservazione dei tempi ma non per affermazioni quantitative sulla
frequenza di rilascio o sulla superiorità di una variante. Nuove prove
andranno descritte solo dopo la loro esecuzione.
