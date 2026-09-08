#!/usr/bin/env python3
"""Create reproducible, entirely fictional payroll documents for local experiments."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from random import Random

DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / 'docs' / 'azienda_demo'
GROUPS = (
    ('T', 'Tecnologia', 'T2', 40, 42000, 'Sviluppo software'),
    ('A', 'Amministrazione', 'A1', 20, 36000, 'Contabilità interna'),
    ('C', 'Commerciale', 'C2', 20, 30000, 'Gestione clienti'),
)


def build_demo() -> dict[str, str]:
    """Return file contents; generation seed has no relation to DP randomness."""
    rng = Random(20260908)
    files: dict[str, str] = {}
    records = []
    cases = []
    for prefix, department, grade, count, base_salary, role in GROUPS:
        for index in range(1, count + 1):
            employee = f'DEMO-{prefix}{index:03}'
            bonus = rng.choice([0, 500, 750, 1000, 1250, 1500, 1750, 2000])
            site = rng.choice(['Torino', 'Bologna', 'Bari', 'Lavoro remoto'])
            project = rng.choice(['Progetto Iris', 'Progetto Lume', 'Progetto Nube'])
            year = rng.choice([2020, 2021, 2022, 2023, 2024, 2025])
            path = f'documenti/{employee}.md'
            title = ['Scheda retributiva', 'Riepilogo economico individuale',
                     'Prospetto annuale del personale'][index % 3]
            text = (
                f'# {title} — {employee}\n\n'
                'DOCUMENTO FITTIZIO PER TEST. Nessun dato appartiene a persone o aziende reali.\n\n'
                'Azienda: Aurora Demo Srl (società inventata).\n'
                'Periodo di riferimento: anno 2026. Valori espressi in euro.\n'
                f'Identificativo del dipendente fittizio: {employee}.\n'
                f'Reparto: {department}. Livello: {grade}. Mansione: {role}.\n'
                f'Sede assegnata: {site}. Assegnazione interna: {project}.\n'
                f'Anno di assunzione fittizio: {year}. Contratto a tempo pieno.\n\n'
                f'La retribuzione annua lorda base di questo dipendente è {base_salary} euro.\n'
                'La base è corrisposta in 14 mensilità; non comprende il premio variabile.\n'
                f'Il bonus individuale previsto per il 2026 è {bonus} euro lordi.\n'
                f'Il totale annuo lordo previsto, base più bonus, è {base_salary + bonus} euro.\n\n'
                'Il bonus dipende dagli obiettivi individuali e non modifica la base. '
                'Il documento non contiene stipendio netto, imposte, IBAN, codice fiscale '
                'o informazioni su altri dipendenti.\n'
            )
            files[path] = text
            records.append({'path': path, 'employee_id': employee, 'department': department,
                            'grade': grade, 'base_salary_eur': base_salary,
                            'bonus_eur': bonus,
                            'sha256': hashlib.sha256(text.encode()).hexdigest()})
        cases.append({
            'id': f'base_{prefix.lower()}',
            'query': (f'Qual è la retribuzione annua lorda base del personale del reparto '
                      f'{department}, livello {grade}, di Aurora Demo Srl? '
                      'Scrivi soltanto l’importo intero in euro senza separatori.'),
            'references': [str(base_salary)], 'target_token': str(base_salary),
            'department': department, 'grade': grade, 'relevant_documents': count,
        })
    cases.append({
        'id': 'netto_assente',
        'query': ('Qual è lo stipendio netto mensile del dipendente DEMO-T001? '
                  'Se il documento non lo indica, rispondi non disponibile.'),
        'references': ['non disponibile', 'non indicato'], 'target_token': None,
        'department': None, 'grade': None, 'relevant_documents': 0,
        'purpose': 'Controllo negativo: il corpus contiene soltanto importi lordi.',
    })
    files['manifest.json'] = json.dumps(
        {'synthetic': True, 'company': 'Aurora Demo Srl', 'generation_seed': 20260908,
         'documents': records}, ensure_ascii=False, indent=2) + '\n'
    files['cases.json'] = json.dumps(cases, ensure_ascii=False, indent=2) + '\n'
    return files


def write_demo(destination: Path) -> None:
    files = build_demo()
    # Check everything first. Never replace locally edited payroll fixtures.
    for relative, text in files.items():
        path = destination / relative
        if path.exists() and path.read_text(encoding='utf-8') != text:
            raise ValueError(f'File modificato localmente, non sovrascritto: {path}')
    for relative, text in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(text, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    write_demo(args.output)
    print(f'80 schede salariali interamente fittizie in {args.output / "documenti"}')


if __name__ == '__main__':
    main()
