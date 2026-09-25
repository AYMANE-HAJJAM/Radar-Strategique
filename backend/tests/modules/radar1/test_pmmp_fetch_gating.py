"""PMMP detail fetch is skipped for obvious noise; plausible candidates fetch once."""
from unittest.mock import Mock
from types import SimpleNamespace

from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.modules.radar1_markets.policy import preliminary_plausible
from backend.app.integrations.openai.base import SearchHit


def test_preliminary_rejects_office_supplies_without_detail():
    result = preliminary_plausible('Fournitures de bureau et consommables informatiques')
    assert result['decision'] == 'reject'


def test_plausible_heritage_continues_to_detail():
    result = preliminary_plausible(
        'Études et suivi des travaux de réhabilitation de l’ancienne médina')
    assert result['decision'] == 'continue'


def test_collector_caches_detail_page_per_url():
    reader = Mock()
    page = SimpleNamespace(text='Référence : R1 Objet : Etude médina Acheteur public : Ville '
                                'Date limite : 01/01/2099 Lieu d exécution : Rabat',
                           texts=['Référence : R1', 'Objet : Etude', 'Acheteur public : Ville'],
                           links=[], rows=[], table_rows=[], row_parts=[], row_links=[],
                           headings=[], h1=[], articles=[], has_form=False)
    reader.get.return_value = ('https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1&orgAcronyme=abc', page)
    from backend.app.integrations.http.html import AccessLimitedPages
    metrics = {'http_403': 0, 'http_429': 0}
    pages = AccessLimitedPages(reader, metrics)
    url = 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1&orgAcronyme=abc'
    pages.get(url)
    pages.get(url)
    assert reader.get.call_count == 1
