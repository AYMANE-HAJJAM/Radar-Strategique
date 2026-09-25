"""Run isolated optimized normal and no-AI comparisons; never touch configured data."""
import json
import subprocess
import sys
from pathlib import Path

CODES = (
    'RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS',
    'RADAR_4_POLICIES', 'RADAR_5_FUNDING',
)


def run(label, extra=()):
    for number, code in enumerate(CODES, 1):
        report = Path('audit-output') / f'{label}-radar{number}.json'
        console = Path('audit-output') / f'{label}-radar{number}-console.txt'
        command = [sys.executable, '-m', 'scripts.run_live_radar', code, '--isolated',
                   '--report-json', str(report), *extra]
        with console.open('w', encoding='utf-8') as output:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
        print(f'{label} {code}: exit={completed.returncode}', flush=True)


def main():
    Path('audit-output').mkdir(exist_ok=True)
    run('optimized')
    run('no-ai', ('--no-ai',))


if __name__ == '__main__':
    main()
