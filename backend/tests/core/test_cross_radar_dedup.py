from datetime import timedelta

from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.modules.radar2_projects.service import ProjectsRadarAgent
from backend.app.modules.radar3_institutions.service import InstitutionsRadarAgent
from backend.app.modules.radar4_policies.service import PoliciesRadarAgent
from backend.app.modules.radar5_funding.service import FundingRadarAgent
from backend.app.core.validation import today_in_morocco
from backend.app.db.extensions import db
from backend.app.db.models import Result, ResultObservation, utcnow
from backend.app.core.review import ResultWorkflowService, ReviewStatus


URL = 'https://example.org/medina-program'
TEXT = 'Programme de rehabilitation de la medina finance par la Banque mondiale.'


def candidates(url=URL, text=TEXT):
    today = today_in_morocco()
    project = ProjectsRadarAgent().normalize_candidate({
        'title': text, 'url': url, 'source': 'official', 'institution': 'Region',
        'publication_date': today, 'raw_text': text, 'source_quality': 'OFFICIAL_PRIMARY',
        'signal_type': 'FINANCING_APPROVED', 'maturity': 'A', 'project_scope': TEXT,
        'signal_evidence': TEXT, 'financing_secured': True,
    })
    institution = InstitutionsRadarAgent().normalize_candidate({
        'title': text, 'url': url, 'source': 'official', 'institution': 'Region',
        'publication_date': today, 'raw_text': text, 'source_quality': 'OFFICIAL_PRIMARY',
        'institution_relevant': True, 'official_source': url, 'recent_activity': TEXT,
        'recent_activity_date': today, 'mission': 'Developpement territorial et patrimoine',
    })
    policy = PoliciesRadarAgent().normalize_candidate({
        'title': text, 'url': url, 'source': 'official', 'institution': 'Region',
        'publication_date': today, 'raw_text': text, 'source_quality': 'OFFICIAL_PRIMARY',
        'document_type': 'program', 'reported_status': 'implementation',
        'status_evidence': TEXT, 'official_source': url, 'reliable_status_evidence': True,
        'scope': TEXT, 'business_implications': TEXT,
    })
    funding = FundingRadarAgent().normalize_candidate({
        'title': text, 'url': url, 'source': 'official', 'institution': 'Region',
        'publication_date': today, 'raw_text': text, 'source_quality': 'OFFICIAL_PRIMARY',
        'funder': 'World Bank', 'program_name': 'Programme Medina', 'morocco_related': True,
        'reported_funding_status': 'active', 'access_mode_evidence': 'future_procurement',
        'beneficiary': 'Region', 'summary': text, 'business_relevance': text,
    })
    return project, institution, policy, funding


def run(app, code, candidate):
    return AgentOrchestrator(app, collector=lambda _: [candidate]).run_radar(code)


def test_same_article_four_radars_has_one_visible_owner_and_all_extractions(app):
    rows = candidates()
    codes = ('RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
    summaries = [run(app, code, candidate) for code, candidate in zip(codes, rows)]
    assert summaries[0].new_results_count == 1
    assert [summary.new_results_count for summary in summaries[1:]] == [0, 0, 0]
    assert [summary.run_metadata['cross_radar_dedup']['reused_without_ai'] for summary in summaries[1:]] == [1, 1, 1]
    with app.app_context():
        stored = db.session.scalars(db.select(Result)).all()
        assert len(stored) == 1
        global_source = stored[0].radar_metadata['global_source']
        assert global_source['first_seen_radar'] == 'RADAR_2_PROJECTS'
        assert global_source['related_radars'] == list(codes)
        assert set(global_source['radar_extractions']) == set(codes)
        assert db.session.scalar(db.select(db.func.count(ResultObservation.id))) == 4


def test_tracking_urls_and_mirrored_title_collapse_globally(app):
    first, second, *_ = candidates(url=URL + '?utm_source=x')
    second = second.model_copy(update={'url': URL + '?utm_campaign=y',
        'title': '  PROGRAMME DE REHABILITATION DE LA MEDINA, FINANCE PAR LA BANQUE MONDIALE! '})
    run(app, 'RADAR_2_PROJECTS', first)
    summary = run(app, 'RADAR_3_INSTITUTIONS', second)
    assert summary.new_results_count == 0 and summary.duplicate_count == 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Result.id))) == 1


def test_different_event_about_same_project_is_preserved(app):
    first, *_ = candidates(url='https://example.org/project-announced',
        text='Projet de rehabilitation de la medina officiellement annonce.')
    *_, second = candidates(url='https://example.org/financing-signed',
        text='Financement de 80 millions signe pour la rehabilitation de la medina.')
    run(app, 'RADAR_2_PROJECTS', first)
    summary = run(app, 'RADAR_5_FUNDING', second)
    assert summary.new_results_count == 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Result.id))) == 2


def test_same_page_material_update_reopens_owner_but_duplicate_does_not(app):
    first, _, _, duplicate = candidates()
    run(app, 'RADAR_2_PROJECTS', first)
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        ResultWorkflowService().apply_human_decision(row, 'approved', 7,
            utcnow(), None, 'RADAR_2_PROJECTS')
        db.session.commit()
    unchanged = run(app, 'RADAR_5_FUNDING', duplicate)
    assert unchanged.updated_results_count == 0
    with app.app_context():
        assert db.session.scalar(db.select(Result)).review_status == ReviewStatus.APPROVED
    *_, changed = candidates(text=TEXT + ' Le financement de 80 millions est desormais signe.')
    update = run(app, 'RADAR_5_FUNDING', changed)
    assert update.updated_results_count == 1 and update.new_results_count == 0
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.review_status == ReviewStatus.PENDING
        assert row.update_reason == {'changed_fields': ['source_content']}
