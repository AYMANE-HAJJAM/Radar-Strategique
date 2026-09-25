from datetime import timedelta

from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar2_projects.service import ProjectsRadarAgent
from backend.app.modules.radar2_projects.collector import ProjectsCollector
from backend.app.modules.radar2_projects.policy import classify_signal
from backend.app.integrations.openai.base import SearchResponse


class NoSearch:
    def search(self, *args, **kwargs):
        return SearchResponse([], None, 'test')


def config(app, **updates):
    values = {key: value for key, value in app.config.items() if key.startswith('RADAR2_')}
    values.update(updates)
    return values


def facts(text, days=0):
    return classify_signal(text, text, today_in_morocco() - timedelta(days=days))


def test_concrete_announcement_convention_financing_and_study_are_accepted():
    assert facts('Projet annoncé de réhabilitation de la médina')['signal_type'] == 'PROJECT_ANNOUNCED'
    assert facts('Convention signée pour un programme d’aménagement urbain')['signal_type'] == 'CONVENTION_SIGNED'
    assert facts('Financement approuvé pour la restauration du monument')['maturity'] == 'A'
    assert facts('Étude préalable pour un espace public')['signal_type'] == 'FEASIBILITY_PREPARATION'


def test_vague_completed_and_unrelated_signals_are_rejected():
    assert facts('Discours qui a souligné l importance du patrimoine')['rejection'] == 'vague'
    assert facts('Projet de restauration inauguré et travaux achevés')['rejection'] == 'completed'
    assert facts('Financement approuvé pour une autoroute')['rejection'] == 'irrelevant'


def test_old_project_requires_recent_concrete_update():
    assert facts('Projet annoncé de réhabilitation du patrimoine', 120)['rejection'] == 'old'
    assert facts('Nouvelle phase: convention signée pour la réhabilitation du patrimoine', 120)['rejection'] is None


def test_multi_project_article_is_split_and_deduplicated(app):
    collector = ProjectsCollector(NoSearch(), config(app))
    text = ('Projet annoncé de réhabilitation de la médina de Fès.\n'
            'Convention signée pour l’aménagement urbain de la place centrale.')
    rows = collector.extract_candidates(title='Deux projets', url='https://maroc.ma/fr/x', evidence=text,
                                        publication_date=today_in_morocco())
    assert len(rows) == 2
    collector._add(rows[0]); collector._add(rows[0])
    assert collector.report.metrics['duplicates'] == 1


def test_official_preferred_and_secondary_fallback(app):
    collector = ProjectsCollector(NoSearch(), config(app))
    official = collector._candidate(title='Projet annoncé de restauration du patrimoine',
        url='https://maroc.ma/fr/projet', evidence='Projet annoncé de restauration du patrimoine',
        publication_date=today_in_morocco())
    secondary = collector._candidate(title='Projet annoncé de restauration du patrimoine à Meknès',
        url='https://mapnews.ma/fr/projet', evidence='Projet annoncé de restauration du patrimoine à Meknès',
        publication_date=today_in_morocco())
    assert official.official_url and official.source_quality == 'OFFICIAL_PRIMARY'
    assert secondary.official_url is None and secondary.source_quality == 'RELIABLE_SECONDARY'


def test_high_confidence_project_skips_ai(app):
    agent = ProjectsRadarAgent()
    candidate = agent.normalize_candidate({'title': 'Convention signée pour la réhabilitation de la médina',
        'url': 'https://maroc.ma/fr/project', 'source': 'maroc.ma', 'source_quality': 'OFFICIAL_PRIMARY',
        'publication_date': today_in_morocco(), 'signal_type': 'CONVENTION_SIGNED',
        'signal_evidence': 'Convention signée pour la réhabilitation de la médina'})
    decision = agent.validate_candidate(candidate, as_of=today_in_morocco())
    assert decision.accepted and decision.allow_ai is False


def test_project_meaningful_update_fields(app):
    from backend.app.core.review import ResultWorkflowService
    class Existing:
        title = 'Projet'; institution = 'Région'; reference = None; deadline = None; source_status = 'active'
        radar_metadata = {'signal_type': 'PROJECT_ANNOUNCED', 'maturity': 'B', 'project_name': 'Projet'}
    candidate = ProjectsRadarAgent().normalize_candidate({'title': 'Projet', 'institution': 'Région',
        'url': 'https://maroc.ma/fr/project', 'source_status': 'active', 'signal_type': 'FINANCING_APPROVED',
        'maturity': 'A', 'publication_date': today_in_morocco(), 'signal_evidence': 'Financement approuvé pour la réhabilitation'})
    assert 'signal_type' in ResultWorkflowService().changed_fields(Existing(), candidate)
