from datetime import date
from unittest.mock import Mock
import pytest
from backend.app.modules.radar3_institutions.curated_sources import role_items, normalize_role, scoped_page, source_records
from backend.app.modules.radar4_policies.curated_legal import arabic_publication_sections, LEGAL_REGISTRY, HERITAGE_BO
from backend.app.modules.radar3_institutions.leadership import RoleEvidence, resolve, role_valid
from backend.app.modules.radar4_policies.status_verification import reference, publication_evidence, apply_publication
from backend.app.modules.radar4_policies.collector import PoliciesCollector
from backend.app.modules.radar3_institutions.institution_policy_source import PolicySourceAdapter
from backend.app.integrations.http.adapters import SourceDefinition

def html(body,title='Partenariat patrimoine'):
    return f'<nav>12 septembre 2026</nav><h1>{title}</h1>{body}<footer>12 septembre 2026</footer>'.encode()

def test_recent_official_event_extracts_own_role_not_other_signatories():
    items=role_items('fnm',html('13 avril 2026. Ali Test, Président de la Fondation Nationale des Musées ; Autre Personne, Président du Conseil Communal d’Essaouira.'))
    records=items[0]['role_records']
    assert len(records)==1 and records[0]['person_name']=='Ali Test'
    assert records[0]['evidence_date']=='2026-04-13'
    parsed=RoleEvidence(**{**records[0],'evidence_date':date(2026,4,13)})
    assert resolve([parsed],date(2026,9,12))[1]=='VERIFIED_CURRENT'

def test_role_before_name_and_minister_portfolio_are_supported():
    items=role_items('culture',html('16 juillet 2026. Le ministre de la Jeunesse, de la Culture et de la Communication, Ali Test, a signé une convention patrimoine.'))
    record=items[0]['role_records'][0]
    assert record['person_name']=='Ali Test' and role_valid(record['role_title'])
    assert not role_valid('Directeur de la communication')

def test_governance_without_date_never_borrows_navigation_date():
    items=role_items('fnm',html('Ali Test, Président de la Fondation Nationale des Musées.'))
    assert items[0]['date'] is None and items[0]['role_records'][0]['evidence_date'] is None
    assert scoped_page('<nav>12 septembre 2026</nav><p>No article</p>')==('',None)

@pytest.mark.parametrize('title',['Offre de recrutement','Appel à candidature'])
def test_curated_source_still_rejects_recruitment(title):
    assert not role_items('fnm',html('13 avril 2026 Ali Test, Président de la Fondation Nationale des Musées',title))

def test_author_is_not_extracted_as_current_holder():
    item=role_items('fnm',html('13 avril 2026 Auteur : Ali Test, Président de la Fondation Nationale des Musées'))[0]
    assert item['role_records']==[]

def test_no_named_role_remains_unverified():
    item=role_items('fnm',html('La Fondation œuvre à la protection du patrimoine.'))[0]
    assert not item['role_records'] and resolve([],date(2026,9,12))[1]=='UNVERIFIED'

@pytest.mark.parametrize('role,kind',[('Directeur général','DIRECTOR_GENERAL'),('Directrice technique','TECHNICAL_DIRECTOR'),
    ('Directeur de l’urbanisme','URBANISM_DIRECTOR'),('Président','PRESIDENT'),('Secrétaire général','SECRETARY_GENERAL'),
    ('Directeur de programme','PROGRAM_DIRECTOR'),('Chef de projet','PROJECT_DIRECTOR'),
    ('Responsable patrimoine','HERITAGE_MANAGER'),('Responsable partenariats','PARTNERSHIP_MANAGER'),
    ('Responsable marchés','PROCUREMENT_PROJECT_MANAGER'),('Directeur','DIRECTOR'),('Intervenant','' )])
def test_role_normalization_is_conservative(role,kind):assert normalize_role(role)==(kind or None)

@pytest.mark.parametrize('value',['33.22','33 / 22','٣٣٫٢٢','33-22'])
def test_reference_variants(value):assert reference(value)=='33.22'

def test_arabic_promulgation_requires_own_reference_and_subject(app):
    entry=LEGAL_REGISTRY['heritage_33_22']
    text='ينفذ وينشر بالجريدة الرسمية، عقب ظهيرنا الشريف هذا، المتعلق بحماية التراث 33.22القانون رقم'
    sections=list(arabic_publication_sections(text,entry));assert len(sections)==1
    assert not list(arabic_publication_sections(text.replace('33.22','99.99'),entry))
    assert not list(arabic_publication_sections('Rapport citant 33.22 حماية التراث',entry))
    c=PoliciesCollector(Mock(),app.config)
    candidate=c._candidate('Loi n° 33.22 relative à la protection du patrimoine','https://sgg.gov.ma/law','Loi patrimoine','SGG')
    doc={'url':HERITAGE_BO,'date':date(2025,6,23),'bo_number':'7415','text':text,'sections':sections}
    proof=publication_evidence(candidate,[doc],date(2026,9,12))
    published=apply_publication(candidate,proof,date(2026,9,12))
    assert published.legal_status=='PUBLISHED' and published.effective_date is None
    assert published.status_evidence==text and published.bo_number=='7415'

def test_consolidated_index_is_lookup_not_in_force_evidence():
    adapter=PolicySourceAdapter(SourceDefinition('SGG','https://sgg.gov.ma/textesconsolides.aspx',parser_type='SGG_CONSOLIDATED'),['sgg.gov.ma'])
    items=adapter.list_items('<a href="/Portals/1/textesconsolides/12_90.pdf">La loi n° 12-90 relative à l’urbanisme</a>'.encode(),'text/html')
    assert items[0]['consolidated_lookup'] and 'IN_FORCE' not in str(items)

def test_registry_excludes_unreliable_archive_and_keeps_weekly_refresh():
    sources=source_records()
    assert len([s for s in sources if s['enabled']])==4
    assert all(s['refresh_days']==7 for s in sources)
    assert not next(s for s in sources if s['parser_type']=='CURATED_ROLE:apdn')['enabled']

@pytest.mark.parametrize('wording,stage',[('Texte adopté par la Chambre des représentants','CHAMBER_ADOPTED'),
    ('Texte adopté définitivement par les deux chambres','PARLIAMENT_ADOPTED'),
    ('Texte non adopté par la Chambre','PRESENTED'),('Examen en commission','COMMITTEE')])
def test_explicit_parliamentary_stage_is_preserved(wording,stage):
    from backend.app.modules.radar4_policies.legislative_progress import parliament_items
    items=parliament_items(html('13 avril 2026 '+wording,'Projet de loi n° 33/22 relatif au patrimoine'),
        'https://chambredesrepresentants.ma/fr/texte')
    assert items[0]['reference']=='33.22' and items[0]['parliamentary_stage']==stage
    assert 'IN_FORCE' not in str(items)
