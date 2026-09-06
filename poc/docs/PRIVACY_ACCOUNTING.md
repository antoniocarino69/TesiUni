# Privacy Accounting

Questo documento definisce il contratto matematico implementato da
`core.privacy`. Le formule seguono Tang et al., *Differentially Private
Retrieval-Augmented Generation*, Algorithm 2, Algorithm 3 e Theorems A.6,
A.9 e A.10 del PDF incluso nella directory degli studi di partenza.

## Ipotesi

La garanzia riguarda il database esterno di retrieval, non i dati di
pre-training del modello. Per due database adiacenti:

- il retriever modifica al massimo un documento restituito;
- ogni documento restituito appartiene a una sola risposta locale;
- ogni risposta contribuisce al massimo una volta per token all'istogramma;
- la scelta dello scheduler usa soltanto segnali operativi non privati;
- la generazione cloud successiva riceve solo la query e l'output DP.

Se una di queste condizioni non vale, il bound non può essere dichiarato senza
una nuova analisi di sensibilità.

## PTR

Per il candidato `k` si definisce:

```text
g = H(k) - H(k + 1)
Delta(g) = 2
Z ~ Normal(0, 4 sigma^2)
tau = 2 sigma Phi^-1(1 - delta)
g_hat = max(2, g) + Z - tau
```

`TopKWithPTR` rilascia i primi `k` token se e solo se `g_hat > 2`.
Il valore `2` è sia la sensibilità globale della differenza sia la soglia
del test. La funzione `probabilita_passaggio_ptr()` implementa la probabilità
analitica dello stesso evento:

```text
P(pass | g) = 1 - Phi((tau + 2 - max(2, g)) / (2 sigma))
```

Per `g <= 2`, la formula si riduce a `delta`. Questo è il failure event
contabilizzato dal Theorem A.10. Per `g > 2`, la probabilità cresce con il gap.

`strict_gap_guard=True` sopprime anche il failure event `g <= 2`. È una policy
operativa aggiuntiva, non l’Algorithm 2 del paper: non viene attivata di
default e non deve essere presentata come parte della prova formale senza una
dimostrazione separata.

## RDP per una chiamata

Per ogni ordine di Rényi `alpha` il filtro compone:

```text
epsilon_find(alpha) = epsilon_EM(alpha)
epsilon_ptr(alpha)  = alpha / (2 sigma^2)
epsilon_total(alpha) = epsilon_find(alpha) + epsilon_ptr(alpha)
```

La conversione usa il Theorem A.6:

```text
epsilon_DP = min_alpha(
    epsilon_total(alpha) + log(1 / delta_conversion) / (alpha - 1)
)
delta_total = delta_ptr + delta_conversion
```

`delta_ptr` è il failure probability del PTR; `delta_conversion` è il delta
usato nella conversione RDP-to-DP. Per impostazione predefinita entrambi
valgono `delta`, quindi `delta_total = 2 * delta` per una chiamata.

## Composizione tra chiamate

Un `DP_KSA_Filter` è un account stateful. Se la stessa istanza viene usata `n`
volte su dati correlati, il filtro non somma gli epsilon già convertiti.
Ricostruisce invece l’account composto per ogni ordine:

```text
epsilon_find_n(alpha) = n * epsilon_find(alpha)
epsilon_ptr_n(alpha)  = n * epsilon_ptr(alpha)
epsilon_total_n(alpha) = epsilon_find_n(alpha) + epsilon_ptr_n(alpha)
delta_ptr_n = n * delta_ptr
delta_total_n = delta_ptr_n + delta_conversion
```

Solo dopo questa composizione viene applicato il `min` sugli ordini e viene
calcolato `epsilon_DP`. Una nuova chiamata che supererebbe il budget solleva
`DPBudgetExhaustedError` prima di consumare nuova casualità.

Di conseguenza:

- `budget_consumato_epsilon` e `budget_consumato_delta` sono cumulativi;
- `epsilon_rimasto` è sempre `epsilon_budget - epsilon_DP_cumulativo`;
- `numero_invocazione` identifica il punto dell’account composto;
- per richieste indipendenti va creata una nuova istanza del filtro;
- un RNG passato al filtro, o creato automaticamente quando `rng=None`, vive
  per tutta la durata dell’istanza.

## Audit e telemetria

`EsitoDP` contiene diagnostica privata utile per esperimenti locali. Non tutto
il contenuto dell’oggetto è un output da inviare al cloud. In particolare,
conteggi, gap, ordine dei token e token scartati devono rimanere nel perimetro
fidato.

`LangfuseTracer` applica per default una modalità redatta:

- niente query, bozze locali, istogrammi grezzi, gap grezzi o risposta finale;
- solo contatori, tempi, esito del PTR e accounting aggregato;
- i token rilasciati possono essere tracciati perché sono già l’output DP
  inviato al provider cloud.

`LANGFUSE_CAPTURE_SENSITIVE=true` abilita la diagnostica completa. Va usato
solo con un’istanza Langfuse fidata, preferibilmente self-hosted e nella stessa
zona di sicurezza del sistema. Il tracer resta best-effort: un errore di
connessione o flush non modifica la decisione privacy.

## Verifiche automatiche

I test coprono:

- riduzione analitica a `P(pass) = delta` per `g <= 2`;
- formula analitica per un gap stabile `g = 3`;
- composizione cumulativa di epsilon e delta tra invocazioni;
- rifiuto della chiamata successiva al superamento del budget;
- persistenza dello stream RNG per istanza;
- redazione e opt-in dei payload Langfuse;
- percorso `DatasetLoader -> AdaptiveScheduler -> DP_KSA_Filter` senza modello.
