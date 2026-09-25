"""Persistent targeted-search lifecycle. External discovery occurs only after versioned confirmation."""
import logging
from datetime import date
from urllib.parse import urlsplit

from sqlalchemy.orm.attributes import flag_modified

from app.db.extensions import db
from app.db.models import (Radar, Result, TargetedSearchBriefVersion, TargetedSearchFeedback,
                        TargetedSearchResultLink, TargetedSearchSession, utcnow)
from app.core.dedup import canonical_url, digest, normalized_source_title
from app.modules.targeted_search.parser import interpret_brief, refine_brief, fold
from app.core.logging import log_failure

logger = logging.getLogger(__name__)

MODE_RADAR = {'PROCUREMENT':'RADAR_1_MARKETS','PROJECTS':'RADAR_2_PROJECTS','ARTICLES':'RADAR_2_PROJECTS',
              'INSTITUTIONS':'RADAR_3_INSTITUTIONS','POLICIES':'RADAR_4_POLICIES','FUNDING':'RADAR_5_FUNDING',
              'MIXED':'RADAR_2_PROJECTS'}


class StaleBriefError(ValueError): pass
class ActiveTargetedRunError(ValueError): pass


class TargetedSearchService:
    @staticmethod
    def _result_payload(link, result, radar):
        metadata=result.radar_metadata or {}
        source_metadata=(result.source_metadata or {}).get('metadata') or {}
        origin=('Recherche ciblée' if metadata.get('targeted_only') else
                {'RADAR_1_MARKETS':'Radar 1','RADAR_2_PROJECTS':'Radar 2',
                 'RADAR_3_INSTITUTIONS':'Radar 3','RADAR_4_POLICIES':'Radar 4',
                 'RADAR_5_FUNDING':'Radar 5'}.get(radar.code,radar.code))
        return {'id':link.result_id,'title':result.title,'url':result.url,
            'institution':result.institution,'reference':result.reference,
            'publication':str(result.publication_date or '—'),
            'deadline':str(result.deadline or '—'),'source':result.source,
            'match_status':link.match_status,'status':link.review_status,
            'origin':origin,'score':link.relevance_score,'reason':link.match_reason,
            **{key:metadata.get(key) for key in (
                'procedure_type','estimated_amount','estimated_currency',
                'estimated_amount_tax_mode','estimated_amount_source','estimated_amount_verified',
                'deadline_time','dce_available','dce_access_mode','dce_url','document_types',
                'competition_prize_amount','competition_prize_currency',
                'eligibility_conditions','competition_regulation_available')},
            'official_url':metadata.get('official_url') or source_metadata.get('official_url')}

    def create(self, app, prompt, user_id, *, today=None):
        brief=interpret_brief(prompt,user_id,today)
        with app.app_context():
            session=TargetedSearchSession(title=brief['search_title'],original_prompt=prompt,
                creator_user_id=user_id,current_version=1,status='DRAFT')
            db.session.add(session);db.session.flush()
            db.session.add(TargetedSearchBriefVersion(session_id=session.id,version=1,brief=brief,
                created_by_user_id=user_id));db.session.commit();return session.id,brief

    def get(self, app, session_id):
        with app.app_context():
            session=db.session.get(TargetedSearchSession,session_id)
            if not session:return None
            version=db.session.scalar(db.select(TargetedSearchBriefVersion).where(
                TargetedSearchBriefVersion.session_id==session.id,
                TargetedSearchBriefVersion.version==session.current_version))
            return {'id':session.id,'title':session.title,'status':session.status,'version':session.current_version,
                    'creator_user_id':session.creator_user_id,'brief':version.brief,'summary':session.run_summary}

    def refine(self, app, session_id, text, user_id, *, today=None):
        with app.app_context():
            session=db.session.get(TargetedSearchSession,session_id)
            if not session or session.status=='RUNNING':raise ValueError('Recherche indisponible.')
            old=db.session.scalar(db.select(TargetedSearchBriefVersion).where(
                TargetedSearchBriefVersion.session_id==session.id,
                TargetedSearchBriefVersion.version==session.current_version))
            brief=refine_brief(old.brief,text,user_id,today);session.current_version+=1;session.status='DRAFT'
            db.session.add(TargetedSearchBriefVersion(session_id=session.id,version=session.current_version,
                brief=brief,refinement_prompt=text,created_by_user_id=user_id));db.session.commit()
            return session.current_version,brief

    def reserve(self, app, session_id, version):
        with app.app_context():
            session=db.session.get(TargetedSearchSession,session_id)
            if not session or session.current_version!=version:raise StaleBriefError('Cette version du brief n’est plus actuelle.')
            changed=db.session.execute(db.update(TargetedSearchSession).where(
                TargetedSearchSession.id==session_id,TargetedSearchSession.current_version==version,
                TargetedSearchSession.status!='RUNNING').values(status='RUNNING',updated_at=utcnow()))
            if changed.rowcount!=1:db.session.rollback();raise ActiveTargetedRunError('Une recherche est déjà en cours.')
            db.session.commit()

    def cancel(self, app, session_id, version):
        with app.app_context():
            changed=db.session.execute(db.update(TargetedSearchSession).where(
                TargetedSearchSession.id==session_id,TargetedSearchSession.current_version==version,
                TargetedSearchSession.status=='DRAFT').values(status='CANCELLED',updated_at=utcnow()))
            db.session.commit();return changed.rowcount==1

    def execute(self, app, session_id, version, provider=None):
        """Run one bounded discovery query; tests inject a provider and production creates it after confirmation."""
        with app.app_context():
            session=db.session.get(TargetedSearchSession,session_id)
            if not session or session.current_version!=version or session.status!='RUNNING':
                raise StaleBriefError('Exécution obsolète.')
            row=db.session.scalar(db.select(TargetedSearchBriefVersion).where(
                TargetedSearchBriefVersion.session_id==session_id,TargetedSearchBriefVersion.version==version))
            brief=row.brief
        production_provider = provider is None
        direct_hits = self._direct_hits(app, brief) if production_provider else []
        if direct_hits:
            summary=self.ingest(app,session_id,version,direct_hits)
            if summary['pending']:
                summary.update(search_calls=0,input_tokens=0,output_tokens=0,direct_source_items=len(direct_hits))
                with app.app_context():
                    session=db.session.get(TargetedSearchSession,session_id);session.status='COMPLETED';session.last_run_at=utcnow();session.run_summary=summary
                    flag_modified(session,'run_summary');db.session.commit()
                return summary
        if provider is None:
            from app.integrations.openai.search import OpenAISearchProvider
            purpose={'PROCUREMENT':'procurement','PROJECTS':'projects','INSTITUTIONS':'institutions',
                     'POLICIES':'policies','FUNDING':'funding'}.get(brief['search_mode'],'projects')
            provider=OpenAISearchProvider(app.config['OPENAI_API_KEY'],app.config['OPENAI_SEARCH_MODEL'],purpose)
        query=self._query(brief)
        try:
            response=provider.search(query,recency_days=self._recency(brief))
            summary=self.ingest(app,session_id,version,response.hits)
            summary['search_calls']=1;summary['input_tokens']=getattr(response.usage,'input_tokens',0) if response.usage else 0
            summary['output_tokens']=getattr(response.usage,'output_tokens',0) if response.usage else 0
            with app.app_context():
                session=db.session.get(TargetedSearchSession,session_id);session.status='COMPLETED';session.last_run_at=utcnow();session.run_summary=summary
                flag_modified(session,'run_summary');db.session.commit()
            return summary
        except Exception as error:
            log_failure(logger, f'targeted execute session_id={session_id}', error)
            with app.app_context():
                session=db.session.get(TargetedSearchSession,session_id)
                if session:session.status='FAILED';db.session.commit()
            raise

    def _direct_hits(self,app,brief):
        """Reuse curated GET-only adapters before constructing any paid provider."""
        from app.integrations.http.adapters import build_source_adapters
        from app.core.source_catalog import DEFAULT_SOURCES
        from app.db.repositories.source_state import SourceStateService
        modes=brief.get('pipeline_modes') or [brief.get('search_mode')]
        hits=[]
        with app.app_context():
            for mode in modes:
                code=MODE_RADAR.get(mode)
                if mode=='PROCUREMENT':
                    from urllib.parse import urlencode
                    from app.modules.radar1_markets.collector import MarketsCollector
                    from app.modules.radar1_markets.discovery_strategies import DirectDiscovery
                    from app.integrations.openai.disabled import DisabledSearchProvider
                    collector=MarketsCollector(DisabledSearchProvider(),dict(app.config))
                    concepts=(brief.get('positive_signals') or brief.get('topics') or [])[:2]
                    places=(brief.get('geography_aliases') or brief.get('geography') or [])[:3]
                    terms=([f'{concept} {place}' for concept in concepts for place in places][:3]
                           if places else concepts[:3])
                    for term in terms:
                        url='https://www.marchespublics.gov.ma/index.php?'+urlencode({
                            'keyWord':term,'page':'entreprise.EntrepriseAdvancedSearch','searchAnnCons':''})
                        rows,_=collector._direct_page(DirectDiscovery('PMMP','targeted',url))
                        for row in rows:
                            try:
                                from app.integrations.pmmp.parser import enrich_detail, verify_detail
                                from app.modules.radar1_markets.policy import detail_url
                                item=collector._normalize(row,url)
                                if detail_url(item.url):
                                    item=enrich_detail(item,collector.pages)
                                    item=verify_detail(item,collector.pages)
                                hits.append(item.model_dump())
                            except (OSError,ValueError,TimeoutError):
                                # The listing identity remains useful; protected
                                # detail access is never bypassed.
                                hits.append(row.model_dump() if hasattr(row,'model_dump') else row)
                    continue
                records=DEFAULT_SOURCES.get(code)
                if not records:continue
                number={'RADAR_2_PROJECTS':2,'RADAR_3_INSTITUTIONS':3,'RADAR_4_POLICIES':4,'RADAR_5_FUNDING':5}.get(code)
                domains=app.config.get(f'RADAR{number}_SOURCE_WHITELIST',())
                adapters=build_source_adapters(records,domains,timeout=app.config.get('SOURCE_HTTP_TIMEOUT_SECONDS',20),
                    state=SourceStateService('TARGETED'))
                for adapter in adapters[:4]:
                    fetched=adapter.fetch()
                    if fetched.status in {'CHANGED','UNCHANGED'}:
                        hits.extend(fetched.items[:50])
        return hits[:100]

    def ingest(self, app, session_id, version, hits):
        counts={'new':0,'known':0,'updated':0,'rejected':0,'pending':0}
        with app.app_context():
            session=db.session.get(TargetedSearchSession,session_id)
            brief=db.session.scalar(db.select(TargetedSearchBriefVersion).where(
                TargetedSearchBriefVersion.session_id==session_id,
                TargetedSearchBriefVersion.version==version)).brief
            radar=db.session.scalar(db.select(Radar).where(Radar.code==MODE_RADAR[brief['search_mode']]))
            for hit in hits:
                data=hit.model_dump() if hasattr(hit,'model_dump') else dict(hit)
                observed_hash=digest([normalized_source_title(data.get('title') or ''),data.get('evidence') or ''])
                score,reason=self._score(brief,data)
                if score<45:counts['rejected']+=1;continue
                published=data.get('publication_date'); published=date.fromisoformat(published) if isinstance(published,str) else published
                if not self._date_ok(brief,published,data.get('status')):counts['rejected']+=1;continue
                try:url=canonical_url(data.get('url'))
                except (ValueError,TypeError):counts['rejected']+=1;continue
                existing=db.session.scalar(db.select(Result).where(db.or_(Result.canonical_url==url,
                    Result.url_key==digest([url]))).limit(1))
                status='KNOWN'
                if existing is None:
                    title=data.get('title') or url; fp=digest([url])
                    deadline=data.get('deadline'); deadline=date.fromisoformat(deadline) if isinstance(deadline,str) else deadline
                    procurement_fields = {key:data[key] for key in (
                        'business_category','procedure_type','estimated_amount','estimated_currency',
                        'estimated_amount_tax_mode','estimated_amount_source','estimated_amount_verified',
                        'estimated_lots','provisional_bond_amount','provisional_bond_currency',
                        'publication_date_source','publication_date_verified','deadline_source',
                        'deadline_verified','deadline_time','dce_available','dce_access_mode','dce_url',
                        'document_types','competition_prize_amount','competition_prize_currency',
                        'eligibility_conditions','competition_regulation_available','official_url',
                        'official_url_status','official_confirmation','detail_verified','source_type')
                        if data.get(key) is not None}
                    existing=Result(radar_id=radar.id,title=title,url=data.get('url'),canonical_url=url,url_key=digest([url]),
                        fingerprint=fp,identity_key=digest([normalized_source_title(title),data.get('institution') or '']),
                        source=data.get('source') or urlsplit(url).hostname,institution=data.get('institution'),
                        publication_date=published,deadline=deadline,status='new',source_status=data.get('status'),
                        discovery_status='NEW',review_status=None,source_metadata={'metadata':{
                            **(data.get('metadata') or {}),'targeted_search_origin':session_id}},
                        radar_metadata={'targeted_only':True,**procurement_fields},analysis=None,
                        content_hash=digest([title,data.get('evidence') or '']))
                    db.session.add(existing);db.session.flush();status='NEW'
                link=db.session.scalar(db.select(TargetedSearchResultLink).where(
                    TargetedSearchResultLink.session_id==session_id,TargetedSearchResultLink.result_id==existing.id))
                if link:
                    status='UPDATED' if link.content_fingerprint!=observed_hash else 'KNOWN'
                    link.brief_version=version;link.match_status=status;link.content_fingerprint=observed_hash
                    link.relevance_score=score;link.match_reason=reason;link.last_matched_at=utcnow()
                else:
                    link=TargetedSearchResultLink(session_id=session_id,brief_version=version,result_id=existing.id,
                        match_status=status,relevance_score=score,content_fingerprint=observed_hash,match_reason=reason)
                    db.session.add(link)
                counts[status.lower()]+=1;counts['pending']+=int(link.review_status=='PENDING')
            db.session.commit();return counts

    def _score(self, brief, data):
        text=fold(' '.join(str(data.get(k) or '') for k in ('title','evidence','institution','location')))
        positives=[fold(x) for x in brief.get('positive_signals',[])]; matched=sum(x in text for x in positives if x)
        if any(fold(x) in text for x in brief.get('negative_signals',[])):return 0,'Exclusion explicite'
        score=35+min(35,matched*10)
        geo=brief.get('geography') or []
        geo_terms=brief.get('geography_aliases') or geo
        if geo:score += 20 if any(fold(x) in text for x in geo_terms) else -35
        if data.get('source_quality') in {'OFFICIAL_PRIMARY','OFFICIAL'}:score+=10
        return max(0,min(100,score)),f'{matched} signal(s), zone '+('confirmée' if not geo or any(fold(x) in text for x in geo_terms) else 'non confirmée')

    @staticmethod
    def _date_ok(brief,published,status):
        if brief.get('recency_mode')!='ARCHIVE' and fold(status) in {'closed','expired'} and 'OPEN' in brief.get('status_requirements',[]):return False
        if not published:return not (brief.get('date_from') or brief.get('date_to'))
        return (not brief.get('date_from') or published>=date.fromisoformat(brief['date_from'])) and (not brief.get('date_to') or published<=date.fromisoformat(brief['date_to']))

    @staticmethod
    def _recency(brief):
        if brief.get('date_from'):
            return max(1,(date.today()-date.fromisoformat(brief['date_from'])).days)
        return 365 if brief.get('search_mode') in {'POLICIES','FUNDING'} else 90

    @staticmethod
    def _query(brief):
        parts=brief.get('positive_signals',[])[:8]+(brief.get('geography_aliases') or brief.get('geography',[]))+brief.get('document_requirements',[])
        dates=[brief.get('date_from'),brief.get('date_to')]
        return 'Targeted professional research: '+'; '.join(str(x) for x in parts+dates if x)

    def history(self, app, limit=20):
        with app.app_context():
            rows=db.session.scalars(db.select(TargetedSearchSession).order_by(TargetedSearchSession.updated_at.desc()).limit(limit))
            return [{'id':x.id,'title':x.title,'version':x.current_version,'status':x.status,'creator':x.creator_user_id} for x in rows]

    def pending_sessions(self,app,limit=20):
        with app.app_context():
            rows=db.session.execute(db.select(TargetedSearchSession,db.func.count(TargetedSearchResultLink.id)).join(
                TargetedSearchResultLink,TargetedSearchResultLink.session_id==TargetedSearchSession.id).where(
                TargetedSearchResultLink.review_status=='PENDING').group_by(TargetedSearchSession.id).order_by(
                TargetedSearchSession.updated_at.desc()).limit(limit)).all()
            return [{'id':session.id,'title':session.title,'count':count} for session,count in rows]

    def result_page(self,app,session_id,index,mode='PENDING'):
        if mode not in {'PENDING','PERTINENT','REJECTED'} or not 0<=index<=10000:raise ValueError('Page invalide.')
        with app.app_context():
            rows=db.session.execute(db.select(TargetedSearchResultLink,Result,Radar).join(Result,
                TargetedSearchResultLink.result_id==Result.id).join(Radar,Result.radar_id==Radar.id).where(TargetedSearchResultLink.session_id==session_id,
                TargetedSearchResultLink.review_status==mode).order_by(TargetedSearchResultLink.relevance_score.desc(),
                Result.publication_date.desc().nullslast(),Result.id.desc())).all()
            total=max(1,(len(rows)+4)//5);effective=min(index,total-1);selected=rows[effective*5:(effective+1)*5]
            cards=[self._result_payload(link,result,radar) for link,result,radar in selected]
            return cards,len(rows)>(effective+1)*5,total,effective

    def result_detail(self,app,session_id,result_id):
        with app.app_context():
            pair=db.session.execute(db.select(TargetedSearchResultLink,Result,Radar).join(Result).join(
                Radar,Result.radar_id==Radar.id).where(TargetedSearchResultLink.session_id==session_id,
                TargetedSearchResultLink.result_id==result_id)).first()
            if not pair:return None
            link,result,radar=pair
            return self._result_payload(link,result,radar)

    def feedback(self,app,session_id,result_id,decision,user_id,reason=None):
        if decision not in {'PERTINENT','REJECTED','TOO_BROAD','TOO_NARROW','WRONG_LOCATION','WRONG_DATE','WRONG_TYPE'}:raise ValueError('Décision invalide.')
        with app.app_context():
            link=db.session.scalar(db.select(TargetedSearchResultLink).where(TargetedSearchResultLink.session_id==session_id,TargetedSearchResultLink.result_id==result_id))
            if not link:raise ValueError('Résultat absent de cette recherche.')
            if decision in {'PERTINENT','REJECTED'}:link.review_status=decision
            db.session.add(TargetedSearchFeedback(session_id=session_id,result_id=result_id,brief_version=link.brief_version,
                decision=decision,reason=reason,user_id=user_id));db.session.commit()
