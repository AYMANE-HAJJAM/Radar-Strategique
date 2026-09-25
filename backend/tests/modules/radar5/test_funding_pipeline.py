from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar5_funding.service import FundingRadarAgent
from backend.app.modules.radar5_funding.collector import FundingCollector
from backend.app.modules.radar5_funding.policy import classify
from backend.app.integrations.openai.base import SearchResponse
from backend.app.core.dedup import identity_keys
from backend.app.core.review import ResultWorkflowService
class NoSearch:
    def search(self,*a,**k):return SearchResponse([])
def cfg(app):return {k:v for k,v in app.config.items() if k.startswith('RADAR5_')}

def test_world_bank_afdb_and_eib_morocco_programs():
    assert classify('World Bank approved Morocco urban development program')[1]=='B'
    assert classify('AfDB Morocco territorial development project in preparation')[1]=='C'
    assert classify('EIB active Morocco cultural infrastructure financing')[1]=='B'

def test_unrelated_country_rejected():
    assert classify('World Bank Tunisia urban development program') is None

def test_active_pipeline_and_access_models():
    assert classify('Morocco urban development approved financing')[1]=='B'
    assert classify('Morocco urban regeneration concept note')[1:] == ('C','PROJECT_PIPELINE')
    assert classify('Morocco heritage consulting services consultant opportunity')[2]=='CONSULTANT_OPPORTUNITY'
    assert classify('Morocco urban procurement plan for beneficiary')[2]=='BENEFICIARY_PROCUREMENT'
    assert classify('Morocco urban framework is a strategic pipeline/framework, not a specific grant, tender, or open call') == ('pipeline','D','PROJECT_PIPELINE')
    assert classify('Active Morocco territorial program does not establish a new financing call, consultant opportunity, or direct eligibility')[2]=='MONITORING_ONLY'

def test_direct_access_requires_explicit_eligibility(app):
    c=FundingCollector(NoSearch(),cfg(app))
    direct=c._candidate('Heritage grant Morocco','https://worldbank.org/x','Open call: Moroccan associations are eligible and can apply for heritage grant','Beneficiary',today_in_morocco())
    vague=c._candidate('Heritage grant Morocco','https://worldbank.org/y','A grant supports Morocco heritage','Beneficiary',today_in_morocco())
    assert direct.opportunity_type=='DIRECT_ACCESS' and direct.direct_eligibility_confirmed
    assert vague.opportunity_type in {'GRANT','MONITORING_ONLY'} and not vague.direct_eligibility_confirmed
    financed=c._candidate('Morocco urban financing','https://afdb.org/x','AfDB approved €150 million for Morocco urban development','FEC',today_in_morocco())
    assert financed.amount==150_000_000 and financed.currency=='EUR'

def test_procurement_plan_update_and_dedup(app):
    agent=FundingRadarAgent();base={'title':'Morocco Urban Program','program_name':'Morocco Urban Program','funder':'World Bank',
        'url':'https://worldbank.org/x','morocco_related':True,'reported_funding_status':'active','beneficiary':'Commune'}
    old=agent.normalize_candidate({**base,'access_mode_evidence':'future_procurement'})
    new=agent.normalize_candidate({**base,'access_mode_evidence':'beneficiary_contractor','procurement_url':'https://worldbank.org/plan'})
    assert identity_keys(old)[1]==identity_keys(new)[1]
    class Existing:
        title=old.title;institution=old.institution;reference=None;deadline=None;source_status=None;radar_metadata=old.radar_fields()
    changes=ResultWorkflowService().changed_fields(Existing(),new)
    assert 'opportunity_type' in changes and 'procurement_url' in changes

def test_closed_strategic_reference_and_deterministic_skip_ai(app):
    agent=FundingRadarAgent();item=agent.normalize_candidate({'title':'Closed Morocco heritage program','funder':'AFD',
        'url':'https://afd.fr/x','morocco_related':True,'reported_funding_status':'closed','strategically_relevant':True,
        'access_mode_evidence':'monitor_only','beneficiary':'Ministry','source':'afd.fr','source_quality':'OFFICIAL_PRIMARY'})
    decision=agent.validate_candidate(item)
    assert decision.accepted and decision.allow_ai is False
    assert not agent.validate_candidate(item.model_copy(update={'strategically_relevant':False})).accepted
