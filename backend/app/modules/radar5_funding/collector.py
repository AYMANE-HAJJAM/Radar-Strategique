import re
from urllib.parse import urljoin,urlsplit
from app.modules.radar5_funding.schemas import FundingCandidate
from app.core.collector_base import sources_unchanged, CollectionReport,ProviderUnavailable,query_batches,run_source_adapters,paid_search_budget
from app.integrations.http.html import PublicPages, AccessLimitedPages
from app.modules.radar5_funding.policy import classify,parse_date,folded
from app.integrations.openai.base import SearchProviderError
QUERIES=('World Bank Morocco urban development project','AfDB Morocco urban territorial program',
    'EIB Morocco urban rehabilitation financing','AFD Maroc patrimoine développement urbain',
    'EU Morocco cultural heritage grant','KfW Morocco urban resilience program')
COUNTERS=('funders_checked','programs_found','morocco_relevant','status_a','status_b','status_c','status_d',
    'direct_access','consultant_opportunity','beneficiary_procurement','pipeline','search_calls','ai_calls','final_kept')
FUNDERS={'worldbank.org':'World Bank','afdb.org':'African Development Bank','eib.org':'European Investment Bank',
    'ebrd.com':'EBRD','afd.fr':'AFD','europa.eu':'European Union','kfw-entwicklungsbank.de':'KfW','undp.org':'UNDP'}
class FundingCollector:
    def __init__(self,provider,config,*,pages=None):
        self.provider,self.config=provider,config;self.domains=tuple(config.get('RADAR5_SOURCE_WHITELIST',()))
        self.report=CollectionReport(metrics={**dict.fromkeys(COUNTERS,0),'collector_health':'HEALTHY'})
        self.pages=AccessLimitedPages(pages or PublicPages(self.domains,config.get('SOURCE_HTTP_TIMEOUT_SECONDS',20)),{'http_403':0,'http_429':0})
        self.on_progress=lambda:None;self.known_unchanged=lambda c:False;self.seen=set()
    def _allowed(self,url):
        host=(urlsplit(url).hostname or '').lower().removeprefix('www.')
        return any(host==d or host.endswith('.'+d) for d in self.domains)
    def _funder(self,url,institution):
        host=(urlsplit(url).hostname or '').lower()
        return next((name for domain,name in FUNDERS.items() if host==domain or host.endswith('.'+domain)),institution)
    def _candidate(self,title,url,evidence,institution=None,publication_date=None,location=None):
        if not self._allowed(url):return None
        found=classify(title+' '+evidence)
        if not found:return None
        status,letter,mode=found;funder=self._funder(url,institution)
        if not funder:return None
        amount=re.search(r'(?<!\d)([\d][\d .,\u00a0]*)\s*(million|milliard|mn|bn)?\s*(EUR|USD|MAD|DH|€|\$)',evidence,re.I)
        prefix_amount=re.search(r'(EUR|USD|MAD|DH|€|\$)\s*([\d][\d .,\u00a0]*)\s*(million|milliard|mn|bn)?',evidence,re.I)
        value=None;currency=None
        if amount or prefix_amount:
            number=(amount[1] if amount else prefix_amount[2]);unit=(amount[2] if amount else prefix_amount[3]);code=(amount[3] if amount else prefix_amount[1])
            try:value=float(number.replace(' ','').replace('\u00a0','').replace(',','.'))*(1_000_000_000 if folded(unit) in {'milliard','bn'} else 1_000_000 if unit else 1)
            except ValueError:pass
            currency={'€':'EUR','$':'USD'}.get(code,code.upper())
        excerpt=' '.join(evidence.split())[:2000];published=parse_date(publication_date)
        direct=mode=='DIRECT_ACCESS' and has_explicit_eligibility(excerpt)
        if mode=='DIRECT_ACCESS' and not direct:mode='MONITORING_ONLY'
        strategic=status!='closed' or bool(found and has_strategic_scope(excerpt))
        return FundingCandidate(title=title[:2000],url=url,source=(urlsplit(url).hostname or '')[:255],institution=institution,
            publication_date=published,source_status='active',morocco_related=True,source_quality='OFFICIAL_PRIMARY',current_evidence=True,
            funder=funder,program=title[:500],program_name=title[:500],country_scope='Morocco',morocco_relevance=excerpt,
            opportunity_type=mode,funding_status=letter,beneficiary=institution,amount=value,currency=currency,
            reported_funding_status=status,territory=location,sector=', '.join(x for x in ('urban','heritage','territorial') if x in folded(excerpt)) or None,
            eligibility=excerpt if direct else None,direct_eligibility_confirmed=direct,access_mode_evidence=mode,
            potential_procurement=excerpt if mode in {'CONSULTANT_OPPORTUNITY','BENEFICIARY_PROCUREMENT','PROJECT_PIPELINE'} else None,
            official_source=url,official_url=url,procurement_url=url if mode=='BENEFICIARY_PROCUREMENT' else None,
            summary=excerpt,business_relevance='Potential access route shown by official program evidence; eligibility is not assumed.',
            general_donor_page=False,strategically_relevant=strategic,approval_date=published if status=='active' else None,
            closing_date=None,metadata={'source_type':'OFFICIAL','access_evidence':excerpt})
    def _add(self,item):
        if not item:return
        key=folded(item.program_name)+'|'+folded(item.funder)
        if key in self.seen or self.known_unchanged(item):return
        self.seen.add(key);self.report.candidates.append(item);self.report.observations.append(item)
        m=self.report.metrics;m['programs_found']+=1;m['morocco_relevant']+=1;m['final_kept']+=1
        if item.funding_status in 'ABCD':m['status_'+item.funding_status.lower()]+=1
        m['direct_access']+=int(item.opportunity_type=='DIRECT_ACCESS');m['consultant_opportunity']+=int(item.opportunity_type=='CONSULTANT_OPPORTUNITY')
        m['beneficiary_procurement']+=int(item.opportunity_type=='BENEFICIARY_PROCUREMENT');m['pipeline']+=int(item.opportunity_type=='PROJECT_PIPELINE')
    def _direct(self):
        def consume(item,result):
            raw=item.get('raw') or {}
            institution=result.source.name
            if raw:
                sector=' '.join(str(value.get('Name') or '') for key,value in raw.items()
                    if key.startswith('sector') and isinstance(value,dict))
                themes=' '.join(str(value.get('name') or '') for value in (raw.get('mjtheme_namecode') or [])
                    if isinstance(value,dict))
                evidence=' '.join(str(raw.get(key) or '') for key in ('project_name','projectstatusdisplay',
                    'borrower','impagency','countryshortname','lendinginstr'))+' '+sector+' '+themes
            else:
                evidence=item.get('evidence') or item.get('title') or ''
            candidate=self._candidate(item.get('title') or result.source.name,item.get('url') or result.url,
                evidence,institution,item.get('date'),raw.get('countryshortname') or raw.get('country_name'))
            if candidate and raw:
                amount=raw.get('totalamt') or raw.get('totalcommamt')
                try: amount=float(str(amount).replace(',',''))
                except (TypeError,ValueError): amount=None
                status=folded(raw.get('projectstatusdisplay') or raw.get('status'))
                candidate=candidate.model_copy(update={'amount':amount,'currency':'USD' if amount is not None else None,
                    'beneficiary':raw.get('borrower') or raw.get('impagency'),
                    'closing_date':parse_date(raw.get('closingdate')),
                    'reported_funding_status':'active' if status=='active' else 'closed' if status in {'closed','completed'} else candidate.reported_funding_status,
                    'funding_status':'B' if status=='active' else candidate.funding_status,
                    'metadata':{**candidate.metadata,'project_id':raw.get('id'),'structured_source':True}})
            self._add(candidate)
        run_source_adapters(self,consume)
        if getattr(self,'source_adapters',None):
            return
        for feed in self.config.get('RADAR5_DIRECT_FEEDS',())[:self.config['RADAR5_DIRECT_SOURCE_LIMIT']]:
            self.report.metrics['funders_checked']+=1
            try:
                base,page=self.pages.get(feed)
                for href,label in page.links:
                    url=urljoin(base,href)
                    if len(label.strip())>25:self._add(self._candidate(label,url,label,self._funder(url,None)))
            except (OSError,ValueError,TimeoutError):pass
    def collect(self,radar):
        self._direct()
        fetched=0
        fallback=paid_search_budget(self.config,5) if hasattr(self,'source_adapters') else self.config['RADAR5_SEARCH_MAX_CALLS']
        budget=0 if len(self.report.candidates)>=self.config.get('RADAR5_DIRECT_MIN_YIELD',2) else fallback
        if sources_unchanged(self.report): budget = 0
        self.report.metrics['escalation_level']=0 if budget==0 else 1
        queries=QUERIES[:min(self.config['RADAR5_SEARCH_MAX_CALLS'],budget)]
        for q,themes in query_batches(queries,self.config.get('RADAR5_SEARCH_BATCH_SIZE',3)):
            if len(self.report.candidates)>=self.config.get('RADAR5_TARGET_OBSERVATIONS',12):break
            self.report.metrics['search_calls'] += 1
            try:
                response=self.provider.search(q,recency_days=365,domains=self.domains);self.report.usage_events.append(response)
                self.report.queries_executed+=len(themes);self.report.successful_queries+=1
                for h in response.hits:
                    item=self._candidate(h.title,h.url,h.evidence,h.institution,h.publication_date,h.location)
                    if item is None and fetched<self.config.get('RADAR5_SEARCH_DETAIL_FETCH_LIMIT',10):
                        try:
                            final,detail=self.pages.get(h.url);fetched+=1
                            item=self._candidate(' '.join(detail.h1).strip() or h.title,final,detail.text,
                                h.institution,h.publication_date,h.location)
                        except (OSError,ValueError,TimeoutError):pass
                    self._add(item)
            except SearchProviderError as e:
                self.report.usage_events.append(e.response)
                self.report.query_errors.append({'query':q,'kind':e.kind})
                if len(self.report.query_errors)>=3 and not self.report.successful_queries:self.report.health='FAILED';raise ProviderUnavailable('Radar 5 search unavailable.')
            self.on_progress()
        if not self.report.candidates:self.report.health='DEGRADED';self.report.health_reasons.append('no_relevant_funding_program')
        self.report.metrics['collector_health']=self.report.health;return self.report.candidates
def has_explicit_eligibility(text):return any(x in folded(text) for x in ('eligible','peut candidater','apply','appel a projets'))
def has_strategic_scope(text):return any(x in folded(text) for x in ('patrimoine','developpement urbain','territorial','rehabilitation'))
