#!/usr/bin/env python3
"""
PoC Completo: Differentially Private RAG (DP-KSA) con Inferenza Neurale Reale.
Esegue un modello compatto reale (Qwen 2.5 0.5B GGUF) in locale con accelerazione Metal,
applica la Privacy Differenziale alle parole chiave estratte ed effettua la chiamata finale
a OpenAI (se presente la chiave API).
"""

import os
import sys
import time
import argparse
from typing import List, Dict, Tuple, Optional
import numpy as np
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Carica automaticamente variabili d'ambiente da file .env se presente
load_dotenv()

console = Console()

def inizializza_langfuse(pk: Optional[str] = None, sk: Optional[str] = None, host: Optional[str] = None):
    """Inizializza il client Langfuse se le credenziali sono presenti."""
    public_key = pk or os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = sk or os.environ.get("LANGFUSE_SECRET_KEY")
    host_url = host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        return None

    try:
        from langfuse import Langfuse
        client = Langfuse(public_key=public_key, secret_key=secret_key, host=host_url)
        if client.auth_check():
            console.print(f"[bold green]Langfuse connesso con successo[/bold green] ([dim]{host_url}[/dim])")
            return client
        else:
            console.print("[yellow]Avviso: credenziali Langfuse non valide. Tracciamento remoto disattivato.[/yellow]")
            return None
    except Exception as e:
        console.print(f"[yellow]Avviso: impossibile connettersi a Langfuse ({e}). Proseguo senza tracciamento remoto.[/yellow]")
        return None

# --- DOCUMENTI PRIVATI NEL DATABASE LOCALE ---
DOCUMENTI_LOCALE = [
    {
        "id": "DOC-001",
        "testo": "Cartella clinica di Mario Rossi (CF: RSSMRA78A01H501Z). Diagnosi: Ipertensione arteriosa stadio 2. Terapia prescritta: Ramipril 10mg al mattino."
    },
    {
        "id": "DOC-002",
        "testo": "Cartella clinica di Luca Bianchi (CF: BNCLCU82C12L219K). Diagnosi: Ipertensione arteriosa primaria. Trattamento confermato: Ramipril 10mg."
    },
    {
        "id": "DOC-003",
        "testo": "Cartella clinica di Anna Verdi (CF: VRDNNA90M41F205X). Paziente affetta da Ipertensione arteriosa. Risposta positiva al trattamento con Ramipril."
    },
    {
        "id": "DOC-004",
        "testo": "Cartella clinica di Giovanni Neri (CF: NREGNN65T08A662P). Diagnosi: Ipertensione arteriosa lieve. Trattamento raccomandato: Ramipril 5mg."
    },
    {
        "id": "DOC-005_CONFIDENZIALE",
        "testo": "Nota confidenziale interna: Il paziente Mario Rossi ha debiti tributari di 45.000 euro e pignoramenti in corso."
    }
]

QUERY_DEFAULT = "Qual è il trattamento raccomandato per l'ipertensione?"

STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in", "con",
    "su", "per", "tra", "fra", "e", "ed", "o", "ha", "al", "del", "della", "delle", "dei",
    "ai", "agli", "alle", "dal", "dalla", "dalle", "nel", "nella", "cartella", "clinica",
    "paziente", "cf", "nota", "diagnosi", "raccomandato", "prescritta", "confermato", "è"
}

def estrai_parole(testo: str) -> List[str]:
    # Sostituisce apostrofi e punteggiatura con spazi per separare articoli (es. l'ipertensione -> ipertensione)
    testo_pulito = testo.replace("'", " ").replace("’", " ")
    parole = "".join(c if c.isalnum() or c.isspace() else " " for c in testo_pulito.lower()).split()
    return [p for p in parole if p not in STOPWORDS and len(p) > 2]


def carica_modello_locale(model_path: str):
    """Carica il modello con llama-cpp-python e accelerazione Metal."""
    try:
        from llama_cpp import Llama
    except ImportError:
        console.print("[red]Errore: 'llama_cpp' non è installato nell'ambiente virtuale.[/red]")
        sys.exit(1)

    console.print(f"[cyan]Caricamento modello locale GGUF:[/cyan] {model_path}")
    console.print("[dim]Inizializzazione con supporto accelerazione hardware Metal (GPU)...[/dim]")
    
    t0 = time.perf_counter()
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,      # Sposta tutti i layer su GPU (Metal su Apple Silicon)
        n_ctx=2048,           # Finestra di contesto
        verbose=False         # Disabilita i log a basso livello per mantenere pulito l'output
    )
    t_load = time.perf_counter() - t0
    console.print(f"[green]Modello caricato in memoria in {t_load:.2f} secondi.[/green]\n")
    return llm


def genera_bozza_neurale(llm, doc_text: str, query: str) -> Tuple[str, float, int]:
    """Esegue un'inferenza reale sul documento locale."""
    prompt = (
        f"<|im_start|>system\n"
        f"Sei un assistente medico conciso. Rispondi alla domanda dell'utente usando ESCLUSIVAMENTE "
        f"le informazioni contenute nel documento di contesto. Rispondi in massimo 10 parole in italiano.<|im_end|>\n"
        f"<|im_start|>user\n"
        f"Documento:\n{doc_text}\n\n"
        f"Domanda: {query}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    t0 = time.perf_counter()
    output = llm(
        prompt,
        max_tokens=30,
        temperature=0.3,
        stop=["<|im_end|>", "\n\n"]
    )
    t_gen = time.perf_counter() - t0

    testo = output["choices"][0]["text"].strip()
    tokens = output["usage"]["completion_tokens"]
    return testo, t_gen, tokens


def applica_dp_ptr(
    bozze: List[str],
    epsilon: float,
    soglia_tau: float
) -> Tuple[Dict[str, int], Dict[str, float], Dict[str, float], List[str], List[str]]:
    """Applica Propose-Test-Release (PTR) con rumore Laplace."""
    conteggi: Dict[str, int] = {}
    for bozza in bozze:
        parole_uniche = set(estrai_parole(bozza))
        for p in parole_uniche:
            conteggi[p] = conteggi.get(p, 0) + 1

    scala_rumore = 1.0 / max(epsilon, 1e-4)
    conteggi_rumorosi: Dict[str, float] = {}
    rumore_applicato: Dict[str, float] = {}
    rilasciati = []
    scartati = []

    for parola, freq in conteggi.items():
        rum = float(np.random.laplace(0.0, scala_rumore))
        tot = freq + rum
        conteggi_rumorosi[parola] = tot
        rumore_applicato[parola] = rum

        if tot >= soglia_tau:
            rilasciati.append(parola)
        else:
            scartati.append(parola)

    rilasciati.sort(key=lambda p: conteggi_rumorosi[p], reverse=True)
    scartati.sort(key=lambda p: conteggi_rumorosi[p], reverse=True)
    return conteggi, conteggi_rumorosi, rumore_applicato, rilasciati, scartati


def chiama_cloud_openai(query: str, parole_chiave: List[str], api_key: str = None) -> Tuple[str, float, int]:
    """Invia le parole chiave al servizio Cloud (OpenAI) per la risposta finale."""
    stringa_kw = ", ".join(parole_chiave)
    prompt_cloud = (
        f"Sei un assistente medico professionale. Rispondi alla seguente domanda basandoti "
        f"esclusivamente su queste parole chiave certificate estratte in modo sicuro: [{stringa_kw}].\n\n"
        f"Domanda: {query}"
    )
    byte_inviati = len(prompt_cloud.encode("utf-8"))

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return (
            f"[SIMULAZIONE CLOUD] Risposta generata con i termini [{stringa_kw}]: "
            "Il trattamento farmacologico indicato per l'ipertensione arteriosa è il Ramipril. "
            "(Nessuna chiave API OpenAI fornita: chiamata remota simulata).",
            0.0,
            byte_inviati
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sei un assistente medico conciso e accurato."},
                {"role": "user", "content": prompt_cloud}
            ],
            temperature=0.2,
            max_tokens=80
        )
        t_call = time.perf_counter() - t0
        risposta_testo = response.choices[0].message.content.strip()
        return risposta_testo, t_call, byte_inviati
    except Exception as e:
        return f"Errore durante la chiamata API OpenAI: {str(e)}", 0.0, byte_inviati


def main():
    parser = argparse.ArgumentParser(description="PoC DP-KSA con Inferenza Neurale Reale")
    parser.add_argument("--model", type=str, default=None, help="Percorso del modello GGUF")
    parser.add_argument("--api-key", type=str, default=None, help="Chiave API OpenAI")
    parser.add_argument("--epsilon", type=float, default=1.0, help="Budget di Privacy Differenziale (default: 1.0)")
    parser.add_argument("--tau", type=float, default=3.0, help="Soglia di rilascio PTR (default: 3.0)")
    parser.add_argument("--langfuse-pk", type=str, default=None, help="Langfuse Public Key")
    parser.add_argument("--langfuse-sk", type=str, default=None, help="Langfuse Secret Key")
    parser.add_argument("--langfuse-host", type=str, default=None, help="Langfuse Host URL")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]PoC Completo: DP-KSA con Inferenza Neurale Reale (Edge + Cloud)[/bold cyan]\n"
        "[dim]Inferenza locale su Apple Silicon (Metal) + Privacy Differenziale + Chiamata Cloud + Tracciamento Langfuse[/dim]",
        border_style="cyan"
    ))

    # Inizializzazione Langfuse (se configurato)
    lf_client = inizializza_langfuse(args.langfuse_pk, args.langfuse_sk, args.langfuse_host)
    trace = None
    if lf_client:
        trace = lf_client.trace(
            name="dp-rag-distributed-request",
            input={"query": QUERY_DEFAULT},
            metadata={
                "hardware": "Apple Silicon (Metal)",
                "local_model": "Qwen2.5-0.5B-Instruct-Q4_K_M",
                "epsilon": args.epsilon,
                "tau": args.tau
            }
        )

    # Individua modello
    model_path = args.model
    if not model_path:
        default_model = os.path.join(os.path.dirname(__file__), "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
        if os.path.exists(default_model):
            model_path = default_model
        else:
            console.print("[yellow]Modello non trovato in locale. Avvio download automatico...[/yellow]")
            from download_model import main as scarica
            model_path = scarica()

    # Caricamento motore locale
    llm = carica_modello_locale(model_path)

    # 1. ESECUZIONE ENSEMBLE LOCALE REALE
    console.print(Panel(
        f"[bold]Fase 1: Inferenza Neurale Locale (Edge)[/bold]\n"
        f"Domanda: [italic yellow]{QUERY_DEFAULT}[/italic yellow]\n"
        f"Il modello compatto locale elaborerà ciascun documento per generare l'ensemble di risposte.",
        border_style="blue"
    ))

    t_ensemble_table = Table(title="Risposte generate dal Modello Locale sull'Hardware", show_header=True)
    t_ensemble_table.add_column("Doc ID", style="dim", width=12)
    t_ensemble_table.add_column("Bozza Generata dal Modello Neurale Locale")
    t_ensemble_table.add_column("Tempo (ms)", justify="right")
    t_ensemble_table.add_column("Token/s", justify="right")

    bozze: List[str] = []
    tempi_gen: List[float] = []
    totale_tokens = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Esecuzione inferenza neurale sull'hardware locale...", total=len(DOCUMENTI_LOCALE))
        for doc in DOCUMENTI_LOCALE:
            testo_bozza, tempo_sec, n_tok = genera_bozza_neurale(llm, doc["testo"], QUERY_DEFAULT)
            bozze.append(testo_bozza)
            tempi_gen.append(tempo_sec)
            totale_tokens += n_tok

            tok_per_sec = (n_tok / tempo_sec) if tempo_sec > 0 else 0
            t_ensemble_table.add_row(
                doc["id"],
                f"[italic]\"{testo_bozza}\"[/italic]",
                f"{tempo_sec * 1000:.1f}",
                f"{tok_per_sec:.1f}"
            )
            progress.advance(task)

    console.print(t_ensemble_table)
    tempo_totale_locale = sum(tempi_gen)
    velocita_media = totale_tokens / tempo_totale_locale if tempo_totale_locale > 0 else 0
    console.print(f"[dim]Tempo totale calcolo locale: {tempo_totale_locale:.3f} s | Velocità media: {velocita_media:.1f} token/s[/dim]\n")

    if trace:
        span_local = trace.span(
            name="edge-neural-ensemble",
            input={"num_docs": len(DOCUMENTI_LOCALE), "query": QUERY_DEFAULT},
            metadata={
                "hardware": "Apple Silicon (Metal)",
                "duration_ms": round(tempo_totale_locale * 1000, 1),
                "tokens_generated": totale_tokens,
                "tokens_per_sec": round(velocita_media, 1)
            }
        )
        span_local.end(output={"bozze_generate": bozze})

    # 2. APPLICAZIONE MECCANISMO DP (PTR)
    console.print(Panel(
        f"[bold]Fase 2: Filtro di Privacy Differenziale (Propose-Test-Release)[/bold]\n"
        f"Parametri: Epsilon = {args.epsilon}, Soglia Tau = {args.tau}",
        border_style="yellow"
    ))

    reali, rumorosi, rumori, rilasciati, scartati = applica_dp_ptr(bozze, args.epsilon, args.tau)

    if trace:
        span_dp = trace.span(
            name="dp-ptr-filter",
            input={"raw_counts": reali},
            metadata={
                "epsilon": args.epsilon,
                "tau": args.tau,
                "noise_applied": {k: round(v, 2) for k, v in rumori.items()},
                "noisy_counts": {k: round(v, 2) for k, v in rumorosi.items()}
            }
        )
        span_dp.end(output={
            "released_keywords": rilasciati,
            "filtered_keywords": scartati
        })

    t_ptr = Table(show_header=True)
    t_ptr.add_column("Parola Chiave", style="bold")
    t_ptr.add_column("Freq. Reale", justify="right")
    t_ptr.add_column("Rumore Laplace", justify="right")
    t_ptr.add_column("Totale Rumoroso", justify="right")
    t_ptr.add_column("Esito Filtro Privacy", justify="center")

    tutte_parole = sorted(reali.keys(), key=lambda p: rumorosi[p], reverse=True)
    for p in tutte_parole:
        esito = "[bold green]RILASCIATO (Sicuro)[/bold green]" if p in rilasciati else "[red]SCARTATO (Filtrato)[/red]"
        t_ptr.add_row(
            p,
            str(reali[p]),
            f"{rumori[p]:+.2f}",
            f"{rumorosi[p]:.2f}",
            esito
        )
    console.print(t_ptr)
    console.print(f"\n[bold green]Parole chiave purificate trasmesse al Cloud:[/bold green] {rilasciati}\n")

    # 3. CHIAMATA CLOUD REMOTA
    console.print(Panel("[bold]Fase 3: Trasmissione di Rete e Inferenza Cloud[/bold]", border_style="magenta"))
    
    risp_cloud, tempo_rete_cloud, byte_inviati = chiama_cloud_openai(QUERY_DEFAULT, rilasciati, args.api_key)

    # Confronto con RAG grezzo
    testo_grezzo = "\n".join([d["testo"] for d in DOCUMENTI_LOCALE])
    byte_grezzi = len(testo_grezzo.encode("utf-8"))
    risparmio_rete = ((byte_grezzi - byte_inviati) / byte_grezzi) * 100

    if trace:
        gen_cloud = trace.generation(
            name="cloud-llm-generation",
            model="gpt-4o-mini",
            input={"prompt_with_purified_keywords": f"Query: {QUERY_DEFAULT} [Keywords: {rilasciati}]"},
            metadata={
                "bytes_transmitted": byte_inviati,
                "raw_rag_bytes": byte_grezzi,
                "network_saving_percent": round(risparmio_rete, 1),
                "duration_ms": round(tempo_rete_cloud * 1000, 1)
            }
        )
        gen_cloud.end(output=risp_cloud)
        trace.update(output=risp_cloud)
        lf_client.flush()
        try:
            trace_url = trace.get_trace_url()
            console.print(Panel(
                f"[bold green]Traccia distribuita registrata su Langfuse:[/bold green]\n"
                f"[link={trace_url}]{trace_url}[/link]",
                border_style="cyan"
            ))
        except Exception:
            pass

    t_res = Table(show_header=True)
    t_res.add_column("Metrica di Sistema", style="bold")
    t_res.add_column("Valore Rilevato")
    t_res.add_row("Dati inviati sul canale di rete", f"{byte_inviati} byte (vs {byte_grezzi} byte del RAG grezzo: [bold green]-{risparmio_rete:.1f}%[/bold green])")
    t_res.add_row("Tempo calcolo locale (Hardware M1)", f"{tempo_totale_locale * 1000:.1f} ms")
    t_res.add_row("Tempo rete + inferenza Cloud", f"{tempo_rete_cloud * 1000:.1f} ms" if tempo_rete_cloud > 0 else "Simulato (chiave API non fornita)")
    t_res.add_row("Tempo totale percepito (End-to-End)", f"{(tempo_totale_locale + tempo_rete_cloud) * 1000:.1f} ms")
    console.print(t_res)

    console.print(Panel(
        f"[bold cyan]Risposta Finale Ricevuta dal Cloud:[/bold cyan]\n{risp_cloud}",
        border_style="green"
    ))

if __name__ == "__main__":
    main()
