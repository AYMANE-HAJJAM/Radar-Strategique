"""Replay a saved live Radar 1 snapshot: no DB, network, AI or messages."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.modules.radar1_markets.policy import evaluate_relevance


def walk(value):
    if isinstance(value, dict):
        if value.get('title') and 'business_relevance' in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main():
    source = Path('radar1-architecture-scope-live.json')
    rows = {}
    for row in walk(json.loads(source.read_text(encoding='utf-8'))):
        key = (row.get('reference'), row['title'])
        rows.setdefault(key, row)
    compared = [dict(title=row['title'], reference=row.get('reference'),
        previous=row['business_relevance'], current=evaluate_relevance(row['title']))
        for row in rows.values()]
    previous = [r for r in compared if r['previous']['decision'] != 'reject']
    report = dict(mode='isolated_saved_live_replay', source=str(source),
        unique_observations=len(compared), previously_eligible=len(previous),
        previously_eligible_now_rejected=sum(r['current']['decision'] == 'reject' for r in previous),
        p1=sum(r['current']['decision'] == 'keep' for r in compared),
        p2=sum(r['current']['decision'] == 'review' for r in compared),
        paid_calls=0, production_writes=0, telegram_messages=0, records=compared)
    output = Path('audit-output/radar1-heritage-comparison.json')
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'records'}, indent=2))


if __name__ == '__main__':
    main()
