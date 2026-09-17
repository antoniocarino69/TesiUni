# Piano pratico di misurazione — `poc/`

Cartella operativa per le misurazioni manuali. **Qui non c'è codice da eseguire in automatico**:
i comandi elencati vanno lanciati a mano da terminale, nell'ordine indicato, leggendo l'output.

Tutti i comandi si intendono eseguiti dalla directory `poc/` con l'ambiente attivo
(`.venv/bin/python …`, **mai** il Python di sistema).

---

## 0. Prima di iniziare — sanity check (5 secondi)

Serve a verificare che l'ambiente sia quello giusto: venv attivo, modello presente,
benchmark scaricato, ruff pulito, test verdi.

```bash
pwd                                    # deve stampare .../poc
.venv/bin/python --version             # 3.13.x
ls models/*.gguf                       # il modello GGUF deve esistere
ls data/squad_real_benchmark.json      # il benchmark SQuAD deve esistere
.venv/bin/python -m ruff check .        # atteso: All checks passed!
.venv/bin/python -m pytest -q          # atteso: 181 passed
```

**A cosa serve:** se uno qualunque di questi fallisce, i comandi sotto daranno numeri
sbagliati o vuoti. È la prima cosa da controllare prima di fidarsi di una misurazione.

---

## 1. Misure statiche — capire a cosa corrispondono i campi del report

Queste misure non richiedono di far girare la pipeline: leggono i moduli e stampano i
valori di default, utili per sapere *prima* cosa ti aspetti.

```bash
# Limiti del prompt, lunghezze, default dello scheduler
.venv/bin/python -c "
from core import model_config, scheduler
print('PROMPT_LIMIT:', model_config.PROMPT_LIMIT)
print('GENERATION_TOKENS:', model_config.GENERATION_MAX_TOKENS)
print('N_MIN:', scheduler.N_MIN, 'N_MAX:', scheduler.N_MAX)
"

# Costanti del meccanismo DP (dominio pubblico, scala Gumbel, sigma, delta)
.venv/bin/python -c "
from core.privacy import DP_KSA_Filter
import inspect
sig = inspect.signature(DP_KSA_Filter.__init__)
print('signature:', sig)
"
```

**A cosa serve:** vedere i numeri che la tesi cita. Se `N_MIN=5`, `N_MAX=40`,
epsilon budget ecc. — è il punto di partenza per interpretare i report.

---

## 2. Smoke test della pipeline end-to-end (modalità offline)

La modalità offline **non chiama il cloud provider**, usa il simulatore deterministico.
È la misura più riproducibile: la lanci N volte e ottieni tempi confrontabili.

```bash
.venv/bin/python run_pipeline.py --offline-cloud --no-telemetry \
    --query "What is the capital of France?" \
    --budget-epsilon 4.0 --budget-delta 1e-5
```

**A cosa serve:** vedere il ciclo completo (calibrazione → filtro → scheduler →
zero-shot / ensemble → risposta) **senza dipendenza dalla rete**. Utile per:
- verificare che il filtro rilasci parole attese;
- misurare quanto tempo spende il filtro su un istogramma tipico;
- misurare la latenza di N=0 (zero-shot puro).

Output chiave da leggere nel report JSON:
- `N_scelto`, `esito.filtro.rilasciate`, `sforamento_previsto_ms`,
  `sforamento_accettato`, `request_ms`, `cli_total_ms`.

---

## 3. Misure con cloud reale (provider commandcode.ai)

### 3.1 Probe E2E di sessione (A1)

```bash
.venv/bin/python run_pipeline.py \
    --query "What is the capital of France?" \
    --budget-epsilon 4.0 --budget-delta 1e-5
```

**A cosa serve:** il primo avvio della sessione esegue **una sola generazione pubblica
di probe** per misurare `E2E_cloud_ms` (tempo complessivo della chiamata, rete inclusa).
Quel valore entra in `cli_total_ms` ma **non** in `request_ms`. Senza credenziali o con
`--offline-cloud`, il probe è saltato (`cloud_probe_skipped=True`) e `E2E_cloud_ms` cade
sul fallback `RTT + tempo_cloud_ms`.

### 3.2 Variazione di N — misurare l'effetto del piano adattivo

```bash
for N in 0 5 10 20 40; do
  echo "=== N=$N ==="
  .venv/bin/python run_pipeline.py --offline-cloud --no-telemetry \
      --query "Describe the role of attention in transformers." \
      --fixed-n $N --budget-epsilon 8.0 --budget-delta 1e-5 \
      2>&1 | tail -5
done
```

**A cosa serve:** `fixed_n` è una baseline sperimentale che **può eccedere lo SLA**.
Serve per misurare la latenza e l'utilità al crescere di N, tenendo fissa la query.
Confronta i `request_ms` tra i valori di N: è la curva che motiva lo scheduler adattivo.

### 3.3 Variazione della soglia di sforamento (A2)

```bash
for K in 0 1 2 5; do
  echo "=== sforamento-k=$K ==="
  .venv/bin/python run_pipeline.py --offline-cloud --no-telemetry \
      --query "Describe the role of attention in transformers." \
      --sforamento-k $K --budget-epsilon 4.0 --budget-delta 1e-5 \
      2>&1 | tail -3
done
```

**A cosa serve:** con `k=0` lo scheduler è prudente (rifiuta `N=5` se sfora). Con
`k>0` accetta `N=N_MIN` se lo sforamento rientra in `k × (RTT + tempo_cloud_ms)`. Misura
frequenza ed entità degli sforamenti accettati: `sforamento_previsto_ms`,
`sforamento_accettato`, `tolleranza_sforamento_ms`.

---

## 4. Telemetria hardware (Apple Silicon)

### 4.1 Con `macmon` (no sudo, preferito)

```bash
which macmon                                            # atteso: /opt/homebrew/bin/macmon
.venv/bin/python -c "
from core.telemetry_hw import HardwareSampler
s = HardwareSampler()
print('backend:', s.backend_name())
print('sample:', s.sample())
"
```

**A cosa serve:** `HardwareSampler` rileva automaticamente `macmon` se presente ed
espone temperatura, watt, CPU/GPU. Se `macmon` non c'è, il modulo ripiega su
`powermetrics` (sudo necessario per temperatura e watt).

### 4.2 Benchmark scheduler

```bash
.venv/bin/python benchmark_scheduler.py \
    --samples 50 --seeds 5 \
    --output reports/scheduler_benchmark.json
```

**A cosa serve:** misura sistematica del piano adattivo al variare di seed e
parametri (RTT simulato, tempo cloud, lunghezza prompt). I campi chiave sono
distribuzione di `N_scelto`, `sla_fattibile`, `sforamento_previsto_ms`.

---

## 5. Verifica del meccanismo DP (privacy accounting)

Queste misure toccano direttamente gli invarianti del paper. Da eseguire con
attenzione e i risultati vanno confrontati con i valori analitici.

```bash
# Bilancio del budget dopo una chiamata
.venv/bin/python -c "
from core.privacy import DP_KSA_Filter
f = DP_KSA_Filter(epsilon_budget=4.0, delta_budget=1e-5)
esito = f.filtra(['alpha','beta','gamma','alpha','beta','alpha','alpha','alpha','alpha'])
print('rilasciate:', esito.rilasciate)
print('budget_consumato_epsilon:', esito.budget_consumato_epsilon)
print('budget_consumato_delta:', esito.budget_consumato_delta)
print('epsilon_rimasto + epsilon_consumato == 4.0 ?',
      abs((f.epsilon_rimasto + esito.budget_consumato_epsilon) - 4.0) < 1e-9)
"

# Test statistico della scala Gumbel
.venv/bin/python -m pytest -v tests/test_privacy.py -k gumbel
```

**A cosa serve:** la prima verifica l'invariante "budget consumato + rimanente = totale".
La seconda verifica che la scala del rumore Gumbel sia ~4/ε (definizione A.7 del paper),
non 2/ε come dice il pseudocodice — la differenza è documentata in
`docs/PRIVACY_ACCOUNTING.md`.

---

## 6. Confronto riproducibilità (con / senza `--seed`)

```bash
# Stessa query due volte, seed diversi
.venv/bin/python run_pipeline.py --offline-cloud --no-telemetry \
    --query "Q" --seed 42 2>&1 | grep -E 'N_scelto|rilasciate' | head -2
.venv/bin/python run_pipeline.py --offline-cloud --no-telemetry \
    --query "Q" --seed 43 2>&1 | grep -E 'N_scelto|rilasciate' | head -2
```

**A cosa serve:** la pipeline corrente usa retrieval deterministico per query, quindi
`--seed` influenza solo il campionamento di ensemble. Verifica che il seed sia
rispettato nell'API `ottieni_campione_ensemble(n, seed=seed)`.

---

## 7. Cosa riportare nei campi della tesi

| Campo report                  | Significato                                                | Unità |
| ----------------------------- | ---------------------------------------------------------- | ----- |
| `N_scelto`                    | inferenze locali pianificate dallo scheduler               | int   |
| `esito.filtro.rilasciate`     | parole rilasciate dal filtro DP-KSA in ordine alfabetico   | list  |
| `budget_consumato_epsilon`    | ε speso per la chiamata (somma dei due algoritmi)          | float |
| `sforamento_previsto_ms`      | stima di sforamento rispetto allo SLA per il piano scelto  | ms    |
| `sforamento_accettato`        | True se lo scheduler ha accettato lo sforamento (k>0)      | bool  |
| `cli_total_ms`                | tempo totale CLI inclusivo di calibrazione e probe         | ms    |
| `request_ms`                  | tempo di una singola richiesta (no probe, no calibrazione) | ms    |
| `E2E_cloud_ms`                | tempo end-to-end di una generazione cloud                  | ms    |
| `cloud_probe_skipped`         | True se il probe E2E non è stato eseguito                  | bool  |
| `ptr_pass_rate_attesa`        | solo P(pass \| gap=3), non previsione sul corpus           | float |

---

## 8. Note operative

- I tempi di prefill esposti da `core.engine` (`tempo_prefill_stimato_sec`) sono
  **stime euristiche**, non misurazioni dirette. Quando li riporti, etichettali come tali.
- Lo SLA è **soft**: sforamenti occasionali sono accettabili. Misura frequenza ed entità.
- Privacy e utilità hanno precedenza sul rispetto puntuale dello SLA: non alzare il
  budget o saltare il filtro per ottenere tempi migliori.
- Con `--offline-cloud` e senza credenziali i tempi cloud sono **simulati** e non
  rappresentano la qualità reale del provider.
- I report JSON vanno in `poc/reports/` o `poc/report_*.json` a seconda dello script.
