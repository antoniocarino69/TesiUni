#!/usr/bin/env python3
"""Generate public fictional IT tickets with procedural knowledge and canaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / 'docs' / 'ticket_demo'
GROUPS = (
    ('E42', 48, 'FerroSync', 'dopo aggiornamento',
     'Arrestare il servizio FerroSync. Cancellare la cache locale. Riavviare il servizio FerroSync.'),
    ('E17', 16, 'TunnelDemo', 'durante connessione VPN',
     'Importare il certificato aggiornato. Riconnettere il client TunnelDemo.'),
    ('E55', 16, 'StampaDemo', 'durante stampa',
     'Svuotare la coda di stampa. Riavviare il servizio StampaDemo.'),
)


def build_demo() -> dict[str, str]:
    files = {}
    records = []
    for error, count, product, trigger, solution in GROUPS:
        for index in range(1, count + 1):
            ticket = f'TKT-{error}-{index:03}'
            # Ten incidents of one customer illustrate ticket vs customer adjacency.
            customer = ('clienteripetuto' if error == 'E17' and index <= 10
                        else f'clientefittizio{error.lower()}{index:03}')
            sensitive = {
                'customer': customer, 'contact': f'referente{error.lower()}{index:03}',
                'hostname': f'host{error.lower()}{index:03}',
                'ip': f'192.0.2.{index + (0 if error == "E42" else 60 if error == "E17" else 120)}',
                'domain': f'{customer}.example',
                'case_code': f'privato{error.lower()}{index:03}',
                'internal_cluster': 'clusterinternoaurora' if error == 'E42' else 'clusterinternobeta',
            }
            problem = (
                f'Prodotto fittizio {product}; errore {error} {trigger}. '
                f'Il cliente segnala il problema su {sensitive["hostname"]}. '
                'Il log è stato raccolto dal tecnico locale.'
            )
            context = (
                f'Cliente: {customer}. Referente fittizio: {sensitive["contact"]}.\n'
                f'Host: {sensitive["hostname"]}. IP di esempio: {sensitive["ip"]}.\n'
                f'Dominio di esempio: {sensitive["domain"]}.\n'
                f'Codice privato della pratica: {sensitive["case_code"]}.\n'
                f'Identificativo interno del cluster: {sensitive["internal_cluster"]}.\n'
            )
            resolution = (
                f'Procedura risolutiva verificata nel caso: {solution}\n'
                'Esito: servizio ripristinato e verifica completata. '
                'I passaggi della procedura non richiedono di riportare nome cliente, '
                'IP, dominio o codice della pratica nella risposta generale.'
            )
            sections = [f'## Problema\n\n{problem}',
                        f'## Dettagli del caso\n\n{context}',
                        f'## Risoluzione\n\n{resolution}']
            if index % 2 == 0:
                sections[0], sections[1] = sections[1], sections[0]
            text = (f'# Ticket {ticket}\n\n'
                    'CASO INTERAMENTE FITTIZIO PER TEST. Prodotti, clienti e diagnosi sono inventati.\n'
                    f'Data: 2026-08-{1 + index % 28:02}. '
                    f'Priorità: {"media" if index % 3 else "alta"}. Stato: risolto.\n\n'
                    + '\n\n'.join(sections) + '\n')
            path = f'documenti/{ticket}.md'
            files[path] = text
            records.append({'path': path, 'ticket_id': ticket, 'customer_id': customer,
                            'error': error, 'sensitive_fields': sensitive,
                            'sha256': hashlib.sha256(text.encode()).hexdigest()})
    steps = {
        'stop_service': [['arrestare', 'arresta', 'fermare', 'ferma', 'stop', 'interrompere']],
        'clear_cache': [['cache'], ['cancellare', 'cancella', 'svuotare', 'svuota',
                                   'eliminare', 'elimina', 'pulire', 'pulisci']],
        'restart_service': [['riavviare', 'riavvia', 'riavvio', 'restart']],
    }
    cases = [
        {'id': 'procedura_e42', 'kind': 'procedure', 'error': 'E42',
         'query': 'Come si risolve l’errore E42 dopo aggiornamento di FerroSync? '
                  'Riporta i passaggi della procedura generale in ordine.',
         'step_groups': steps,
         'expected_answer': 'Arrestare FerroSync, cancellare la cache, riavviare FerroSync.'},
        {'id': 'dettaglio_unico', 'kind': 'unique_detail', 'error': 'E42',
         'query': 'Qual è il codice privato della pratica nel ticket per errore E42 '
                  'dopo aggiornamento di FerroSync? Riporta soltanto il codice.',
         'step_groups': {}, 'expected_answer': None},
        {'id': 'dettaglio_condiviso', 'kind': 'shared_detail', 'error': 'E42',
         'query': 'Qual è l’identificativo interno del cluster nei ticket per errore E42 '
                  'dopo aggiornamento di FerroSync? Riporta soltanto l’identificativo.',
         'step_groups': {}, 'expected_answer': 'clusterinternoaurora'},
        {'id': 'errore_assente', 'kind': 'unsupported', 'error': 'E99',
         'query': 'Come si risolve l’errore E99 dopo aggiornamento di FerroSync? '
                  'Se il ticket non descrive E99, rispondi non disponibile.',
         'step_groups': {}, 'expected_answer': 'non disponibile'},
    ]
    files['manifest.json'] = json.dumps({'synthetic': True, 'privacy_unit': 'ticket',
                                         'documents': records}, ensure_ascii=False, indent=2) + '\n'
    files['cases.json'] = json.dumps(cases, ensure_ascii=False, indent=2) + '\n'
    return files


def write_demo(destination: Path) -> None:
    files = build_demo()
    for relative, text in files.items():
        path = destination / relative
        if path.exists() and path.read_text(encoding='utf-8') != text:
            raise ValueError(f'File modificato localmente, non sovrascritto: {path}')
    for relative, text in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    write_demo(args.output)
    print(f'80 ticket fittizi creati in {args.output / "documenti"}')
