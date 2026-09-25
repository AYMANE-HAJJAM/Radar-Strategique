import re
from urllib.parse import urljoin, urlsplit
from app.modules.radar4_policies.schemas import PolicyCandidate
from app.core.collector_base import sources_unchanged, CollectionReport, ProviderUnavailable, query_batches, run_source_adapters, paid_search_budget
from app.integrations.http.html import PublicPages, AccessLimitedPages
from app.modules.radar4_policies.policy import classify, parse_date, folded
from app.integrations.openai.base import SearchProviderError
from app.integrations.http.verification import VerificationPages
from app.modules.radar4_policies.status_verification import publication_evidence, apply_publication, instrument_sections, document_sections
from app.core.validation import today_in_morocco

QUERIES=('site:sgg.gov.ma projet loi urbanisme patrimoine','site:parlement.ma loi urbanisme foncier Maroc',
    'site:cese.ma étude patrimoine urbanisme','stratégie officielle aménagement territoire Maroc',
    'consultation publique réglementation bâtiment Maroc')
COUNTERS=('official_sources_checked','new_texts','updated_texts','laws','drafts','strategies','studies','search_calls','ai_calls','final_kept')

class PoliciesCollector:
    def __init__(self,provider,config,*,pages=None):
        self.provider,self.config=provider,config
        self.report=CollectionReport(metrics={**dict.fromkeys(COUNTERS,0),'collector_health':'HEALTHY'})
        self.domains=tuple(config.get('RADAR4_SOURCE_WHITELIST',())); self.official=tuple(config.get('RADAR4_OFFICIAL_DOMAINS',()))
        self.pages=AccessLimitedPages(pages or PublicPages(self.domains,config.get('SOURCE_HTTP_TIMEOUT_SECONDS',20)),{'http_403':0,'http_429':0})
        self.on_progress=lambda:None; self.known_unchanged=lambda candidate:False; self.seen=set()
        self.verification_pages=VerificationPages(self.domains,self.report.metrics,limit=min(8,config.get('RADAR4_DIRECT_SOURCE_LIMIT',8)))
        self.bo_documents=[]

    def _verify_status(self):
        from datetime import date
        # Only an extracted own-instrument reference is used; filenames are not proof.
        for index,item in enumerate(list(self.report.candidates)):
            if not item.reference_number and item.official_document_url and index<3:
                doc=self.verification_pages.get(item.official_document_url)
                if doc:
                    first=next(instrument_sections(doc['text'],include_drafts=True),None)
                    if first:
                        item=item.model_copy(update={'reference_number':first['reference'],'reference':first['reference']})
            proof=publication_evidence(item,self.bo_documents,today_in_morocco())
            item=apply_publication(item,proof,today_in_morocco()) if item.reference_number else item.model_copy(update={'publication_check':'MISSING_VERIFIED_REFERENCE'})
            if item.reference_number and not self.bo_documents:
                item=item.model_copy(update={'publication_check':'OFFICIAL_SOURCE_UNAVAILABLE'})
            self.report.candidates[index]=item;self.report.observations[index]=item
        self.report.metrics['publication_checks']=sum(bool(c.reference_number) for c in self.report.candidates)
        self.report.metrics['bulletins_checked']=len(self.bo_documents)
        self.report.metrics['bulletin_numbers']=[d.get('bo_number') for d in self.bo_documents]
        self.report.metrics['published_verified']=sum(c.publication_verified for c in self.report.candidates)
        self.report.metrics['in_force_verified']=sum(c.legal_status=='IN_FORCE' and c.publication_verified for c in self.report.candidates)
    def _official(self,url):
        host=(urlsplit(url).hostname or '').lower().removeprefix('www.')
        return any(host==d or host.endswith('.'+d) for d in self.official)
    def _candidate(self,title,url,evidence,institution=None,publication_date=None,*,draft_listing=False,document_type=None,listing_url=None):
        found=classify(title,evidence)
        if not found or not self._official(url):
            self.report.metrics['unrelated_or_nonofficial_rejected']=self.report.metrics.get('unrelated_or_nonofficial_rejected',0)+1
            return None
        dtype,status=found; published=parse_date(publication_date)
        if status=='IN_FORCE':
            # An HTML announcement is not a verified BO publication/effectiveness check.
            status='POLICY_SIGNAL'
        if draft_listing:
            dtype=document_type or dtype
            status='DRAFT'
        reference=(re.search(r'\b(?:loi|decret|décret|arrêté|arrete)\s+n?[°º]?\s*([\d.-]+)',title+' '+evidence,re.I))
        reference=reference.group(1) if reference else None
        # A modification's cited law is not necessarily the new text's identity.
        if not re.match(r'^(?:projet de |avant.projet de )?(?:loi|décret|decret|arrêté|arrete)\s',title,re.I):
            reference=None
        excerpt=' '.join(evidence.split())[:2000]
        return PolicyCandidate(title=title[:2000],url=url,source=(urlsplit(url).hostname or '')[:255],
            institution=institution or (urlsplit(url).hostname or ''),publication_date=published,source_status='active',
            source_quality='OFFICIAL_PRIMARY',current_evidence=True,morocco_related=True,document_type=dtype,
            verification_date=today_in_morocco(),status_source_url=listing_url or url,
            status_source_type='SGG_DRAFT_LIST' if draft_listing else 'OFFICIAL_PAGE',
            status_confidence=.95 if draft_listing else .8 if status!='POLICY_SIGNAL' else .3,
            legal_status=status,reported_status=status,reference_number=reference,reference=reference,
            scope=excerpt or title,official_url=url,official_document_url=url if url.lower().endswith('.pdf') else None,
            summary=((excerpt or title)[:1750] + ' — Version publiée comme projet ; adoption ultérieure et entrée en vigueur actuelles non vérifiées.') if draft_listing else (excerpt or title),
            business_implications='Potential implications for architecture, heritage or territorial planning require professional review.',
            reliable_status_evidence=status!='POLICY_SIGNAL',official_source=listing_url or url,status_evidence=excerpt or title,
            metadata={'source_type':'OFFICIAL','legal_status_evidence':excerpt or title,
                'status_scope':'Listed draft version; subsequent adoption/current effectiveness not verified' if draft_listing else 'Source evidence',
                'publication_date_verified':bool(published), 'listing_url':listing_url})
    def _add(self,item):
        if not item:return
        key=folded(item.reference_number or item.title)
        if key in self.seen or self.known_unchanged(item):return
        self.seen.add(key);self.report.candidates.append(item);self.report.observations.append(item)
        self.report.metrics['new_texts']+=1;self.report.metrics['final_kept']+=1
        self.report.metrics['laws']+=int(item.document_type in {'LAW','DECREE','ORDER','CIRCULAR'})
        self.report.metrics['drafts']+=int(item.legal_status in {'DRAFT','UNDER_PREPARATION','PUBLIC_CONSULTATION'})
        self.report.metrics['decrees']=self.report.metrics.get('decrees',0)+int(item.document_type=='DECREE')
        self.report.metrics['strategies']+=int(item.document_type in {'STRATEGY','PROGRAM','REGULATORY_REFORM'})
        self.report.metrics['studies']+=int(item.document_type in {'PUBLIC_STUDY','POLICY_STUDY'})
    def _direct(self):
        def consume(item, result):
            if item.get('parliamentary_stage'):
                candidate=self._candidate(item['title'],item['url'],item['evidence'],result.source.name,item.get('date'))
                if candidate:
                    candidate.metadata['parliamentary_stage']=item['parliamentary_stage']
                    candidate=candidate.model_copy(update={'reference_number':item['reference'],'reference':item['reference']})
                    if item['parliamentary_stage']=='PARLIAMENT_ADOPTED':
                        candidate=candidate.model_copy(update={'document_type':'LAW','legal_status':'ADOPTED',
                            'reported_status':'ADOPTED',
                            'reliable_status_evidence':True})
                    self._add(candidate)
                return
            if item.get('consolidated_lookup'):
                candidate=self._candidate(item['title'],item['url'],item['evidence'],'SGG')
                if candidate:
                    self.report.metrics['consolidated_references_checked']=self.report.metrics.get('consolidated_references_checked',0)+1
                    proof=publication_evidence(candidate,self.bo_documents,today_in_morocco())
                    if proof:self._add(apply_publication(candidate,proof,today_in_morocco()))
                return
            if item.get('bo_document'):
                from datetime import date
                doc=item.get('document') or self.verification_pages.get(item['url'])
                if doc:
                    if not item.get('document'):
                        doc.update(date=date.fromisoformat(item['date']),bo_number=item['reference'])
                    self.bo_documents.append(doc)
                    for section in document_sections(doc):
                        if len(self.report.candidates)>=self.config['RADAR4_DIRECT_SOURCE_LIMIT']:break
                        candidate=self._candidate(section['heading'][:900],doc['url'],section['heading'],'SGG',doc['date'])
                        if not candidate:continue
                        candidate=candidate.model_copy(update={'reference_number':section['reference'],'reference':section['reference'],
                            'document_type':section['document_type']})
                        proof=publication_evidence(candidate,[doc],today_in_morocco())
                        if proof:self._add(apply_publication(candidate,proof,today_in_morocco()))
                return
            if len(self.report.candidates)>=self.config['RADAR4_DIRECT_SOURCE_LIMIT']:return
            self._add(self._candidate(item.get('title') or result.source.name,
                item.get('url') or result.url, item.get('evidence') or item.get('title') or '',
                institution=result.source.name, publication_date=item.get('date'),
                draft_listing=item.get('draft_listing',False),document_type=item.get('document_type'),
                listing_url=item.get('listing_url')))
        run_source_adapters(self, consume)
        if getattr(self, 'source_adapters', None):
            return
        remaining=self.config['RADAR4_DIRECT_SOURCE_LIMIT']
        for feed in self.config.get('RADAR4_DIRECT_FEEDS',()):
            if remaining<=0:break
            try:
                base,page=self.pages.get(feed);self.report.metrics['official_sources_checked']+=1
                for href,label in page.links:
                    if remaining<=0:break
                    target=urljoin(base,href)
                    if self._official(target) and classify(label):
                        self._add(self._candidate(label,target,label,institution=(urlsplit(target).hostname or '')));remaining-=1
            except (OSError,ValueError,TimeoutError):pass
    def collect(self,radar):
        self._direct()
        self._verify_status()
        fetched=0
        fallback=paid_search_budget(self.config,4) if hasattr(self,'source_adapters') else self.config['RADAR4_SEARCH_MAX_CALLS']
        budget=0 if len(self.report.candidates)>=self.config.get('RADAR4_DIRECT_MIN_YIELD',1) else fallback
        if sources_unchanged(self.report): budget = 0
        self.report.metrics['escalation_level']=0 if budget==0 else 1
        queries=QUERIES[:min(self.config['RADAR4_SEARCH_MAX_CALLS'],budget)]
        for query,themes in query_batches(queries,self.config.get('RADAR4_SEARCH_BATCH_SIZE',3)):
            if len(self.report.candidates)>=self.config.get('RADAR4_TARGET_OBSERVATIONS',3):break
            self.report.metrics['search_calls'] += 1
            try:
                response=self.provider.search(query,recency_days=365,domains=self.domains)
                self.report.usage_events.append(response);self.report.queries_executed+=len(themes);self.report.successful_queries+=1
                for hit in response.hits:
                    item=self._candidate(hit.title,hit.url,hit.evidence,hit.institution,hit.publication_date)
                    if item is None and fetched<self.config.get('RADAR4_SEARCH_DETAIL_FETCH_LIMIT',10):
                        try:
                            final,detail=self.pages.get(hit.url);fetched+=1
                            item=self._candidate(' '.join(detail.h1).strip() or hit.title,final,detail.text,
                                hit.institution,hit.publication_date)
                        except (OSError,ValueError,TimeoutError):pass
                    self._add(item)
            except SearchProviderError as error:
                self.report.usage_events.append(error.response)
                self.report.query_errors.append({'query':query,'kind':error.kind})
                if len(self.report.query_errors)>=3 and not self.report.successful_queries:
                    self.report.health='FAILED';raise ProviderUnavailable('Radar 4 search unavailable.')
            self.on_progress()
        self.report.metrics['official_sources_checked']=len(self.report.metrics.get('source_health',{})) or self.report.metrics['official_sources_checked']
        if not self.report.candidates:self.report.health='DEGRADED';self.report.health_reasons.append('no_relevant_official_policy_text')
        elif any(v in {'FAILED','BLOCKED','COOLDOWN'} for v in self.report.metrics.get('source_health',{}).values()):
            self.report.health='PARTIAL';self.report.health_reasons.append('some_official_sources_unavailable')
        self.report.metrics['collector_health']=self.report.health;return self.report.candidates
