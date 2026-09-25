from datetime import date,timedelta
from unittest.mock import Mock
import pytest
from backend.app.modules.radar3_institutions.leadership import RoleEvidence, resolve, extract, role_valid
from backend.app.modules.radar3_institutions.collector import InstitutionsCollector
from backend.app.modules.radar4_policies.collector import PoliciesCollector
from backend.app.modules.radar4_policies.status_verification import publication_evidence, apply_publication
from backend.app.modules.radar4_policies.policy import classify
from backend.app.modules.radar4_policies.service import PoliciesRadarAgent
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.validation import today_in_morocco
from backend.app.db.extensions import db
from backend.app.db.models import Result

TODAY=date(2026,9,12)

def test_bo_publication_uses_morocco_calendar_date():
    import json
    from backend.app.integrations.http.adapters import SourceDefinition
    from backend.app.modules.radar3_institutions.institution_policy_source import PolicySourceAdapter
    adapter=PolicySourceAdapter(SourceDefinition('BO','https://sgg.gov.ma/list',parser_type='BO_PUBLICATIONS'),['sgg.gov.ma'])
    rows=[{'BoDate':'/Date(1784156400000)/','BoNum':'7526','BoUrl':'/BO/FR/2873/2026/BO_7526_Fr.pdf'},
          {'BoDate':'/Date(-1804032000000)/','BoNum':'1','BoUrl':'/BO/bo_fr/1912/bo_1_fr.pdf'}]
    items=adapter.list_items(json.dumps(rows).encode(),'application/json')
    assert items[0]['date']=='2026-07-16' and items[0]['reference']=='7526'
    assert items[1]['date'].startswith('1912-')

def test_confirmed_role_flag_cannot_bypass_missing_evidence(app):
    from backend.app.modules.radar3_institutions.validators import validate
    c=InstitutionsCollector(Mock(),app.config)
    base=c._candidate('Agence urbaine','https://alomrane.gov.ma/profile','Mission de patrimoine et urbanisme','Agence urbaine',profile_evidence=True)
    item=c.apply_leadership(base,[role(days=None,kind='GOVERNANCE')])
    decision=validate(item.model_copy(update={'current_status':'VERIFIED_CURRENT'}),TODAY)
    assert 'current_role_evidence_missing_or_stale' in decision.reasons
def role(name='Ali Test',days=1,kind='OFFICIAL_RELEASE',departed=False):
    return RoleEvidence(name,'Directeur général','Agence urbaine','https://maroc.ma/official',kind,
        None if days is None else TODAY-timedelta(days=days),'Programme officiel urbanisme',departed)

def test_recent_official_appointment_and_obsolete_holder():
    assert resolve([role(kind='APPOINTMENT')],TODAY)[1]=='VERIFIED_CURRENT'
    assert resolve([role(days=500)],TODAY)[1]=='OBSOLETE'
    assert resolve([role(departed=True)],TODAY)[1]=='OBSOLETE'

def test_newest_official_holder_wins_over_old_static_and_old_appointment():
    winner,status=resolve([role('Old Holder',days=None,kind='GOVERNANCE'),role('Old Holder',days=400),role('New Holder')],TODAY)
    assert status=='VERIFIED_CURRENT' and winner.person_name=='New Holder'

def test_undated_governance_needs_recent_crosscheck():
    assert resolve([role(days=None,kind='GOVERNANCE')],TODAY)[1]=='PROBABLY_CURRENT'
    assert resolve([role(days=None,kind='GOVERNANCE'),role()],TODAY)[1]=='VERIFIED_CURRENT'
    assert resolve([role('Ali Test'),role('Other Holder')],TODAY)[1]=='UNVERIFIED'

@pytest.mark.parametrize('value',['journaliste','auteur','directeur communication','contact recrutement','ancien directeur','intervenant'])
def test_invalid_roles_cannot_be_confirmed(value):assert not role_valid(value)

def test_article_author_and_recruitment_contact_not_extracted():
    for text in ['Auteur : Ali Test, Directeur général du patrimoine','Contact presse recrutement : Ali Test, Directeur général']:
        assert not extract(text,'Agence','https://maroc.ma/x','OFFICIAL_RELEASE',TODAY)

def test_interim_appointment_extracted():
    found=extract('Ali Test a été nommé Directeur général par intérim du programme patrimoine','Agence','https://maroc.ma/x','APPOINTMENT',TODAY)
    assert found and found[0].interim

def test_replacement_updates_institution_without_dedup_changes(app):
    c=InstitutionsCollector(Mock(),app.config)
    base=c._candidate('Agence urbaine','https://alomrane.gov.ma/profile','Mission de patrimoine et urbanisme','Agence urbaine',profile_evidence=True)
    a=c.apply_leadership(base,[role('Old Holder',days=10)])
    b=c.apply_leadership(base,[role('Old Holder',days=10),role('New Holder')])
    code='RADAR_3_INSTITUTIONS'
    first=AgentOrchestrator(app,collector=lambda _: [a],no_ai=True).run_radar(code)
    second=AgentOrchestrator(app,collector=lambda _: [b],no_ai=True).run_radar(code)
    assert first.new_results_count==1 and second.updated_results_count==1
    with app.app_context():
        row=db.session.scalar(db.select(Result));assert row.review_status=='PENDING'
        assert row.radar_metadata['person_name']=='New Holder'
        assert 'Old Holder' not in str(row.radar_metadata['decision_makers'])
        assert db.session.scalar(db.select(db.func.count()).select_from(Result))==1

def policy(app,status='DRAFT'):
    c=PoliciesCollector(Mock(),app.config)
    return c._candidate('Projet de loi n° 12.34 urbanisme','https://sgg.gov.ma/draft','Projet de loi urbanisme','SGG').model_copy(update={'legal_status':status,'reported_status':status})

def bulletin(text=None,url='https://sgg.gov.ma/BO/2026/BO_7000_Fr.pdf'):
    return {'url':url,'date':date(2026,1,1),'bo_number':'7000','text':text or 'Dahir n° 1.26.1 portant promulgation de la loi n° 12.34 relative à l urbanisme\nArticle premier. Texte officiel.'}

def test_draft_without_publication_stays_draft(app):
    item=policy(app);assert publication_evidence(item,[],TODAY) is None
    assert apply_publication(item,None,TODAY).legal_status=='DRAFT'

def test_parliamentary_approval_not_effectiveness(app):
    c=PoliciesCollector(Mock(),app.config)
    item=c._candidate('Loi urbanisme adoptée','https://parlement.ma/law','Loi adoptée au parlement','SGG')
    assert item.legal_status=='ADOPTED' and not item.publication_verified

def test_publication_is_not_effectiveness(app):
    item=policy(app);proof=publication_evidence(item,[bulletin()],TODAY)
    published=apply_publication(item,proof,TODAY)
    assert published.legal_status=='PUBLISHED' and published.publication_verified and published.effective_date is None
    assert PoliciesRadarAgent().validate_candidate(published).allow_ai is False

def test_only_own_effective_clause_and_date_allow_in_force(app):
    item=policy(app)
    doc=bulletin(bulletin()['text']+'\nLa présente loi entre en vigueur le 1 janvier 2026.')
    assert publication_evidence(item,[doc],TODAY)['status']=='IN_FORCE'
    doc=bulletin(bulletin()['text']+'\nLa présente loi entrera en vigueur le 1 janvier 2027.')
    assert publication_evidence(item,[doc],TODAY)['status']=='PUBLISHED'

def test_media_and_incidental_references_cannot_verify_publication(app):
    item=policy(app)
    assert publication_evidence(item,[bulletin(url='https://example.com/BO/news.pdf')],TODAY) is None
    assert publication_evidence(item,[bulletin('Rapport de contrôle : conformément à la loi n° 12.34 urbanisme en vigueur.')],TODAY) is None

def test_legal_lifecycle_uses_existing_identity_and_reopens_review(app):
    item=policy(app);published=apply_publication(item,publication_evidence(item,[bulletin()],TODAY),TODAY)
    adopted=item.model_copy(update={'document_type':'LAW','legal_status':'ADOPTED','reported_status':'ADOPTED'})
    force=apply_publication(item,publication_evidence(item,[bulletin(bulletin()['text']+'\nLa présente loi entre en vigueur le 1 janvier 2026.')],TODAY),TODAY)
    code='RADAR_4_POLICIES'
    for index,candidate in enumerate([item,adopted,published,force]):
        run=AgentOrchestrator(app,collector=lambda _: [candidate],no_ai=True).run_radar(code)
        assert (run.new_results_count if index==0 else run.updated_results_count)==1
    again=AgentOrchestrator(app,collector=lambda _: [force],no_ai=True).run_radar(code)
    assert again.new_results_count==0 and again.duplicate_count==1
    with app.app_context():assert db.session.scalar(db.select(db.func.count()).select_from(Result))==1

def test_strategy_status_is_separate_and_unrelated_law_rejected():
    assert classify('Stratégie annoncée pour le patrimoine')==('STRATEGY','ANNOUNCED')
    assert classify('Stratégie patrimoine mise en oeuvre')==('STRATEGY','IMPLEMENTATION')
    assert classify('Loi relative aux médicaments') is None
