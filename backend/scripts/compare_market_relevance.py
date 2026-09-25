"""Offline comparison of old/new business gates on the SAME titles; no API or DB."""
import json
from pathlib import Path
from backend.app.modules.radar1_markets.policy import contains, evaluate_relevance


def compare(titles):
    legacy = json.loads(Path('tests/fixtures/legacy_market_keywords.json').read_text(encoding='utf-8'))
    rows = []
    for title in titles:
        old = not any(contains(title, term) for term in legacy['NEGATIVE']) and any(
            contains(title, term) for group, terms in legacy.items() if group != 'NEGATIVE' for term in terms)
        rows.append(dict(title=title, old_kept=old, new=evaluate_relevance(title)))
    return dict(count=len(rows), old_rejected=sum(not row['old_kept'] for row in rows),
                new_rejected=sum(row['new']['decision'] == 'reject' for row in rows),
                new_ambiguous=sum(row['new']['decision'] == 'review' for row in rows),
                priorities={str(p): sum(row['new']['decision'] != 'reject' and row['new']['priority'] == p
                                       for row in rows) for p in (1, 2, 3)}, rows=rows)


if __name__ == '__main__':
    fixtures = json.loads(Path('tests/fixtures/manual_market_relevance.json').read_text(encoding='utf-8'))
    report = {'manual_examples': compare([row['title'] for row in fixtures])}
    for name in ('radar1-collection-final-validation.json', 'radar1-relevance-live.json'):
        if Path(name).exists():
            snapshot = json.loads(Path(name).read_text(encoding='utf-8'))
            titles = list(dict.fromkeys(row['title'] for row in snapshot['run_metadata']['procurement_trace']
                                       if row.get('title')))
            report[name] = compare(titles)
    Path('radar1-relevance-comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, result in report.items():
        print(name, {key: value for key, value in result.items() if key != 'rows'})
