from datetime import timedelta
from unittest.mock import Mock
import pytest
from backend.app.modules.radar3_institutions.collector import InstitutionsCollector
from backend.app.modules.radar4_policies.collector import PoliciesCollector
from backend.app.modules.radar4_policies.policy import classify
from backend.app.modules.radar3_institutions.institution_policy_source import PolicySourceAdapter, InstitutionSourceAdapter
from backend.app.integrations.http.adapters import SourceDefinition, normalized_item_hash
from backend.app.core.validation import today_in_morocco
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.db.extensions import db
from backend.app.db.models import Result


@pytest.mark.parametrize('title,evidence', [
    ('Avis de recrutement directeur du patrimoine', 'Un directeur sera recrute'),
    ('Bibliotheque historique : memoire du patrimoine', 'Un article sur des siecles de rayonnement culturel'),
    ('Conference patrimoine', 'Le directeur participe a une conference'),
])
def test_weak_institution_content_rejected(app, title, evidence):
    c = InstitutionsCollector(Mock(), app.config)
    assert c._candidate(title, 'https://maroc.ma/x', evidence, 'Agence', today_in_morocco()) is None


def test_unverified_holder_is_not_invented_in_profile(app):
    c = InstitutionsCollector(Mock(), app.config)
    item = c._candidate('Agence urbaine', 'https://alomrane.gov.ma/profile',
        'Mission de planification et de rehabilitation du patrimoine', 'Agence', profile_evidence=True)
    assert item and item.person is None and not item.role_verified
    assert 'Responsable actuel non vérifié' in item.recent_activity


def test_current_official_role_and_role_change_update_one_row(app):
    c = InstitutionsCollector(Mock(), app.config)
    def candidate(role):
        return c._candidate('Nomination patrimoine', 'https://maroc.ma/leader',
            'Fatima Zahra Alaoui a été nommée ' + role + ' du patrimoine', 'Agence', today_in_morocco())
    first = candidate('directrice générale')
    changed = candidate('directrice technique')
    assert first.role_verified and changed.role_verified
    code = 'RADAR_3_INSTITUTIONS'
    assert AgentOrchestrator(app, collector=lambda _: [first], no_ai=True).run_radar(code).new_results_count == 1
    run = AgentOrchestrator(app, collector=lambda _: [changed], no_ai=True).run_radar(code)
    assert run.updated_results_count == 1
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.discovery_status == 'UPDATED' and row.review_status == 'PENDING'
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 1


@pytest.mark.parametrize('title,evidence,expected', [
    ('Projet de loi patrimoine', 'modifie une loi en vigueur', ('DRAFT_LAW','DRAFT')),
    ('Décret n° 2.26.123 relatif au patrimoine', 'Pris pour application de la loi n° 22.80', ('DECREE','POLICY_SIGNAL')),
    ('Projet de décret patrimoine', 'loi en vigueur', ('DECREE','UNDER_PREPARATION')),
    ('Décret patrimoine', 'Pris pour application de la loi en vigueur', ('DECREE','POLICY_SIGNAL')),
    ('Loi patrimoine', 'Texte non adopté', ('LAW','POLICY_SIGNAL')),
    ('Loi réhabilitation fonctionnelle', '', None),
])
def test_status_and_instrument_are_not_inherited_from_citations(title, evidence, expected):
    assert classify(title, evidence) == expected


def test_media_cannot_supply_official_legal_evidence(app):
    c = PoliciesCollector(Mock(), app.config)
    assert c._candidate('Loi urbanisme adoptée','https://example.com/news','Loi en vigueur','Presse') is None


def test_draft_to_adopted_persists_same_law(app):
    c = PoliciesCollector(Mock(), app.config)
    draft = c._candidate('Projet de loi n° 12.34 urbanisme','https://sgg.gov.ma/draft','Projet de loi urbanisme','SGG')
    adopted = c._candidate('Loi n° 12.34 urbanisme adoptée','https://sgg.gov.ma/law','Loi adoptée urbanisme','SGG')
    code='RADAR_4_POLICIES'
    AgentOrchestrator(app,collector=lambda _: [draft],no_ai=True).run_radar(code)
    run=AgentOrchestrator(app,collector=lambda _: [adopted],no_ai=True).run_radar(code)
    assert run.updated_results_count==1
    again=AgentOrchestrator(app,collector=lambda _: [adopted],no_ai=True).run_radar(code)
    assert again.new_results_count==0 and again.duplicate_count==1
    with app.app_context():
        row=db.session.scalar(db.select(Result))
        assert row.review_status=='PENDING'
        assert db.session.scalar(db.select(db.func.count()).select_from(Result))==1


def test_sgg_repeater_preserves_type_and_draft_context():
    a=PolicySourceAdapter(SourceDefinition('SGG','https://sgg.gov.ma/list',parser_type='SGG_DRAFT_TABLE'),('sgg.gov.ma',))
    html='<div class="repeater"><li class=col1><p>Décret</p></li><li><a href="/draft.pdf">Construction et urbanisme : application de la loi 12.34</a></li></div>'
    item=a.list_items(html.encode(),'text/html')[0]
    assert item['draft_listing'] and item['document_type']=='DECREE' and item['url']=='https://sgg.gov.ma/draft.pdf'


def test_institution_profile_hash_tracks_body_changes_ignoring_navigation():
    a=InstitutionSourceAdapter(SourceDefinition('Agence','https://alomrane.gov.ma/profile',parser_type='INSTITUTION_PROFILE'),('alomrane.gov.ma',))
    html='<nav>Avis de recrutement</nav><h1>Agence</h1><p>'+('Mission de patrimoine et amenagement. '*5)+'</p><footer>Contact</footer>'
    first=a.list_items(html.encode(),'text/html')
    assert 'recrutement' not in first[0]['evidence']
    changed=a.list_items(html.replace('patrimoine','urbanisme').encode(),'text/html')
    assert normalized_item_hash(first)!=normalized_item_hash(changed)
