from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar4_policies.service import PoliciesRadarAgent
from backend.app.modules.radar4_policies.collector import PoliciesCollector
from backend.app.modules.radar4_policies.policy import classify
from backend.app.integrations.openai.base import SearchResponse
from backend.app.core.dedup import identity_keys
from backend.app.core.review import ResultWorkflowService

class NoSearch:
    def search(self,*args,**kwargs):return SearchResponse([])
def cfg(app):return {k:v for k,v in app.config.items() if k.startswith('RADAR4_')}

def test_adopted_and_draft_law_statuses_are_distinct():
    assert classify('Loi adoptée relative à l urbanisme')==('LAW','ADOPTED')
    assert classify('Projet de loi adopté annoncé relatif au patrimoine')==('DRAFT_LAW','DRAFT')

def test_policy_study_and_strategy():
    assert classify('Étude stratégique de planification urbaine')==('POLICY_STUDY','POLICY_SIGNAL')
    assert classify('Stratégie en préparation pour le patrimoine')==('STRATEGY','UNDER_PREPARATION')
    assert classify('Projet de décret relatif au patrimoine')==('DECREE','UNDER_PREPARATION')
    assert classify('Projet de loi urbanisme soumis aux commentaires du public')==('DRAFT_LAW','PUBLIC_CONSULTATION')

def test_irrelevant_policy_and_procurement_rejected():
    assert classify('Loi relative à la pêche maritime') is None
    assert classify('Appel d offres pour étude urbaine') is None

def test_direct_official_source_preferred(app):
    collector=PoliciesCollector(NoSearch(),cfg(app))
    official=collector._candidate('Projet de loi urbanisme','https://sgg.gov.ma/x','Projet de loi relatif à l urbanisme','SGG',today_in_morocco())
    secondary=collector._candidate('Projet de loi urbanisme','https://example.com/x','Projet de loi relatif à l urbanisme','Presse',today_in_morocco())
    assert official and official.source_quality=='OFFICIAL_PRIMARY' and secondary is None

def test_draft_to_adopted_is_same_identity_and_meaningful_update(app):
    agent=PoliciesRadarAgent()
    base={'title':'Loi 12.34 relative à l urbanisme','institution':'SGG','url':'https://sgg.gov.ma/x',
          'reference_number':'12.34','reference':'12.34','reliable_status_evidence':True,
          'official_source':'https://sgg.gov.ma/x','status_evidence':'Texte officiel'}
    draft=agent.normalize_candidate({**base,'document_type':'DRAFT_LAW','reported_status':'DRAFT'})
    adopted=agent.normalize_candidate({**base,'document_type':'LAW','reported_status':'ADOPTED'})
    assert identity_keys(draft)[1]==identity_keys(adopted)[1]
    class Existing:
        title=draft.title;institution='SGG';reference='12.34';deadline=None;source_status=None
        radar_metadata=draft.radar_fields()
    assert 'legal_status' in ResultWorkflowService().changed_fields(Existing(),adopted)

def test_deterministic_legal_status_skips_ai(app):
    collector=PoliciesCollector(NoSearch(),cfg(app))
    item=collector._candidate('Loi adoptée urbanisme','https://sgg.gov.ma/x','Loi adoptée relative à l urbanisme','SGG',today_in_morocco())
    decision=PoliciesRadarAgent().validate_candidate(item)
    assert decision.accepted and decision.allow_ai is False
