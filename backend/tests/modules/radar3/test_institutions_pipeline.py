from datetime import timedelta

from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar3_institutions.service import InstitutionsRadarAgent
from backend.app.modules.radar3_institutions.collector import InstitutionsCollector
from backend.app.modules.radar3_institutions.policy import classify, public_excerpt
from backend.app.integrations.openai.base import SearchResponse
from backend.app.core.dedup import identity_keys
from backend.app.core.review import ResultWorkflowService


class NoSearch:
    def search(self, *args, **kwargs): return SearchResponse([])


def cfg(app): return {key: value for key, value in app.config.items() if key.startswith('RADAR3_')}


def test_relevant_and_irrelevant_institution():
    assert classify('Agence lançant un programme de réhabilitation de médina')['relevant']
    assert not classify('Association organisant un tournoi sportif')['relevant']


def test_current_decision_maker_and_appointment_accepted(app):
    collector = InstitutionsCollector(NoSearch(), cfg(app))
    item = collector._candidate('Nomination patrimoine', 'https://maroc.ma/fr/x',
        'Fatima Zahra Alaoui a été nommée directrice générale du programme de réhabilitation du patrimoine',
        'Agence de développement', today_in_morocco())
    assert item.person == 'Fatima Zahra Alaoui'
    assert item.activity_type == 'NEW_APPOINTMENT' and item.role_verified
    decision = InstitutionsRadarAgent().validate_candidate(item, as_of=today_in_morocco())
    assert decision.accepted and decision.allow_ai is False


def test_recent_official_current_holder_is_verified(app):
    collector = InstitutionsCollector(NoSearch(), cfg(app))
    item = collector._candidate('Conseil de surveillance urbanisme', 'https://alomrane.gov.ma/fr/x',
        'Mme Fatima Zahra El Mansouri a présidé le conseil et est ministre de l urbanisme',
        'Groupe Al Omrane', today_in_morocco())
    assert item.person == 'Fatima Zahra El Mansouri'
    assert item.role_type == 'STRATEGIC_DECISION_MAKER' and item.role_verified


def test_obsolete_role_rejected(app):
    item = InstitutionsRadarAgent().normalize_candidate({'title': 'Ancien directeur patrimoine',
        'institution': 'Agence', 'institution_relevant': True, 'person': 'Ali Test',
        'position': 'Directeur', 'obsolete_holder': True})
    assert not InstitutionsRadarAgent().validate_candidate(item).accepted


def test_duplicate_person_identity_ignores_source_url(app):
    agent = InstitutionsRadarAgent()
    base = {'title': 'Nomination', 'institution': 'Agence', 'institution_relevant': True,
        'person': 'Ali Test', 'position': 'Directeur', 'nomination_unconfirmed': True}
    one = agent.normalize_candidate({**base, 'url': 'https://maroc.ma/a'})
    two = agent.normalize_candidate({**base, 'url': 'https://culture.gov.ma/b'})
    assert identity_keys(one)[1] == identity_keys(two)[1]


def test_role_and_activity_changes_are_meaningful(app):
    class Existing:
        title='Nomination'; institution='Agence'; reference=None; deadline=None; source_status='active'
        radar_metadata={'person':'Ali Test','position':'Chef de projet','institution_name':'Agence','activity_type':'CURRENT_PROFILE'}
    candidate = InstitutionsRadarAgent().normalize_candidate({'title':'Nomination','institution':'Agence',
        'person':'Ali Test','position':'Directeur de projet','institution_relevant':True,
        'activity_type':'NEW_RESPONSIBILITY','nomination_unconfirmed':True})
    changed = ResultWorkflowService().changed_fields(Existing(), candidate)
    assert 'position' in changed and 'activity_type' in changed


def test_private_contact_data_is_not_stored():
    text = public_excerpt('Directrice patrimoine contact test@example.com +212 6 12 34 56 78')
    assert 'example.com' not in text and '+212' not in text


def test_stale_role_not_verified(app):
    collector = InstitutionsCollector(NoSearch(), cfg(app))
    item = collector._candidate('Nomination patrimoine', 'https://maroc.ma/fr/x',
        'Ali Test a été nommé directeur général du patrimoine', 'Agence',
        today_in_morocco() - timedelta(days=181))
    assert item is None


def test_generic_portal_is_not_treated_as_target_institution(app):
    collector = InstitutionsCollector(NoSearch(), cfg(app))
    assert collector._candidate('Patrimoine urbain', 'https://maroc.ma/fr/x',
        'Programme de réhabilitation du patrimoine', 'Maroc.ma - portail officiel du Royaume du Maroc',
        today_in_morocco()) is None
