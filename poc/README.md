# Proof of Concept: DP-KSA (Differential Privacy RAG)

Questo prototipo dimostra operativamente il funzionamento del framework **DP-KSA** (*Differentially Private Keyword-based Semantic Augmentation*) e il ruolo dello **scheduler adattivo** per la tesi in Architetture e Reti di Calcolatori.

---

## Script disponibili

1. **`poc_dp_ksa.py` (Prototipo rapido algoritmico)**  
   Simula l'ensemble con testo predefinito, mostra il conteggio delle frequenze, applica il rumore di Laplace con la soglia PTR e simula la decisione dello scheduler al variare della latenza di rete.
   ```bash
   ./poc/.venv/bin/python poc/poc_dp_ksa.py
   ```

2. **`poc_real_dp_ksa.py` (Pipeline completa con inferenza reale e tracciamento)**  
   - Esegue **inferenza neurale reale** sul modello compatto `Qwen2.5-0.5B-Instruct` quantizzato a 4-bit, con accelerazione hardware Metal su Apple Silicon GPU;
   - Applica il filtro di Privacy Differenziale sulle parole chiave estratte;
   - Invia le parole chiave sicure a **OpenAI** (`gpt-4o-mini`);
   - Invia la traccia distribuita completa a **Langfuse** (mostrando tempi edge, parametri DP, traffico di rete risparmiato e risposta cloud).

---

## Configurazione Credenziali (Opzionale)

Puoi creare un file `poc/.env` partendo da `poc/.env.example`:

```bash
cp poc/.env.example poc/.env
```

Inserisci le tue chiavi nel file `.env`:

```env
OPENAI_API_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # oppure https://us.cloud.langfuse.com
```

---

## Esecuzione completa

Con credenziali in `.env`:
```bash
./poc/.venv/bin/python poc/poc_real_dp_ksa.py
```

Oppure passando i parametri da riga di comando:
```bash
./poc/.venv/bin/python poc/poc_real_dp_ksa.py \
  --api-key "sk-..." \
  --langfuse-pk "pk-lf-..." \
  --langfuse-sk "sk-lf-..."
```

Se Langfuse è configurato, al termine dello script verrà stampato il link diretto alla traccia web su Langfuse.
