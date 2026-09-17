# Test preliminari con pipeline completa e provider reale

Esecuzioni del 16 settembre 2026, macOS ARM64, Qwen2.5 0.5B Instruct Q4_K_M,
calibrazione automatica attiva, provider cloud reale OpenAI-compatible.
Calibrazione misurata: prefill ~1900-2000 tok/s, generation ~480-490 tok/s
(velocità default configurate erano 250 e 50 tok/s).

I quattro casi seguenti sono singole esecuzioni, non medie su più prove.
Servono a verificare che il flusso end-to-end funzioni con il provider reale
e a identificare i parametri utili per una campagna sperimentale sistematica.

## Caso 1: Super Bowl 50 con budget privacy limitato

```
Dataset: SQuAD 1.1 (100 contesti pubblici)
Query: Who won Super Bowl 50?
Epsilon=1, delta=1e-4, SLA=60000 ms
```

| Misura | Valore |
|---|---:|
| N pianificato | 40 |
| Sigma | 8.71 |
| k_hat (FindBestK) | 6 |
| PTR superato | no |
| Keyword rilasciate | 0 |
| Calibrazione | 602 ms |
| Request | 17009 ms |
| Cloud | 4928 ms |
| SLA violato | no |

Il rumore gaussiano con sigma=8.71 rende il test PTR quasi impossibile da
superare: `P(PTR | gap=3) = 0.012%`. Il cloud ha risposto correttamente
usando la propria conoscenza generale, senza input dai documenti locali.

Report completo: `poc/report_real.json`

## Caso 2: Super Bowl 50 con budget privacy più ampio

```
Dataset: SQuAD 1.1
Query: Who won Super Bowl 50?
Epsilon=8, delta=0.01, SLA=60000 ms
```

| Misura | Valore |
|---|---:|
| N pianificato | 40 |
| Sigma | 0.94 |
| k_hat (FindBestK) | 6 |
| PTR superato | sì |
| Keyword rilasciate | bowl, england, new, patriots, super, won |
| Calibrazione | 590 ms |
| Request | 20429 ms |
| Cloud | 8312 ms |
| SLA violato | no |

Con sigma ridotta da 8.71 a 0.94, il PTR passa e 6 keyword vengono rilasciate.
Il cloud ha ricevuto le keyword e ha prodotto una risposta in cui nota
un'incongruenza: le keyword suggeriscono "New England Patriots won", ma la
risposta corretta del Super Bowl 50 è Denver Broncos. Il cloud ha scelto di
rispondere con il fatto storico corretto aggiungendo una nota sul disaccordo
con le keyword ricevute.

Questo comportamento è coerente con il design del filtro: DP-KSA rilascia un
sottoinsieme rumoroso dei token più frequenti nelle bozze locali, non la
risposta corretta. La privacy è preservata, ma l'utilità della risposta può
variare a seconda del caso.

Report completo: `poc/report_real_e8.json`

## Caso 3: Procedura E42 (informazione condivisa)

```
Corpus: 95 ticket sintetici (documenti/)
Query: Come si risolve l'errore E42 dopo aggiornamento di FerroSync?
       Riporta i passaggi della procedura generale in ordine.
Epsilon=8, delta=0.01, SLA=60000 ms
```

| Misura | Valore |
|---|---:|
| N pianificato | 40 |
| Sigma | 0.94 |
| k_hat (FindBestK) | 9 |
| PTR superato | sì |
| Keyword rilasciate | arrestare, cache, cancellare, ferrosync, locale, riavviare, ricorrere, servizio, tecnico |
| Calibrazione | 595 ms |
| Request | 33365 ms |
| Cloud | 9246 ms |
| SLA violato | no |

I tre passaggi attesi (arrestare, cancellare cache, riavviare) sono presenti
in molte bozze locali. Il PTR passa e il cloud ricostruisce la procedura
completa, più una nota sul ricorso al tecnico.

Risposta cloud ricevuta: arrestare FerroSync, cancellare la cache,
riavviare FerroSync, ricorrere al tecnico se il problema persiste.
Coerente con l'`expected_answer` del `cases.json`:
"Arrestare FerroSync, cancellare la cache, riavviare FerroSync."

Report completo: `poc/report_ticket_e42.json`

## Caso 4: Codice privato (informazione unica)

```
Corpus: 95 ticket sintetici (stesso corpus del caso 3)
Query: Qual è il codice privato della pratica nel ticket per errore E42
       dopo aggiornamento di FerroSync? Riporta soltanto il codice.
Epsilon=8, delta=0.01, SLA=60000 ms
```

| Misura | Valore |
|---|---:|
| N pianificato | 40 |
| Sigma | 0.94 |
| k_hat (FindBestK) | 6 |
| PTR superato | no |
| Keyword rilasciate | 0 |
| Calibrazione | 619 ms |
| Request | 23893 ms |
| Cloud | 10090 ms |
| SLA violato | no |

Il codice privato della pratica esiste in un solo ticket. Con 40 inferenze
su 95 documenti, compare in poche bozze. Il gap fra conteggi è piccolo,
il rumore gaussiano lo sovrasta, PTR fallisce. Il cloud riceve solo la
query senza keyword e risponde esplicitamente di non avere informazioni
su FerroSync, senza inventare un codice.

Questo è il comportamento desiderato quando il filtro non rilascia: il
provider non ha accesso ai documenti e dichiara il proprio limite invece
di rispondere con un codice inventato.

Report completo: `poc/report_ticket_codice.json`

## Osservazioni trasversali

**Calibrazione.** I throughput misurati (~1950 tok/s prefill, ~480 tok/s
generation) sono circa 8-10 volte superiori ai default configurati
(250 e 50 tok/s). Senza la calibrazione, con i default e uno SLA di 60 s,
lo scheduler pianifica comunque N=40 perché il budget temporale è ampio.
La calibrazione diventa decisiva quando lo SLA è stretto (es. 1500 ms),
dove i default portano in zero-shot mentre le velocità reali consentono
un N maggiore.

**Budget epsilon e rilascio.** Con epsilon=1 e delta=1e-4, sigma è troppo
alta per rilasci frequenti. Con epsilon=8 e delta=0.01, sigma scende
sufficientemente da far passare il PTR quando il contenuto è condiviso tra
molte bozze. I valori vanno calibrati sulla campagna sperimentale, non
fissati a priori.

**Comportamento del cloud senza keyword.** In entrambi i casi di PTR
fallito (Super Bowl epsilon=1, codice privato), il provider ha risposto
senza input dai documenti. Per Super Bowl ha usato conoscenza generale
e ha risposto correttamente; per il codice privato ha dichiarato di non
sapere. Il filtro non controlla quale dei due comportamenti il cloud
adotti: dipende dal modello remoto e dalla query.

**Utilità della risposta rilasciata.** Nel caso 2, le keyword rilasciate
contengono "patriots" e "new england", che sono token frequenti nelle bozze
SQuAD ma non la risposta corretta a "Who won Super Bowl 50?" (Denver
Broncos). Il cloud ha notato il disaccordo. Questo evidenzia che il filtro
rilascia token frequenti, non token corretti: la pertinenza al quesito
va verificata sperimentalmente caso per caso.

**Limiti di queste esecuzioni.** Sono singole run, non medie. La
variabilità del provider e del modello locale non è caratterizzata.
I casi ticket sono su un corpus sintetico generato dal PoC stesso; non
rappresentano ticket linguistici reali.
