"""Summarize persisted radar usage without making network calls."""
from collections import defaultdict

from backend.app import create_app
from backend.app.db.extensions import db
from backend.app.db.models import Radar, SearchRun


def main():
    app = create_app()
    with app.app_context():
        rows = db.session.execute(db.select(SearchRun, Radar.code).join(Radar)).all()
        totals = defaultdict(lambda: defaultdict(int))
        runs = defaultdict(int)
        for run, code in rows:
            runs[code] += 1
            for field in ('direct_fetches', 'search_calls', 'resolution_search_calls', 'ai_calls',
                          'input_tokens', 'output_tokens', 'new_results_count', 'updated_results_count'):
                totals[code][field] += getattr(run, field) or 0
        for code in sorted(totals):
            useful = totals[code]['new_results_count'] + totals[code]['updated_results_count']
            paid = totals[code]['search_calls']
            ratio = round(useful / paid, 2) if paid else None
            print(dict(radar=code, runs=runs[code], **totals[code], useful_per_paid_call=ratio))


if __name__ == '__main__':
    main()
