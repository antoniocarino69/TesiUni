# Report di Audit Formale e Architetturale: DP-RAG Proof-of-Concept

**Data dell'audit:** 9 settembre 2026  
**Versione target PoC:** Revisione corrente (`poc/`)  
**Autori dell'audit:** Team di Revisione Tecnica (Worker M1, M2, M3, M4)  
**Ambito di verifica:** Meccanismo formale DP-KSA (`core/privacy.py`), isolamento architetturale e confini fiduciari (`core/documents.py`, `core/scheduler.py`, `core/pipeline.py`, `core/cloud.py`, `core/telemetry.py`), qualità del codice, linter e suite di test automatizzati (`poc/tests/`).  
**Riferimenti scientifici e normativi:**
- Tang et al., *Differentially Private Retrieval-Augmented Generation*, PDF di ricerca provvisorio YYYY(X) / [arXiv:2602.14374v1](https://arxiv.org/html/2602.14374v1) (Algoritmi 1, 2, 3 e Appendice A).
- Specifiche di progetto: `poc/ARCHITECTURE.md`, `poc/docs/PRIVACY_ACCOUNTING.md`, `poc/docs/CONFIGURATION.md`.
- Regolamento di qualità: `AGENTS.md`.

---

## 1. Sintesi Esecutiva

Il presente audit fornisce la valutazione sistematica e formale del Proof-of-Concept (PoC) **DP-RAG**, un'architettura che integra modelli neurali locali operanti su documenti riservati con modelli di sintesi in cloud, applicando il meccanismo **DP-KSA** (*Differentially Private Keyword Selection Algorithm*) per garantire la riservatezza differenziale a livello di documento.

L'indagine ha combinato tre direttrici di verifica indipendenti:
1. **Verifica formale e matematica (R1):** analisi degli algoritmi differenzialmente privati in `core/privacy.py` a fronte dei teoremi e delle definizioni dimostrati da Tang et al. (Algoritmi 1–3 e Appendice A).
2. **Verifica dei confini architetturali e dei canali di fuga (R2):** controllo dell'isolamento dei dati privati nei moduli `core/documents.py`, `core/scheduler.py`, `core/pipeline.py`, `core/cloud.py` e `core/telemetry.py`.
3. **Audit empirico e qualità del software (R3):** esecuzione completa della suite di test unitari e d'integrazione, misurazione della copertura del codice con `coverage` ed esecuzione statica delle regole di stile e conformità con `ruff`.

### 1.1 Riepilogo Statistico dei Controlli

| Categoria di Controllo | Totale Controlli | Conforme | Rischio | Suggerimento | Non Conforme |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **R1 — Aderenza Formale DP (Algoritmi 1-3, Appendice A)** | 15 | 13 | 1 | 1 | 0 |
| **R2 — Architettura, Isolamento e Confini Fiduciari** | 14 | 13 | 0 | 1 | 0 |
| **R3 — Verifica Sperimentale, Invarianti e Qualità Codice** | 9 | 7 | 0 | 2 | 0 |
| **Totale Complessivo** | **38** | **33** | **1** | **4** | **0** |

### 1.2 Sintesi della Suite di Test e Metriche di Qualità

- **Esecuzione Test (`pytest -v`):** **77 test su 77 superati con successo** in 0.74 secondi (0 fallimenti, 0 errori, 0 skip).
- **Analisi Statica e Linter (`ruff check .`):** **0 violazioni, 0 avvisi** su profilo Python 3.10 (lunghezza riga $\le 100$ caratteri).
- **Copertura del Codice (`coverage` su `core/scheduler.py`):** **97%** (116 righe coperte su 119, ampiamente al di sopra della soglia obbligatoria del 90%).
- **Validazione Statistica del Rumore:** 10.000 campioni Gumbel analizzati con convergenza empirica a $\text{scala} \approx 4.0$ per $\epsilon=1.0$; 6.000 simulazioni Monte Carlo sul Meccanismo Esponenziale con convergenza alla distribuzione teorica $\Pr[k] \propto \exp(\epsilon \cdot q / 4)$ entro $\pm 0.02$.

### 1.3 Verdetto Complessivo

L'implementazione del PoC DP-RAG è **rigorosa, autentica e conforme ai fondamenti scientifici dichiarati**. In particolare, il PoC adotta una correzione conservativa essenziale rispetto allo pseudocodice del paper, impostando la scala del rumore Gumbel a $4/\epsilon$ anziché $2/\epsilon$, prevenendo un raddoppio involontario del consumo del budget privacy. Non sono state rilevate fughe di dati privati verso il provider cloud, né dipendenze indebite dello scheduler dalle dimensioni dei documenti privati.

---

## 2. Matrice di Conformità Completa

La matrice seguente consolida tutti i 38 punti di controllo individuati nei requisiti R1, R2 e R3.

| Requisito / Invariante | Stato | File e Riga | Descrizione / Evidenza nel codice | Azione raccomandata |
| :--- | :---: | :--- | :--- | :--- |
| **R1.01 — FindBestK: Dominio pubblico predefinito** | **Conforme** | `core/privacy.py:51-52`<br>`core/privacy.py:413-417` | `candidati = list(range(r_min_k, r_max_k + 1))` con `DEFAULT_R_MIN_K = 1` e `DEFAULT_R_MAX_K = 10`. Il dominio dei candidati è statico, pubblico e indipendente dal numero di parole distinte estratte. | Mantenere invariato. |
| **R1.02 — FindBestK: Sensibilità globale del gap $\Delta = 2$** | **Conforme** | `core/privacy.py:67`<br>`core/privacy.py:395` | `GLOBAL_GAP_SENSITIVITY = 2.0`. Modificare un documento altera al più una risposta; nell'istogramma dei termini unici un token può guadagnare $+1$ e un altro perdere $-1$, portando la sensibilità di $H(k) - H(k+1)$ a 2. | Mantenere la costante e la verifica associata. |
| **R1.03 — FindBestK: Scala del rumore Gumbel $4/\epsilon$** | **Conforme** | `core/privacy.py:378-400` | `scale = 2.0 * GLOBAL_GAP_SENSITIVITY / epsilon` ($= 4/\epsilon$). Allineato alla Definizione A.7 del paper ($\exp(\frac{\epsilon q}{2\Delta})$) che con $\Delta=2$ richiede scala $4/\epsilon$. Centratura via costante di Eulero-Mascheroni. | Mantenere la documentazione in `PRIVACY_ACCOUNTING.md`. |
| **R1.04 — FindBestK: Conteggi zero impliciti** | **Conforme** | `core/privacy.py:364-369` | `counts = counts[:limit + 1] + [0] * max(0, limit + 1 - len(counts))`. Gli indici del dominio pubblico non osservati ricevono conteggio zero e gap 0.0, prevenendo leakage sulla dimensione dell'istogramma. | Mantenere invariato. |
| **R1.05 — FindBestK: Gap dell'ultimo token osservato** | **Conforme** | `core/privacy.py:368-369` | Per $M$ token osservati, il gap all'indice $M$ è $c_M - 0 = c_M$. Cattura correttamente la variazione rispetto al fondo scala dei termini non comparsi. | Mantenere invariato. |
| **R1.06 — TopKWithPTR: Test del gap rumoroso $\hat{d}_k > 2$** | **Conforme** | `core/privacy.py:506-509` | `noisy_gap = max(GLOBAL_GAP_SENSITIVITY, gap) + gaussian_noise - gaussian_threshold`. Soglia $2\sigma \cdot (-\Phi^{-1}(\delta))$ calcolata in modo numericamente stabile contro l'underflow su $\delta$ piccoli. | Mantenere invariato. |
| **R1.07 — TopKWithPTR: Ordinamento alfabetico token rilasciati** | **Conforme** | `core/privacy.py:512`<br>`core/cloud.py:105` | `released_tokens = tuple(sorted(token_ordinati[:k])) if passed else ()`. I token vengono riordinati in modo puramente alfabetico; nessun conteggio privato o rango relativo viene esposto. | Mantenere invariato; preservare la difesa in profondità in `cloud.py`. |
| **R1.08 — TopKWithPTR: Semantica del failure event e `strict_gap_guard`** | **Conforme** | `core/privacy.py:470`<br>`core/privacy.py:509-511` | `strict_gap_guard` è impostato a `False` di default. Se $d_k \le 2$, il test passa con probabilità analitica $\delta$, conformemente al Teorema A.10. Se fallisce, restituisce tupla vuota (zero-shot). | Mantenere disattivato di default; documentare il guard come opzione difensiva fuori standard. |
| **R1.09 — RDP: Bound Exponential Mechanism (Thm A.9)** | **Conforme** | `core/privacy.py:569-598` | Implementazione esatta del bound RDP per meccanismi $\epsilon$-DP riformulata con `_log_cosh` per prevenire overflow con ordini $\alpha$ elevati (es. $\alpha=1024$). | Mantenere l'ottimizzazione trigonometrica. |
| **R1.10 — RDP: Composizione lineare multi-query (Thm A.3)** | **Conforme** | `core/privacy.py:640-643`<br>`core/privacy.py:912-924` | Per $m$ invocazioni consecutive, i costi RDP si sommano algebricamente per ciascun ordine $\alpha$: $\epsilon_{\text{RDP}, m}(\alpha) = m \cdot \epsilon_{\text{EM}}(\alpha) + m \cdot \frac{\alpha}{2\sigma^2}$. | Mantenere invariato. |
| **R1.11 — RDP: Conversione in $(\epsilon, \delta)$-DP (Thm A.6)** | **Conforme** | `core/privacy.py:600-626` | Minimizzazione su ordini discreti di $\epsilon_{\text{RDP}}(\alpha) + \frac{\log(1/\delta_{\text{conversion}})}{\alpha - 1}$. Il $\delta$ totale esposto è $\delta_{\text{total}} = \delta_{\text{ptr}} + \delta_{\text{conversion}}$. | Suggerimento R1.15 per raffinare la griglia. |
| **R1.12 — Accounting: Blocco proattivo esaurimento budget** | **Conforme** | `core/privacy.py:903-939`<br>`core/privacy.py:959`<br>`core/pipeline.py:82` | `_account_for_next_invocation()` e `filter_.verifica_budget()` bloccano la richiesta con `DPBudgetExhaustedError` prima del retrieval locale, del caricamento del modello o del campionamento del rumore. | Mantenere invariato. |
| **R1.13 — Accounting: Invariante di conservazione in `EsitoDP`** | **Conforme** | `core/privacy.py:234-269`<br>`core/privacy.py:984-1015` | Viene costantemente verificata l'uguaglianza `budget_consumato_epsilon + epsilon_rimasto == epsilon_budget`. Tracciamento esplicito del consumo cumulativo. | Mantenere invariato. |
| **R1.14 — Account RDP: Persistenza in memoria volatile tra esecuzioni CLI** | **Rischio** | `core/privacy.py:887-940`<br>`core/pipeline.py:141` | L'account RDP risiede nella memoria dell'istanza Python. Esecuzioni CLI separate (`run_pipeline.py`) creano un nuovo filtro con `account_scope='single_request'`. | Documentare che la CLI ha ambito di sessione singola. Per deployment di produzione, usare uno statefile crittografico o un database per persistere l'account tra processi. |
| **R1.15 — RDP: Densità della griglia di ordini Rényi** | **Suggerimento** | `core/privacy.py:54-66` | La tupla `DEFAULT_RDP_ORDERS` campiona 11 ordini (da 2.0 a 1024.0). Sebbene sia un limite superiore matematicamente solido, una griglia più fitta (includendo ordini seminteri) potrebbe ridurre lievemente l'$\epsilon$ convertito. | Valutare l'arricchimento con ordini intermedi (es. 1.5, 2.5, 3.5, 4.0, etc.) in una futura versione. |
| **R2.01 — Unità Protetta: Singolo documento normalizzato** | **Conforme** | `core/documents.py:19-24`<br>`core/documents.py:48-57` | L'unità protetta è il documento identificato dall'hash crittografico SHA-256 del testo con spazi normalizzati (`content_id`). Copie identiche vengono deduplicate all'origine. | Mantenere invariato. |
| **R2.02 — Assenza di Statistiche Globali (No IDF di corpus)** | **Conforme** | `core/documents.py:104-111` | Il punteggio di rilevanza dell'estratto è calcolato come overlap lessicale tra i termini della query pubblica e il singolo frammento (`len(query_terms & set(...))`). Nessuna dipendenza dal resto del corpus. | Preservare il principio di scoring puramente locale; non introdurre IDF globale o BM25 con parametri cross-documento. |
| **R2.03 — Un Solo Estratto e Candidato per Documento** | **Conforme** | `core/documents.py:106-111` | Ciascun documento produce esattamente un candidato nell'ensemble (la finestra di 400 parole con il punteggio massimo, pareggi risolti deterministicamente con `-i`). I frammenti multipli non votano indipendentemente. | Mantenere invariato. |
| **R2.04 — Padding con Slot Pubblici Vuoti** | **Conforme** | `core/documents.py:113-116`<br>`core/pipeline.py:91-94` | Se il corpus ha meno di $N$ documenti, gli slot mancanti sono colmati con `RetrievedDocument('public-empty-i', '', '', 0, True)`, che generano bozze vuote senza duplicare documenti privati. | Mantenere invariato. |
| **R2.05 — Scheduler: Isolamento da Dati Privati** | **Conforme** | `core/pipeline.py:54-60`<br>`run_pipeline.py:101-107`<br>`core/scheduler.py:164-180` | Lo scheduler determina $N$ ricevendo `[prompt_token_budget] * candidates` (costanti pubbliche) prima del recupero dei documenti. Non consulta mai conteggi di parole o token reali dei testi privati. | Mantenere invariato. |
| **R2.06 — Scheduler: Pianificazione $N \in [5, 40]$ e Fallback Zero-Shot** | **Conforme** | `core/scheduler.py:27-28`<br>`core/scheduler.py:233-235` | Se lo SLA temporale stimato non consente almeno $N_{\min}=5$ generazioni locali, la decisione collassa a $N=0$ (zero-shot), escludendo l'accesso al corpus e l'uso del modello neurale. | Mantenere invariato. |
| **R2.07 — Scheduler: Trasparenza Baseline Fissa (`fixed_n`)** | **Conforme** | `core/scheduler.py:238-239`<br>`core/scheduler.py:258-268` | La modalità sperimentale `fixed_n` impone $N$ anche se eccede lo SLA temporale stimato, segnalando esplicitamente `sla_fattibile=False` e motivando la violazione. | Mantenere la chiara separazione tra modalità adattiva e baseline fissa. |
| **R2.08 — Scheduler: Semantica Trasparente di `ptr_pass_rate_attesa`** | **Conforme** | `core/scheduler.py:151-163`<br>`core/scheduler.py:276-277` | Il valore restituito è la probabilità teorica condizionata $P(\text{pass} \mid \text{gap}=3)$ dell'Algoritmo 2 per un salto di riferimento pari a 3, non una previsione del rilascio sul corpus privato. | Mantenere la documentazione esplicita per evitare fraintendimenti accademici. |
| **R2.09 — Scheduler: Blocco Proattivo del Budget** | **Conforme** | `core/scheduler.py:201-204`<br>`core/pipeline.py:82` | Se il budget $\epsilon \le 0$ o non consente una scala $\sigma$ valida, viene sollevata `PrivacyBudgetExhaustedError` a monte del caricamento del modello o della lettura dei documenti. | Mantenere invariato. |
| **R2.10 — Confine Cloud: Solo Query e Keyword Alfabetiche** | **Conforme** | `core/cloud.py:105-112`<br>`core/cloud.py:152-160` | Il payload trasmesso all'endpoint OpenAI-compatibile contiene solo la query pubblica e le keyword alfabetiche (`", ".join(sorted(set(parole_chiave)))`). Nessun testo di contesto o bozza viene trasmesso. | Mantenere invariato. |
| **R2.11 — Confine Cloud: Confinamento Locale delle Metriche di Risparmio** | **Conforme** | `core/cloud.py:115-120`<br>`core/pipeline.py:114` | I testi grezzi dei contesti sono utilizzati esclusivamente a livello locale per calcolare la percentuale di caratteri risparmiati rispetto a un RAG standard. | Mantenere locale. |
| **R2.12 — Telemetria: Redazione Predefinita dei Dati Sensibili** | **Conforme** | `core/telemetry.py:28`<br>`core/telemetry.py:138-142`<br>`core/telemetry.py:227-236` | `DEFAULT_CAPTURE_SENSITIVE = False`. Nella configurazione predefinita, le tracce Langfuse omettono il testo della query, le bozze, l'istogramma privato dei termini e i gap non privatizzati. | Mantenere redatto per default. |
| **R2.13 — Telemetria: Esclusione Esplicita della Garanzia DP** | **Conforme** | `core/telemetry.py:135-137` | Ciascuna traccia esportata riporta nei metadati `"telemetry_dp_guarantee": False`. Il modulo documenta chiaramente che la telemetria è diagnostica sperimentale e non un rilascio differenzialmente protetto. | Mantenere nei metadati di traccia. |
| **R2.14 — Test di Integrazione: Budget uniforme vs lunghezze stimate** | **Suggerimento** | `tests/test_pipeline_integration.py:36` | Il test passa `[doc.token_stimati for doc in candidates]` all'AdaptiveScheduler. Pur essendo valido come test di flessibilità dell'API, si discosta dal pattern uniforme di produzione. | Allineare il test al modello di produzione passando un budget omogeneo `[config.prompt_token_budget] * len(candidates)`. |
| **R3.01 — Esecuzione Suite di Test Pytest** | **Conforme** | `poc/tests/` | Esecuzione completa con 77 test superati su 77 in 0.74s, 0 fallimenti, 0 errori, 0 skip. | Nessuna azione necessaria. |
| **R3.02 — Controllo di Stile e Linter con Ruff** | **Conforme** | `poc/pyproject.toml` | Esecuzione completa di `ruff check .` con zero errori e zero warning, nel rispetto delle regole PEP 8 e limiti a 100 caratteri. | Nessuna azione necessaria. |
| **R3.03 — Copertura del Codice su Scheduler** | **Conforme** | `core/scheduler.py`<br>`tests/test_scheduler.py` | Copertura misurata al 97% (116 righe su 119), superiore alla soglia vincolante del 90%. | Suggerimento R3.08 per coprire le guardie difensive rimanenti. |
| **R3.04 — Validazione Statistica Rumore Gumbel ($N=10.000$)** | **Conforme** | `tests/test_privacy.py:27-37` | Verifica statistica della scala del rumore Gumbel $\approx 4/\epsilon$ su 10.000 campioni; deviazione standard empirica entro $0.16$ dal valore atteso $4.0$. | Mantenere invariato. |
| **R3.05 — Validazione Statistica Meccanismo Esponenziale** | **Conforme** | `tests/test_privacy.py:226-232` | 6.000 simulazioni empiriche di `find_best_k` con utilità 8 e 2 confermano convergenza alla distribuzione teorica $\frac{1}{1 + e^{-6/4}}$ con scostamento $< 0.02$. | Mantenere invariato. |
| **R3.06 — Riproducibilità e Campionamento Dataset** | **Conforme** | `tests/test_dataset.py:8-16` | Su 1.000 iterazioni non seedate, campioni da 5 elementi collidono con frequenza $< 0.01$ ($p > 0.99$). Con seed fisso, il campionamento è perfettamente deterministico. | Mantenere invariato. |
| **R3.07 — Scaricamento Atomico e Integrità Modello GGUF** | **Conforme** | `tests/test_engine.py:34-66` | In caso di stream interrotto o discrepanza con `Content-Length`, il file parziale `.part` viene rimosso immediatamente e viene sollevata `ModelDownloadError`. | Mantenere invariato. |
| **R3.08 — Copertura 100% Rami Difensivi dello Scheduler** | **Suggerimento** | `core/scheduler.py:119, 141, 145` | Le tre linee non coperte dal test di coverage riguardano verifiche difensive per input negativi o non interi su `max_tokens` e `token_per_documento`. | Aggiungere un test parametrico in `tests/test_scheduler.py` per portare la copertura al 100%. |
| **R3.09 — Test Monte Carlo su Failure Branch PTR ($d_k \le 2$)** | **Suggerimento** | `tests/test_privacy.py:78-86` | La probabilità analitica di rilascio $\delta$ per gap instabili è verificata tramite la funzione chiusa cumulativa gaussiana. | Aggiungere un test Monte Carlo con $10.000$ invocazioni dirette di `top_k_with_ptr` su gap instabile per validare empiricamente la frequenza empirica $\approx \delta$. |

---

## 3. Approfondimenti Tecnici Dettagliati (Deep-Dives)

### 3.1 Deep-Dive 1: FindBestK e Meccanismo Esponenziale

#### 3.1.1 Analisi Matematica: Algoritmo 3 vs Definizione A.7
Nel paper di Tang et al., l'Algoritmo 3 (*FindBestK*) presenta il seguente pseudocodice:
$$\text{Return } \operatorname{argmax}_{k \in \{1, \dots, N-1\}} \left\{ d_k + r(k) + \text{Gumbel}(2/\epsilon) \right\}$$
Tuttavia, nella **Definizione A.7** (*Exponential Mechanism*, McSherry & Talwar 2007) a pagina 14 del medesimo articolo, gli autori definiscono formalmente il meccanismo esponenziale per una funzione di utilità $q(D, o)$:
$$\Pr[M(D) = o] \propto \exp\left( \frac{\epsilon \cdot q(D, o)}{2 \Delta(q)} \right)$$
dove $\Delta(q) = \max_{o} \max_{D \sim D'} |q(D, o) - q(D', o)|$ è la sensibilità globale della funzione di utilità.

Per il noto teorema di equivalenza tra il meccanismo esponenziale e il campionamento Gumbel-max (Dwork & Roth 2014, richiamato nella dimostrazione del Teorema A.11):
$$\operatorname{argmax}_o \left\{ q(D, o) + \text{Gumbel}(0, \beta) \right\} \sim \Pr[o] \propto \exp\left( \frac{q(D, o)}{\beta} \right)$$
Uguagliando gli esponenti tra la forma Gumbel e la Definizione A.7:
$$\frac{1}{\beta} = \frac{\epsilon}{2 \Delta(q)} \implies \beta = \frac{2 \Delta(q)}{\epsilon}$$

#### 3.1.2 Sensibilità Globale del Gap: $\Delta(d_k) = 2$
Sia $D \sim D'$ una coppia di dataset adiacenti che differiscono per un documento ($|D \Delta D'| \le 1$). Nell'architettura DP-KSA, ciascun documento genera una sola risposta sintetica, e da ciascuna risposta viene estratto l'insieme dei token unici (ciascuna risposta vota per una parola al massimo una volta).

Siano $c_1 \ge c_2 \ge \dots$ i conteggi ordinati delle frequenze dei token. Tang et al. dimostrano in Appendice A.2 (dimostrazione del Teorema A.11) che tra dataset adiacenti, al variare di una singola risposta:
1. Un token può comparire in $D$ ma non in $D'$: il suo conteggio scende di 1.
2. Un altro token può comparire in $D'$ ma non in $D$: il suo conteggio sale di 1.
3. Nell'istogramma dei conteggi ordinati $H(k)$, la funzione decrescente subisce al più uno scostamento unitario: $|H_D(k) - H_{D'}(k)| \le 1$ per ogni $k$.

Considerando la funzione di utilità del gap $d_k = H(k) - H(k+1)$:
$$\Delta(d_k) = \max_{D \sim D'} |(H_D(k) - H_D(k+1)) - (H_{D'}(k) - H_{D'}(k+1))|$$
Nel caso peggiore:
- $H(k)$ aumenta di $+1$ mentre $H(k+1)$ rimane invariato o diminuisce di $-1$, determinando una variazione massima:
$$\Delta(d_k) = 1 - (-1) = 2$$

#### 3.1.3 Dimostrazione della Scala $4/\epsilon$ rispetto al Refuso $2/\epsilon$
Sostituendo $\Delta(d_k) = 2$ nell'equazione della scala Gumbel $\beta = \frac{2 \Delta(q)}{\epsilon}$:
$$\beta = \frac{2 \times 2}{\epsilon} = \frac{4}{\epsilon}$$
Se l'implementazione adottasse ciecamente la scala $\beta = 2/\epsilon$ indicata nello pseudocodice di Algoritmo 3, il meccanismo campionerebbe secondo una distribuzione:
$$\exp\left( \frac{d_k}{2/\epsilon} \right) = \exp\left( \frac{\epsilon \cdot d_k}{2} \right) = \exp\left( \frac{2\epsilon \cdot d_k}{2 \times 2} \right) = \exp\left( \frac{2\epsilon \cdot d_k}{2 \Delta} \right)$$
Tale scelta garantirebbe matematicamente soltanto una protezione di $(2\epsilon)$-DP, consumando nei fatti **il doppio del budget di privacy dichiarato**.

L'implementazione in `core/privacy.py` (righe 378-400) e la documentazione in `poc/docs/PRIVACY_ACCOUNTING.md` adottano rigorosamente:
```python
GLOBAL_GAP_SENSITIVITY = 2.0
scale = 2.0 * GLOBAL_GAP_SENSITIVITY / epsilon  # scale = 4.0 / epsilon
samples = _rng_or_default(rng).gumbel(loc=0.0, scale=scale, size=size)
centered = samples - EULER_MASCHERONI * scale
```
La sottrazione del valore atteso della variabile Gumbel standard ($\gamma \cdot \text{scale}$, con $\gamma \approx 0.57721566$) centra il rumore a media zero senza influenzare l'operazione di argmax. Questa correzione conservativa garantisce che il consumo di budget certificato corrisponda all'$\epsilon$ nominale.

#### 3.1.4 Gestione dei Conteggi Zero Impliciti e Gap dell'Ultimo Token
Se l'insieme delle risposte private contiene meno token distinti rispetto a $r_{\max} = 10$, troncare l'istogramma o consentire che la dimensione di $H$ vari costituirebbe un canale di fuga differenziale sulla dimensione del lessico privato.

In `core/privacy.py:364-369` (`calcola_gap`):
```python
counts = sorted((c for c in istogramma.values() if c > 0), reverse=True)
limit = len(counts) if max_k is None else max_k
counts = counts[:limit + 1] + [0] * max(0, limit + 1 - len(counts))
return {k: float(counts[k - 1] - counts[k]) for k in range(1, limit + 1)}
```
- L'array `counts` viene esteso con zeri fino a una dimensione minima di $\text{limit} + 1$.
- Se sono presenti $M$ token osservati ($c_1 \ge \dots \ge c_M > 0$) e $\text{limit} \ge M$, il gap all'indice $M$ vale esattamente:
  $$d_M = \text{counts}[M-1] - \text{counts}[M] = c_M - 0 = c_M$$
- Per ogni $k > M$, $\text{counts}[k-1] - \text{counts}[k] = 0 - 0 = 0.0$.
Di conseguenza, il dominio valutato da FindBestK include sempre tutti gli indici $k \in [1, 10]$ anche in presenza di istogrammi vuoti o sparsi.

---

### 3.2 Deep-Dive 2: TopKWithPTR, Propose-Test-Release e Stabilità Locale

#### 3.2.1 Formulazione del Test del Gap Rumoroso
L'Algoritmo 2 (*TopKWithPTR*) di Tang et al. definisce la condizione di rilascio delle prime $k$ parole chiave:
$$\hat{d}_k = \max(2, d_k) + \mathcal{N}(0, 4\sigma^2) - \Phi^{-1}(1 - \delta; 0, 2\sigma) > 2$$
Nel codice (`core/privacy.py:506-509`):
```python
gaussian_threshold = 2.0 * sigma * (-NormalDist().inv_cdf(delta))
gaussian_noise = float(_rng_or_default(rng).normal(loc=0.0, scale=2.0 * sigma))
noisy_gap = max(GLOBAL_GAP_SENSITIVITY, gap) + gaussian_noise - gaussian_threshold
passed = noisy_gap > GLOBAL_GAP_SENSITIVITY and (
    not strict_gap_guard or gap > GLOBAL_GAP_SENSITIVITY
)
```

**Stabilità numerica della soglia:**  
La soglia teorica corrisponde al quantile $\Phi^{-1}(1-\delta; 0, 2\sigma) = 2\sigma \cdot \Phi^{-1}_{\text{std}}(1-\delta)$. Calcolare direttamente $1-\delta$ in precisione floating-point a 64 bit causa perdita catastrofica di precisione quando $\delta \le 10^{-15}$, portando $1-\delta$ a fondersi con $1.0$ e generando un valore infinito o non definito.  
Sfruttando la simmetria della distribuzione normale standard:
$$\Phi^{-1}_{\text{std}}(1 - \delta) = -\Phi^{-1}_{\text{std}}(\delta)$$
L'uso di `-NormalDist().inv_cdf(delta)` garantisce la corretta computazione della soglia per qualsiasi valore infinitesimo di $\delta$.

#### 3.2.2 Garanzia di Stabilità Locale per $d_k > 2$
Siano $S_k(D)$ l'insieme dei primi $k$ token più frequenti nel corpus $D$. Il Teorema A.10 dimostra che se il gap empirico soddisfa $d_k = H(k) - H(k+1) > 2$, allora per qualunque dataset adiacente $D' \sim D$:
$$S_k(D) = S_k(D')$$
Poiché la sensibilità globale di $H(k)$ è unitaria, un dataset adiacente può variare il conteggio di ciascun token al massimo di $\pm 1$. Se la distanza minima tra il $k$-esimo token e il $(k+1)$-esimo token è strettamente maggiore di 2, nessun token esterno può superare o eguagliare la frequenza dei primi $k$ token. La sensibilità locale dell'insieme $S_k(D)$ è pertanto identicamente nulla.

#### 3.2.3 Semantica del Failure Branch ($d_k \le 2$) e Ruolo di `strict_gap_guard`
Quando il gap privato non soddisfa la condizione di stabilità ($d_k \le 2$), il termine $\max(2, d_k)$ collassa a $2$.
La disuguaglianza del test rumoroso diventa:
$$2 + \mathcal{N}(0, 4\sigma^2) - 2\sigma \Phi^{-1}_{\text{std}}(1-\delta) > 2 \iff \mathcal{N}(0, 4\sigma^2) > 2\sigma \Phi^{-1}_{\text{std}}(1-\delta)$$
Standardizzando la variabile gaussiana:
$$\Pr[\hat{d}_k > 2] = \Pr\left[ \frac{\mathcal{N}(0, 4\sigma^2)}{2\sigma} > \Phi^{-1}_{\text{std}}(1-\delta) \right] = 1 - (1 - \delta) = \delta$$
Questo risultato evidenzia che:
1. Con $d_k \le 2$, il test rumoroso ha una probabilità analitica esatta pari a $\delta$ di passare accidentalmente.
2. Questo evento eccezionale corrisponde alla probabilità di fallimento tollerata nella definizione di approximate $(\epsilon, \delta)$-DP e di $\delta$-approximate RDP (Definizione A.5).
3. `strict_gap_guard` è un'opzione difensiva aggiuntiva implementata in `core/privacy.py:470`: se attivata, impone `passed = False` ogni volta che il vero gap privato non rumoroso è $\le 2$. Tuttavia, come correttamente specificato in `PRIVACY_ACCOUNTING.md` e nei commenti del codice, `strict_gap_guard` è **disattivata di default (`False`)**, poiché il paper originale include analiticamente tale probabilità residua all'interno del parametro $\delta$.

#### 3.2.4 Ordinamento Alfabetico ed Esclusione di Ranghi e Frequenze Private
Sebbene per $d_k > 2$ l'**insieme** $S_k(D)$ sia localmente stabile, l'**ordinamento interno** dei primi $k$ elementi non è stabile. Due token con frequenze molto vicine all'interno dei primi $k$ possono scambiarsi di posizione in un dataset adiacente ($c_1 = 10, c_2 = 9 \implies c'_1 = 9, c'_2 = 10$).  
Se il meccanismo rilasciasse i token ordinati per frequenza o allegasse i conteggi osservati, esporrebbe canali con sensibilità globale unitaria senza alcun rumore di protezione.

Per impedire categoricamente questa fuga:
1. In `core/privacy.py:512`:
   ```python
   released_tokens = tuple(sorted(token_ordinati[:k])) if passed else ()
   ```
   I token vengono ordinati esclusivamente in ordine alfabetico/lessicografico.
2. In `core/privacy.py:350` (`_ordina_token`):
   ```python
   token_validi = [token for token, count in istogramma.items() if count > 0]
   ```
   I token con frequenza zero vengono categoricamente esclusi dall'insieme dei candidati.
3. In `core/cloud.py:105`:
   ```python
   keyword_string = ", ".join(sorted(set(parole_chiave)))
   ```
   L'adattatore cloud riordina e deduplica alfabeticamente l'elenco prima di includerlo nel prompt, realizzando un secondo livello di difesa in profondità.

---

### 3.3 Deep-Dive 3: Accounting RDP e Conversione $(\epsilon, \ delta)$-DP

#### 3.3.1 Bound RDP per il Meccanismo Esponenziale (Teorema A.9)
Il Teorema A.9 di Tang et al. dimostra che un meccanismo $\epsilon_{\text{find}}$-DP soddisfa per ogni ordine $\alpha > 1$ un bound in Rényi Differential Privacy limitato da:
$$\epsilon_{\text{EM}}(\alpha) := \min\left( \frac{\alpha \epsilon^2_{\text{find}}}{2}, \frac{1}{\alpha - 1} \log \frac{\sinh(\alpha \epsilon_{\text{find}}) - \sinh((\alpha - 1) \epsilon_{\text{find}})}{\sinh(\epsilon_{\text{find}})} \right)$$

Nel codice (`core/privacy.py:569-598`), il rapporto iperbolico è riscritto applicando la formula di prostaferesi per eliminare le instabilità numeriche:
$$\sinh(\alpha\epsilon) - \sinh((\alpha-1)\epsilon) = 2 \sinh\left(\frac{\epsilon}{2}\right) \cosh\left(\frac{2\alpha - 1}{2}\epsilon\right)$$
$$\sinh(\epsilon) = 2 \sinh\left(\frac{\epsilon}{2}\right) \cosh\left(\frac{\epsilon}{2}\right)$$
Semplificando il fattore $2 \sinh(\epsilon/2)$, il logaritmo del rapporto si riduce esattamente alla differenza tra funzioni $\log \cosh$:
$$\log \frac{\sinh(\alpha\epsilon) - \sinh((\alpha-1)\epsilon)}{\sinh(\epsilon)} = \log \cosh\left(\frac{2\alpha - 1}{2}\epsilon\right) - \log \cosh\left(\frac{\epsilon}{2}\right)$$
La funzione `_log_cosh(x)` è implementata mediante $x + \log(1 + e^{-2x}) - \log(2)$, garantendo stabilità floating-point assoluta anche per $\alpha = 1024$.

#### 3.3.2 Composizione RDP Lineare (Teorema A.3)
Per il Meccanismo Gaussiano utilizzato in PTR, il Teorema A.10 stabilisce una garanzia di $\delta_{\text{ptr}}$-approximate $\frac{\alpha}{2\sigma^2}$-RDP.  
Per il Teorema A.3 (*Rényi Composition*), le curve di divergenza RDP si compongono linearmente per somma algebrica per ciascun ordine $\alpha$:
$$\epsilon_{\text{RDP}, m}(\alpha) = m \cdot \epsilon_{\text{EM}}(\alpha, \epsilon_{\text{find}}) + m \cdot \frac{\alpha}{2\sigma^2}$$
Mentre per l'union bound il parametro di fallimento PTR cumulativo su $m$ interrogazioni consecutive è:
$$\delta_{\text{ptr}, m} = m \cdot \delta_{\text{ptr}}$$

#### 3.3.3 Conversione in $(\epsilon, \delta)$-DP (Teorema A.6)
Applicando il Teorema A.6 (Canonne et al. 2018 / Balle et al. 2020), dato un budget di conversione $\delta_{\text{conversion}} > 0$:
$$\epsilon_{\text{DP}} = \min_{\alpha \in \mathcal{A}} \left\{ \epsilon_{\text{RDP}}(\alpha) + \frac{\log(1 / \delta_{\text{conversion}})}{\alpha - 1} \right\}$$
Il delta totale consumato dal sistema è la somma rigorosa:
$$\delta_{\text{total}} = m \cdot \delta_{\text{ptr}} + \delta_{\text{conversion}}$$
Nella configurazione predefinita di `core/privacy.py`, per una singola richiesta viene impostato $\delta_{\text{ptr}} = \delta_{\text{conversion}} = 10^{-4}$, determinando un parametro cumulativo $\delta_{\text{total}} = 2 \times 10^{-4}$.

#### 3.3.4 Blocco Proattivo del Budget Multi-Query
L'istanza `DP_KSA_Filter` mantiene lo stato persistente dell'account:
- Prima di eseguire il campionamento o accedere ai token, il metodo `filtra()` invoca internamente `self._account_for_next_invocation()` (riga 959).
- Se la spesa potenziale della chiamata aggiuntiva porterebbe $\epsilon_{\text{DP}} > \epsilon_{\text{budget}} + 10^{-9}$ oppure $\delta_{\text{total}} > \delta_{\text{budget}} + 10^{-15}$, il filtro solleva immediatamente `DPBudgetExhaustedError`.
- Lo stato del generatore di numeri pseudocasuali e il contatore delle invocazioni non vengono modificati.
- A livello architetturale (`core/pipeline.py:82`), il controllo viene effettuato prima del recupero dei documenti dal disco e prima dell'inferenza neurale locale, impedendo qualsiasi fuga temporale o spreco di calcolo.

---

### 3.4 Deep-Dive 4: Unità Protetta, Adiacenza e Scoring Locale

#### 3.4.1 Definizione dell'Unità Protetta
Nella formulazione matematica di Tang et al., l'unità protetta è il singolo documento originale. Due database $D$ e $D'$ sono adiacenti se differiscono per la rimozione o la sostituzione di un singolo documento ($|D \Delta D'| \le 1$).

Nel codice (`core/documents.py`):
- `normalized_content(text)` (riga 20): comprime sequenze multiple di spazi, tabulazioni e caratteri di a capo in singoli spazi, rimuovendo artefatti superficiali di formattazione.
- `content_id(text)` (riga 24): genera l'identificativo univoco mediante l'hash crittografico SHA-256 del testo normalizzato.
- `DocumentCorpus.__init__` (righe 49-57): aggrega i documenti in un dizionario basato su `content_id`. Documenti identici o duplicati all'interno della cartella o del dataset non possono ottenere slot multipli nell'ensemble.
- Anche in `core/dataset.py:99-108`, quando si carica il benchmark SQuAD (in cui più domande condividono il medesimo testo di contesto), i testi vengono raggruppati per `content_id`, assicurando che ciascun contesto origini esattamente un voto.

#### 3.4.2 Scoring Locale ed Eliminazione di Dipendenze Globali
Se il processo di selezione degli estratti (retrieval) utilizzasse statistiche dell'intero corpus (quali Inverse Document Frequency globale, pesature TF-IDF estese al dataset o embedding generati da modelli calibrati sull'intera collezione), la presenza o rimozione del documento $d$ nel dataset $D$ potrebbe alterare il punteggio o l'estratto selezionato per un diverso documento $d'$. In tale scenario, l'adiacenza tra insiemi di risposte risulterebbe violata, invalidando l'ipotesi $\Delta(d_k) = 2$.

Nel codice (`core/documents.py:104-111`):
```python
query_terms = set(re.findall(r'\w+', query.casefold()))
candidates = []
for doc in self.documents:
    words = doc.text.split()
    chunks = [' '.join(words[i:i + chunk_words]) for i in range(0, len(words), chunk_words)]
    scores = [len(query_terms & set(re.findall(r'\w+', chunk.casefold()))) for chunk in chunks]
    best = max(range(len(chunks)), key=lambda i: (scores[i], -i))
    candidates.append(RetrievedDocument(doc.id, chunks[best], doc.source, scores[best]))
selected = sorted(candidates, key=lambda doc: (-doc.score, doc.id))[:n]
```
- **Overlap lessicale puramente locale:** Lo score è il semplice conteggio dei termini della query pubblica presenti nella finestra di 400 parole. Non vi è alcuna consultazione di frequenze del corpus né di modelli di embedding globali.
- **Unicità del contributo:** Ciascun documento produce un solo candidato nell'elenco, selezionando la finestra con punteggio massimo (con tie-break deterministico `-i`).
- **Stabilità dell'ordinamento:** La selezione dei migliori $N$ elementi ordina per punteggio decrescente e risolve i pareggi tramite l'hash crittografico deterministico `doc.id`. Sostituire un documento in $D$ modifica al massimo un documento nell'insieme dei candidati selezionati.

#### 3.4.3 Padding degli Slot Mancanti con Segnaposto Pubblici
Qualora il numero di documenti unici nel corpus sia inferiore a $N$ ($|D| < N$), duplicare documenti esistenti amplificherebbe il peso di tali testi, moltiplicandone i voti nell'istogramma e violando la sensibilità globale.

In `core/documents.py:113-116` e `core/pipeline.py:91-94`:
```python
return selected + [
    RetrievedDocument(f'public-empty-{i}', '', '', 0, True)
    for i in range(n - len(selected))
]
```
Gli slot mancanti vengono popolati da elementi esplicitamente contrassegnati con `is_padding=True`, per i quali la pipeline assegna direttamente bozze testuali vuote `''` senza consultare il modello neurale e senza inserire voti fittizi nell'istogramma privato.

---

### 3.5 Deep-Dive 5: Isolamento dello Scheduler

#### 3.5.1 Pianificazione di $N$ su Parametri Pubblici
In un sistema RAG adattivo, se la dimensione dell'ensemble $N$ dipendesse dalla lunghezza effettiva dei documenti privati recuperati (ad esempio elaborando meno documenti quando i testi estratti sono lunghi), la scelta di $N$ costituirebbe un canale laterale di fuga dell'informazione sulla dimensione o complessità dei dati riservati.

Nel codice (`core/pipeline.py:54-60` e `core/scheduler.py:164-180`):
```python
decision = AdaptiveScheduler(max_tokens=config.max_tokens).schedule(
    [config.prompt_token_budget] * config.candidates,
    epsilon_budget=config.epsilon, delta=config.delta,
    latenza_rete_ms=config.rtt_ms, latenza_massima_ms=config.sla_ms,
    tempo_cloud_ms=config.cloud_ms, tok_per_sec_prefill=config.prefill_tps,
    tok_per_sec_generazione=config.generation_tps, fixed_n=config.fixed_n,
)
```
- Lo scheduler viene eseguito al passo 2 della pipeline, **prima** di caricare il corpus o effettuare il recupero.
- Riceve come input una sequenza omogenea pari a `config.prompt_token_budget` (costante pubblica di configurazione, es. 1000 token). Non riceve le lunghezze reali dei file né il conteggio effettivo dei documenti presenti nel vault.
- Come confermato dal test `test_public_schedule_independent_of_document_lengths_and_count` (`tests/test_request.py:38`), un corpus di documenti lunghi 5.000 parole e un corpus di documenti da 10 parole generano la medesima identica decisione di pianificazione ($N=21$).

#### 3.5.2 Pianificazione Temporale e Fallback Zero-Shot ($N=0$)
L'algoritmo stima il tempo sequenziale massimo necessario per ciascun documento sulla base dei throughput dichiarati:
$$\text{tempo\_documento} = \frac{\text{prompt\_token\_budget}}{\text{tok\_per\_sec\_prefill}} + \frac{\text{max\_tokens}}{\text{tok\_per\_sec\_generazione}}$$
Sottraendo dalla latenza massima consentita dallo SLA la latenza di rete (RTT) e il tempo stimato del provider cloud:
$$\text{tempo\_residuo} = \text{latenza\_massima\_ms} - \text{latenza\_rete\_ms} - \text{tempo\_cloud\_ms}$$
La capacità temporale massima di ensemble è data da:
$$N_{\text{stimato}} = \min\left( N_{\max}, \left\lfloor \frac{\text{tempo\_residuo}}{\text{tempo\_documento}} \right\rfloor \right)$$
Se $N_{\text{stimato}} < N_{\min}$ (dove $N_{\min} = 5$), l'ensemble collassa a $N=0$ (zero-shot). In modalità zero-shot, la pipeline esclude qualsiasi operazione di retrieval, non avvia il motore neurale locale e interpella il cloud con la sola query pubblica.

#### 3.5.3 Semantica di `ptr_pass_rate_attesa`
In `core/scheduler.py:151-163`:
```python
@staticmethod
def _stima_ptr_pass_rate(epsilon_top_k_ptr: float, sigma: float, delta: float) -> float:
    return probabilita_passaggio_ptr(PTR_REPRESENTATIVE_GAP, sigma, delta)
```
La documentazione e il codice chiariscono che tale valore è la probabilità teorica condizionata $P(\text{pass} \mid \text{gap}=3)$ dell'Algoritmo 2 per un salto di frequenza di riferimento pari a 3 (il minimo gap stabile). Il valore non è una stima empirica sul corpus privato (che lo scheduler non può conoscere a priori).

---

### 3.6 Deep-Dive 6: Confini di Rilascio: Cloud e Telemetria

#### 3.6.1 Confinamento del Modulo Cloud (`core/cloud.py`)
Il modulo `core/cloud.py` gestisce l'interazione con l'endpoint esterno.
Nel metodo `_costruisci_prompt` (righe 105-112):
```python
keyword_string = ", ".join(sorted(set(parole_chiave)))
prompt_cloud = (
    "You are a factual synthesis assistant. Answer the user question "
    "based strictly on these privately verified key concepts: "
    f"[{keyword_string}].\n\nQuestion: {domanda}"
)
if not parole_chiave:
    prompt_cloud = f"Answer the question using your general knowledge. Question: {domanda}"
```
- Al modello cloud vengono trasmessi unicamente la query pubblica e l'elenco lessicografico delle parole chiave rilasciate dal filtro.
- I contesti privati (`testi_grezzi_per_confronto`) sono ricevuti dal metodo `genera` esclusivamente per calcolare localmente la riduzione dei byte (`len("\n".join(...))`) a fini di benchmark comparativo. Nessun estratto di documento o frammento di testo privato viene inserito nella richiesta HTTP verso il provider.
- In modalità `offline=True`, il componente non apre connessioni di rete e restituisce un risultato simulato deterministico.

#### 3.6.2 Confinamento della Telemetria (`core/telemetry.py`)
Il tracciamento diagnostico basato su Langfuse è progettato per documentare il comportamento interno della pipeline a fini di ricerca:
- **Redazione per impostazione predefinita (`DEFAULT_CAPTURE_SENSITIVE = False`):**  
  Nella configurazione ordinaria, le tracce omettono il testo della query pubblica, le bozze generate localmente, la dimensione dell'istogramma, i conteggi privati e i termini scartati dal filtro. Vengono registrati solo metadati aggregati non sensibili (ad es. numero di bozze, esito binario del test PTR, tempo di esecuzione).
- **Dichiarazione esplicita nei metadati di traccia:**  
  Ogni traccia generata da `LangfuseTracer` include esplicitamente:
  ```python
  "telemetry_purpose": "thesis_observability",
  "telemetry_dp_guarantee": False,
  "capture_sensitive": self.capture_sensitive
  ```
  Viene così formalmente sancito che i dati di telemetria costituiscono osservabilità di sviluppo e non godono della certificazione differenziale applicata al rilascio cloud.
- **Resilienza dell'infrastruttura:**  
  Tutte le chiamate a Langfuse sono incapsulate in blocchi `try ... except Exception`. Eventuali disconnessioni, timeout o errori del server di tracing non interrompono l'esecuzione della pipeline e non alterano l'output della richiesta.

---

### 3.7 Deep-Dive 7: Verifica Sperimentale e Qualità del Codice

#### 3.7.1 Esito della Suite di Test (`pytest -v`)
L'esecuzione della suite completa dei test su Python 3.13 con pytest 9.1.1 raccoglie 77 test ed è completata in 0.74 secondi con esito interamente positivo:
```
============================== 77 passed in 0.74s ==============================
```
I moduli testati includono:
- `test_privacy.py` (17 test): validazione statistica e formale del rumore Gumbel, del quantile PTR, dell'ordinamento alfabetico, della conservazione contabile e del blocco proattivo.
- `test_scheduler.py` (14 test): copertura di tutti i rami di pianificazione (SLA incompatibile $\implies N=0$, rete veloce $\implies N=40$, esaurimento del budget $\implies \text{PrivacyBudgetExhaustedError}$).
- `test_documents.py` (6 test): deduplicazione dei documenti per hash SHA-256, invarianza rispetto ai frammenti multipli, gestione di PDF con testo estraibile ed esclusione di file nascosti e symlink.
- `test_dataset.py` (4 test): riproducibilità con seed, indipendenza statistica senza seed, deduplicazione dei contesti SQuAD.
- `test_engine.py` (5 test): scaricamento atomico del modello GGUF e cancellazione dei file parziali corrotti.
- `test_cloud.py` (4 test): verifica del confinamento del payload e simulazione offline.
- `test_telemetry.py` (5 test): redazione dei dati sensibili e gestione delle eccezioni di rete.
- `test_request.py` (6 test) e test dei casi applicativi (`test_salary_demo.py`, `test_ticket_demo.py`, `test_ticket_prompts.py`).

#### 3.7.2 Risultati del Linter (`ruff check .`)
Il linter Ruff è stato eseguito sull'intero repository:
```
All checks passed!
```
Nessuna violazione di formattazione, tipizzazione o importazioni inutilizzate è stata riscontrata.

#### 3.7.3 Misurazione della Copertura (`coverage` su `core/scheduler.py`)
La verifica di copertura specifica sul modulo più articolato (`core/scheduler.py`) ha evidenziato:
```
Name                      Stmts   Miss  Cover   Missing
-------------------------------------------------------
core/scheduler.py           119      3    97%   119, 141, 145
tests/test_scheduler.py      64      0   100%
```
Il 97% di copertura supera con ampio margine il limite minimo di accettazione del 90%. Le uniche tre righe non coperte riguardano controlli difensivi su tipi non conformi o valori negativi nei costruttori.

#### 3.7.4 Validazione Statistica del Rumore Gumbel e Meccanismo Esponenziale
In `tests/test_privacy.py`:
- **Scala del rumore Gumbel ($N=10.000$):** Con $\epsilon = 1.0$, la deviazione standard empirica riscalata $\hat{s} = s_{\text{emp}} \cdot \frac{\sqrt{6}}{\pi}$ converge a $4.00 \pm 0.16$, confermando sperimentalmente la calibrazione su scala $4/\epsilon$.
- **Meccanismo Esponenziale (6.000 selezioni):** Configurando due opzioni con utilità $q_1 = 8$ e $q_2 = 2$ con $\epsilon = 1.0$, la probabilità teorica di selezione è:
  $$\Pr[k=1] = \frac{1}{1 + \exp\left( \frac{2 - 8}{4} \right)} = \frac{1}{1 + e^{-1.5}} \approx 0.81757$$
  Il test verifica che la frequenza empirica ricada esattamente entro $\pm 0.02$ da tale valore teorico.

---

## 4. Raccomandazioni e Note per la Tesi

Sulla base delle evidenze emerse dall'audit, si formulano le seguenti raccomandazioni operative e metodologiche da recepire nel testo della tesi di laurea:

1. **Documentazione esplicita della discrepanza della scala Gumbel ($4/\epsilon$ vs $2/\epsilon$):**  
   Nel capitolo metodologico dedicato a DP-KSA, è fondamentale evidenziare con precisione che lo pseudocodice di Algoritmo 3 in Tang et al. riporta $\text{Gumbel}(2/\epsilon)$, ma che la Definizione A.7 del meccanismo esponenziale impone $\beta = \frac{2\Delta}{\epsilon}$. Poiché la sensibilità globale del gap è $\Delta(d_k) = 2$, la scala teorica necessaria per preservare $\epsilon$-DP è categoricamente $4/\epsilon$. Adottare $2/\epsilon$ corrisponderebbe a una perdita di riservatezza reale pari a $2\epsilon$. Questo adattamento prudenziale qualifica il lavoro di tesi per rigore scientifico e maturità critica.

2. **Dichiarazione dell'ambito di persistenza dell'account RDP:**  
   Specificare nella tesi che il PoC implementa un account RDP cumulativo residente nella memoria del processo (`account_scope='single_request'`). Nelle esecuzioni via CLI singola, ogni comando crea una nuova istanza del filtro. In un'architettura di produzione distribuita o multi-utente, la persistenza del budget cumulativo richiederebbe un database sicuro o un registro crittografico di stato condiviso tra i processi di inferenza.

3. **Distinzione netta tra telemetria locale e garanzie di rilascio:**  
   Chiarire nella discussione dei risultati sperimentali che i dati registrati su Langfuse (tracce, tempi di latenza ed esiti dei test) costituiscono strumentazione di osservabilità scientifica autorizzata per la tesi e non sono coperti dal filtro DP. La garanzia differenziale si applica esclusivamente al payload (query e keyword lessicografiche) trasmesso verso il modello cloud.

4. **Trasparenza sulla metrica `ptr_pass_rate_attesa`:**  
   Evidenziare nel testo che il campo `ptr_pass_rate_attesa` calcolato dallo scheduler rappresenta la probabilità condizionata analitica $P(\text{pass} \mid \text{gap}=3)$ dell'Algoritmo 2 per un salto di frequenza rappresentativo pari a 3. Non deve essere interpretato né presentato come una previsione del tasso effettivo di rilascio sul corpus privato, che dipende dalla reale concordanza dei documenti e dalla specificità della domanda.

5. **Formalizzazione del regime di adiacenza e dell'unità protetta:**  
   Sottolineare che la privacy a livello di documento presuppone che l'ingestione assicuri l'indipendenza delle fonti. Poiché la deduplicazione automatica agisce sull'hash crittografico del testo normalizzato, documenti quasi-identici (es. bozze leggermente riviste della stessa comunicazione) devono essere aggregati o sanati nella fase di preparazione dei dati per evitare che una singola entità logica ottenga voti multipli nell'ensemble.

---

## 5. Conclusioni dell'Audit

Il Proof-of-Concept DP-RAG dimostra una completa aderenza ai principi della privacy differenziale, un'architettura modulare rigorosamente confinata e un livello di copertura empirica e di qualità del codice eccellente.  
Tutti i controlli obbligatori risultano conformi; le aree di attenzione individuate (la persistenza multi-processo e le rifiniture opzionali dei test) sono debitamente circoscritte e documentate. Il sistema fornisce una base sperimentale solida, trasparente e scientificamente verificabile per la stesura e la discussione della tesi.
