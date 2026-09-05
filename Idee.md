
Privacy differenziale...time to first token comparando i modelli e rapportandoli all'effettiva efficienza e promt enginering...che c'entra con architetture di reti e calcolatori? promtare e vedere

# idea 1

Proposta di Tesi di Laurea  
Titolo provvisorio: _Architetture Ibride Edge-Cloud per Sistemi RAG: Mitigazione del Data Leakage tramite Privacy Differenziale su Dispositivi Consumer Eterogenei._  
1. Contesto e Motivazione  
L'integrazione di sistemi di _Retrieval-Augmented Generation_ (RAG) direttamente su dispositivi edge (es. tramite database vettoriali locali leggeri) è un trend in rapida crescita per la gestione di documenti sensibili aziendali o personali. Tuttavia, i limiti computazionali dell'hardware consumer rendono spesso necessario delegare l'inferenza complessa a Large Language Models (LLM) ospitati in Cloud tramite API. Questo passaggio espone il sistema a un grave rischio di _data leakage_, in quanto i contesti recuperati localmente verrebbero trasmessi in chiaro a un provider di terze parti (l'attore ostile/non fidato).  
2. Modello di Minaccia (Threat Model) e Soluzione Proposta  
A differenza della letteratura standard in cui l'attore ostile è l'utente finale del dispositivo, questo studio sposta l'attore ostile "a monte", identificandolo nel provider Cloud dell'API di generazione.  
Per tutelare i dati locali prima della trasmissione, si propone un'architettura ibrida basata sul framework DP-KSA (Differentially Private Keyword-based Semantic Augmentation). Il sistema delega a uno _Small Language Model_ (SLM) locale il compito di:  

- Generare un _ensemble_ di risposte preliminari basate sui documenti recuperati.  
    
- Applicare il paradigma _Propose-Test-Release_ (PTR) per estrarre un sottoinsieme di parole chiave (keyword) garantite matematicamente dalla Privacy Differenziale (‭

$\epsilon$

‬-DP).  
Le keyword "purificate" e il prompt originale vengono poi inviati all'API Cloud per la generazione finale _zero-shot_, preservando l'utilità semantica ma annullando il rischio di compromissione dei documenti sorgente.  

3. Analisi Architetturale e Metodologia di Test  
L'applicazione della DP sull'edge introduce un severo overhead computazionale (legato alla generazione locale degli _ensemble_). Il cuore della tesi consisterà nel valutare l'impatto di questo carico di lavoro misurando il parametro TTFT (Time To First Token).  
I test empirici verranno condotti utilizzando modelli SLM quantizzati (es. Qwen 2.5 3B o Llama 3.2 3B) per confrontare due paradigmi architetturali _mobile_ diametralmente opposti:  

- **Architettura x86 + dGPU:** Nvidia RTX 2070 Super Mobile (8GB VRAM dedicata, raffreddamento attivo, alti consumi).  
    
- **Architettura SoC ARM:** Apple Silicon M1 (8GB Memoria Unificata, raffreddamento passivo _fanless_, alta efficienza).  
    

L'obiettivo scientifico è misurare il degrado del TTFT e le dinamiche di ottimizzazione in condizioni di risorse fortemente vincolate (limiti dei 5GB operativi di memoria unificata su Mac, frammentazione della memoria su PC) e documentare gli effetti del _thermal throttling_ durante l'esecuzione sequenziale degli _ensemble_ necessari per la validazione PTR.  
Questo documento copre esattamente l'idea originale, dimostra che hai una base di partenza solida supportata da letteratura recente e chiarisce quale sarà il tuo personale apporto sperimentale legato all'hardware.