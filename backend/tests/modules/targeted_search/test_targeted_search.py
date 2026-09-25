from datetime import date
from unittest.mock import Mock

import pytest

from backend.app.db.extensions import db
from backend.app.db.models import Result, TargetedSearchBriefVersion, TargetedSearchResultLink, TargetedSearchSession
from backend.app.integrations.openai.base import SearchHit, SearchResponse
from backend.app.modules.targeted_search.parser import fold, interpret_brief
from backend.app.modules.targeted_search.service import ActiveTargetedRunError, StaleBriefError, TargetedSearchService
from backend.app.bot.handlers.common import fallback, on_callback
from test_bot import fixture_update


TODAY=date(2026,9,14)


@pytest.mark.parametrize('prompt,mode,place,start,documents',[
    ('Trouve des marchés à El Jadida en lien avec les murailles, avec CPS et RC.',
     'PROCUREMENT','El Jadida',None,['CPS','RC']),
    ('Cherche les projets en gestation sur la valorisation du patrimoine à Safi.',
     'PROJECTS','Safi',None,[]),
    ('Cherche des études territoriales à Dakhla depuis juin 2026.',
     'PROJECTS','Dakhla','2026-06-01',[]),
    ('Quels bailleurs financent la régénération urbaine au Maroc ?',
     'FUNDING','Maroc',None,[]),
])
def test_reference_briefs_are_interpreted_without_external_calls(prompt,mode,place,start,documents):
    brief=interpret_brief(prompt,123,TODAY)
    assert brief['search_mode']==mode and brief['geography']==[place]
    assert brief['date_from']==start and brief['document_requirements']==documents
    if 'murailles' in prompt:
        assert {'remparts','fortifications','bastions'}<=set(brief['related_concepts'])
    if place=='Dakhla':assert 'patrimoine' not in brief['positive_signals']


@pytest.mark.parametrize('prompt,start,end,recency',[
    ('depuis le 1er juillet 2026','2026-07-01',None,'EXPLICIT'),
    ('le 1er juillet 2026','2026-07-01','2026-07-01','EXPLICIT'),
    ('entre 1 juin 2026 et 30 juillet 2026','2026-06-01','2026-07-30','EXPLICIT'),
    ('archives 2023-2024','2023-01-01','2024-12-31','ARCHIVE'),
    ('avant juin 2026',None,'2026-06-30','EXPLICIT'),
    ('aujourd’hui','2026-09-14','2026-09-14','CURRENT'),
    ('cette semaine','2026-09-14','2026-09-14','CURRENT'),
])
def test_date_constraints_are_first_class(prompt,start,end,recency):
    brief=interpret_brief('Cherche des articles '+prompt,123,TODAY)
    assert (brief['date_from'],brief['date_to'],brief['recency_mode'])==(start,end,recency)


def test_exact_month_has_both_boundaries():
    brief=interpret_brief('articles septembre 2026',123,TODAY)
    assert (brief['date_from'],brief['date_to'])==('2026-09-01','2026-09-30')


@pytest.mark.parametrize('alias,canonical',[
    ('Mazagan','El Jadida'),('Cité Portugaise','El Jadida'),
    ('Fès el-Bali','Fès'),('Fès Jdid','Fès'),
    ('Ksar El Bahr','Safi'),('Château de Mer','Safi'),
    ('Essaouira','Essaouira'),('Tiznit','Tiznit'),('Taroudant','Taroudant'),
])
def test_moroccan_heritage_aliases(alias,canonical):
    brief=interpret_brief(f'projets patrimoine à {alias}',123,TODAY)
    assert brief['geography']==[canonical]
    assert fold(alias) in [fold(value) for value in brief['geography_aliases']]


def test_unknown_literal_geography_is_preserved():
    brief=interpret_brief('Cherche des projets à Aït Ben Haddou, depuis juin 2026',123,TODAY)
    assert brief['geography']==['Aït Ben Haddou']


def test_refinement_versions_same_session_and_rejects_old_confirmation(app):
    service=TargetedSearchService();session_id,first=service.create(app,'murailles El Jadida',123,today=TODAY)
    version,second=service.refine(app,session_id,'ajoute portes historiques et bastions',123,today=TODAY)
    assert version==2 and {'portes historiques','bastions'}<=set(second['related_concepts']+second['positive_signals'])
    with pytest.raises(StaleBriefError):service.reserve(app,session_id,1)
    service.reserve(app,session_id,2)
    with app.app_context():
        assert db.session.get(TargetedSearchSession,session_id).status=='RUNNING'
        assert db.session.scalar(db.select(db.func.count(TargetedSearchBriefVersion.id)))==2


def test_ten_launch_attempts_reserve_only_one_run(app):
    service=TargetedSearchService();session_id,_=service.create(app,'articles patrimoine Safi',123,today=TODAY)
    outcomes=[]
    for _ in range(10):
        try:service.reserve(app,session_id,1);outcomes.append('reserved')
        except ActiveTargetedRunError:outcomes.append('active')
    assert outcomes.count('reserved')==1 and outcomes.count('active')==9


def test_exclusion_refinement_is_session_local(app):
    service=TargetedSearchService();one,_=service.create(app,'patrimoine Safi',123,today=TODAY)
    two,_=service.create(app,'patrimoine Safi',123,today=TODAY)
    _,changed=service.refine(app,one,'exclus le tourisme sans intervention patrimoniale',123,today=TODAY)
    assert changed['negative_signals']
    assert not service.get(app,two)['brief']['negative_signals']


def test_confirmed_execution_reuses_global_result_and_distinguishes_known(app):
    service=TargetedSearchService();provider=Mock()
    provider.search.return_value=SearchResponse([SearchHit(title='Restauration des murailles El Jadida',
        url='https://example.org/tender?utm_source=x',evidence='CPS RC remparts El Jadida',
        location='El Jadida',publication_date='2026-09-10',status='open')])
    first,_=service.create(app,'marchés murailles El Jadida avec CPS et RC',123,today=TODAY)
    service.reserve(app,first,1);summary=service.execute(app,first,1,provider)
    assert summary['new']==1 and provider.search.call_count==1
    second,_=service.create(app,'marchés remparts El Jadida',123,today=TODAY)
    service.reserve(app,second,1);known=service.execute(app,second,1,provider)
    assert known['known']==1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Result.id)))==1
        assert db.session.scalar(db.select(db.func.count(TargetedSearchResultLink.id)))==2


def test_procurement_metadata_is_persisted_and_rendered(app):
    service=TargetedSearchService();session_id,_=service.create(
        app,'marchés murailles El Jadida avec CPS RC DCE',123,today=TODAY)
    service.reserve(app,session_id,1)
    hit=SearchHit(title='Restauration des murailles El Jadida',url='https://example.org/rich',
        evidence='CPS RC DCE remparts El Jadida',location='El Jadida',
        publication_date='2026-09-10',deadline='2026-10-01',status='open')
    data=hit.model_dump()|{'estimated_amount':2_000_000,'estimated_currency':'MAD',
        'estimated_amount_verified':True,'deadline_time':'10:00','dce_available':True,
        'dce_access_mode':'FORM_REQUIRED','document_types':['CPS','RC','DCE']}
    assert service.ingest(app,session_id,1,[data])['new']==1
    card=service.result_page(app,session_id,0)[0][0]
    assert card['estimated_amount']==2_000_000 and card['deadline_time']=='10:00'
    assert card['document_types']==['CPS','RC','DCE']
    assert card['dce_access_mode']=='FORM_REQUIRED'


def test_continue_marks_unchanged_known_and_material_content_updated(app):
    service=TargetedSearchService();provider=Mock()
    hit=SearchHit(title='Restauration murailles El Jadida',url='https://example.org/evolving',
        evidence='Projet de restauration remparts El Jadida',location='El Jadida')
    provider.search.return_value=SearchResponse([hit])
    session_id,_=service.create(app,'projets murailles El Jadida',123,today=TODAY)
    service.reserve(app,session_id,1);assert service.execute(app,session_id,1,provider)['new']==1
    service.reserve(app,session_id,1);assert service.execute(app,session_id,1,provider)['known']==1
    provider.search.return_value=SearchResponse([hit.model_copy(update={'evidence':hit.evidence+' financement approuve'})])
    service.reserve(app,session_id,1);assert service.execute(app,session_id,1,provider)['updated']==1
    with app.app_context():assert db.session.scalar(db.select(db.func.count(TargetedSearchResultLink.id)))==1


def test_current_rejects_expired_but_archive_includes_it(app):
    hit=SearchHit(title='Marché murailles El Jadida',url='https://example.org/archive',
        evidence='restauration remparts El Jadida',location='El Jadida',publication_date='2023-06-01',status='expired')
    service=TargetedSearchService()
    current,_=service.create(app,'marchés actuels murailles El Jadida',123,today=TODAY)
    service.reserve(app,current,1);assert service.ingest(app,current,1,[hit])['rejected']==1
    archive,_=service.create(app,'archives marchés murailles El Jadida 2023-2024',123,today=TODAY)
    service.reserve(app,archive,1);assert service.ingest(app,archive,1,[hit])['new']==1


def test_draft_history_and_refinement_cost_zero(app):
    service=TargetedSearchService();provider=Mock()
    session_id,_=service.create(app,'études territoriales Dakhla',123,today=TODAY)
    service.refine(app,session_id,'depuis juin 2026',123,today=TODAY)
    assert service.history(app)[0]['id']==session_id
    provider.search.assert_not_called()


async def test_telegram_draft_confirmation_is_local_and_versioned(app):
    callback,context=fixture_update(app,data='t:new')
    await on_callback(callback,context)
    assert context.user_data['targeted_input']=={'action':'new'}
    message,_=fixture_update(app)
    message.effective_message.text='marchés murailles El Jadida avec CPS et RC'
    message_context=context
    await fallback(message,message_context)
    rendered=message.effective_message.reply_text.call_args
    assert 'Recherche comprise' in rendered.args[0]
    launch=rendered.kwargs['reply_markup'].inline_keyboard[0][0].callback_data
    assert launch.startswith('t:confirm:')
    with app.app_context():
        session=db.session.scalar(db.select(TargetedSearchSession))
        assert session.status=='DRAFT' and session.current_version==1
