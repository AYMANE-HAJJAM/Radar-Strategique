"""Run isolated direct-only and normal low-cost validation for every radar."""
import subprocess
import sys
from pathlib import Path

RADARS = ('RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS',
          'RADAR_4_POLICIES', 'RADAR_5_FUNDING')


def main():
    output = Path('audit-output')
    output.mkdir(exist_ok=True)
    failures = []
    for mode, flags in (('direct-only', ('--direct-only',)), ('low-cost', ())):
        for index, radar in enumerate(RADARS, 1):
            report = output / f'{mode}-radar{index}.json'
            command = [sys.executable, '-m', 'scripts.run_live_radar', radar, '--isolated', '--dry-run',
                       *flags, '--report-json', str(report)]
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (output / f'{mode}-radar{index}-console.txt').write_text(result.stdout, encoding='utf-8')
            print(f'{mode} {radar}: exit={result.returncode}', flush=True)
            if result.returncode not in {0, 2}:
                failures.append((mode, radar, result.returncode))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
