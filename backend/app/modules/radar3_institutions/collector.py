import re
from urllib.parse import urljoin, urlsplit

from app.modules.radar3_institutions.schemas import InstitutionCandidate
from app.core.collector_base import sources_unchanged, CollectionReport, ProviderUnavailable, query_batches, run_source_adapters, paid_search_budget
from app.integrations.http.html import PublicPages, AccessLimitedPages
from app.modules.radar3_institutions.policy import classify, parse_date, public_excerpt, folded, rejection_reason
from app.core.validation import today_in_morocco
from app.integrations.openai.base import SearchProviderError
from app.modules.radar3_institutions.leadership import RoleEvidence, resolve, extract, evidence_date
from app.integrations.http.verification import VerificationPages
from dataclasses import asdict

QUERIES = (
    'site:alomrane.gov.ma Al Omrane gouvernance directoire amenagement urbain',
    'site:culture.gov.ma ministere culture organisation direction patrimoine',
    'site:alomrane.gov.ma Al Omrane programme rehabilitation medina convention',
    'site:maroc.ma Al Omrane nomination direction programme urbanisme',
    'site:maroc.ma ministere culture direction patrimoine nomination officielle',
)
COUNTERS = ('institutions_checked', 'institutions_newly_discovered', 'institutions_updated',
    'decision_makers_identified', 'current_roles_verified', 'appointments_detected',
    'unchanged_skipped', 'search_calls', 'ai_calls', 'final_kept')


class InstitutionsCollector:
    def __init__(self, provider, config, *, pages=None):
        self.provider, self.config = provider, config
        self.report = CollectionReport(metrics={**dict.fromkeys(COUNTERS, 0), 'collector_health': 'HEALTHY'})
        self.domains = tuple(config.get('RADAR3_SOURCE_WHITELIST', ()))
        self.official = tuple(config.get('RADAR3_OFFICIAL_DOMAINS', ()))
        self.pages = AccessLimitedPages(pages or PublicPages(self.domains, config.get('SOURCE_HTTP_TIMEOUT_SECONDS', 20)), {'http_403': 0, 'http_429': 0})
        self.on_progress = lambda: None
        self.known_unchanged = lambda candidate: False
        self.source_recent = lambda url, days: False
        self.seen, self.seen_urls = set(), set()
        self.leadership_records = {}
        self.verification_pages = VerificationPages(self.domains,self.report.metrics,
            limit=min(8,config.get('RADAR3_INSTITUTION_FETCH_LIMIT',8)))

    def apply_leadership(self, profile, records):
        selected,status=resolve(records,today_in_morocco())
        history=[{**asdict(e),'evidence_date':e.evidence_date.isoformat() if e.evidence_date else None} for e in records]
        if status=='OBSOLETE':
            self.report.metrics['obsolete_role_rejected']=self.report.metrics.get('obsolete_role_rejected',0)+1
        confirmed=status=='VERIFIED_CURRENT'
        visible=selected if status in {'VERIFIED_CURRENT','PROBABLY_CURRENT'} else None
        label=(f'{selected.role_title} : {selected.person_name} — '
               +('rôle actuel vérifié' if confirmed else 'probablement actuel, non confirmé')) if visible else 'Responsable actuel non vérifié'
        return profile.model_copy(update={'person':None,'profile_type':'INSTITUTION',
            'activity_type':('LEADERSHIP_CHANGE' if selected and len({folded(e.person_name) for e in records})>1 else
                'NEW_APPOINTMENT' if selected and (selected.source_type=='APPOINTMENT' or selected.interim) else profile.activity_type),
            'person_name':visible.person_name if visible else None,'role_title':visible.role_title if visible else None,
            'current_status':status,'role_verified':confirmed,'role_verified_at':selected.evidence_date if confirmed else None,
            'role_source_url':selected.source_url if selected else None,'role_source_type':selected.source_type if selected else None,
            'evidence_date':selected.evidence_date if selected else None,'verification_date':today_in_morocco(),
            'verification_confidence':.95 if confirmed else .65 if visible else 0,
            'role_evidence':history,'decision_makers':[label] if visible else [],
            'position':visible.role_title if visible else None,
            'title':(profile.institution_name+' — '+label)[:2000],
            'recent_activity':(label+' | '+(profile.mission or profile.architecture_heritage_relevance))[:2000],
            'leadership_limitation':None if confirmed else label})

    def _verify_leadership(self):
        for index,profile in enumerate(list(self.report.candidates)):
            records=self.leadership_records.get(profile.institution_name,[])
            if not records:continue
            # Undated governance is cross-checked against a bounded official activity snapshot.
            for link in getattr(self,'activity_links',[])[:3]:
                doc=self.verification_pages.get(link)
                if not doc:continue
                text=doc['text']; dated=evidence_date(text)
                names={folded(r.person_name) for r in records}
                found=extract(text,profile.institution_name,doc['url'],'OFFICIAL_RELEASE',dated)
                records.extend(e for e in found if folded(e.person_name) in names)
            updated=self.apply_leadership(profile,records)
            self.report.candidates[index]=updated
            self.report.observations[index]=updated
        for status in ('VERIFIED_CURRENT','PROBABLY_CURRENT','UNVERIFIED','OBSOLETE'):
            self.report.metrics[status.lower()]=sum(c.current_status==status for c in self.report.candidates)
        self.report.metrics['current_roles_verified']=sum(c.role_verified for c in self.report.candidates)
        self.report.metrics['appointments_detected']=sum(c.activity_type in {'NEW_APPOINTMENT','LEADERSHIP_CHANGE','NEW_RESPONSIBILITY'} for c in self.report.candidates)

    def _official(self, url):
        host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
        return any(host == d or host.endswith('.' + d) for d in self.official)

    def _candidate(self, title, url, evidence, institution=None, publication_date=None, location=None, *, profile_evidence=False):
        self.report.metrics['institutions_checked'] += int(bool(institution))
        reason = rejection_reason(title, evidence)
        if reason:
            self.report.metrics[reason + '_rejected'] = self.report.metrics.get(reason + '_rejected', 0) + 1
            return None
        published = parse_date(publication_date)
        facts = classify(title + ' ' + evidence, published)
        generic = ('portail officiel' in folded(institution or '') or
                   folded(institution or '').startswith('acteurs publics'))
        if not facts['relevant'] or facts['obsolete'] or not institution or generic:
            return None
        official = self._official(url)
        excerpt = public_excerpt(evidence)
        person = None
        match = re.search(r'\b(?:M(?:me)?\.?\s+)?([A-ZÀ-ÖØ-Ý][\wÀ-ÿ-]+(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ-]+){1,3})\s+'
                          r'(?:a été\s+)?(?:nommé|nommée|a présidé|a preside|préside|preside)', evidence)
        if match:
            person = match.group(1).strip()
        role = facts['role_type'] if person else None
        verified = bool(person and official and published and facts['current'] and role)
        if person and not verified:
            key = 'obsolete_role_rejected' if published and not facts['current'] else 'officeholders_unverified'
            self.report.metrics[key] = self.report.metrics.get(key, 0) + 1
            return None
        meaningful = facts['activity_type'] != 'CURRENT_PROFILE'
        if not person and not (official and profile_evidence) and not (meaningful and facts['current']):
            self.report.metrics['generic_article_rejected'] = self.report.metrics.get('generic_article_rejected', 0) + 1
            return None
        profile = 'PERSON' if person else 'INSTITUTION'
        if not person:
            self.report.metrics['officeholders_unverified'] = self.report.metrics.get('officeholders_unverified', 0) + 1
        result_type = ('NEW_APPOINTMENT' if facts['activity_type'] == 'NEW_APPOINTMENT' else
            'CURRENT_DECISION_MAKER' if person else 'INSTITUTION_PROFILE' if profile_evidence else
            {'PROGRAM_LAUNCH': 'NEW_PROGRAM', 'PARTNERSHIP': 'NEW_PARTNERSHIP',
             'LEADERSHIP_CHANGE': 'ROLE_CHANGE'}.get(facts['activity_type'], 'NEW_STRATEGIC_ACTIVITY'))
        return InstitutionCandidate(title=title[:2000], url=url, source=(urlsplit(url).hostname or '')[:255],
            institution=institution[:255], publication_date=published, source_status='active',
            morocco_related=True, source_quality='OFFICIAL_PRIMARY' if official else 'RELIABLE_SECONDARY',
            current_evidence=facts['current'], profile_type=profile, institution_name=institution[:500],
            city_region=location, architecture_heritage_relevance=excerpt,
            recent_activity=excerpt if person else (excerpt[:1940] + ' — Responsable actuel non vérifié'),
            recent_activity_date=published, activity_type=facts['activity_type'], person=person,
            result_type=result_type, mission=excerpt if profile_evidence else None,
            leadership_limitation=None if person else 'Responsable actuel non vérifié',
            verification_confidence=.95 if verified else None,
            position=role.replace('_', ' ').title() if role else None, role_type=role,
            responsibility_scope=excerpt if person else None, official_source=url if official else None,
            professional_source=None if official else url, official_site=url if official else None,
            role_verified=verified, role_verified_at=published if verified else None,
            current_status='VERIFIED_CURRENT' if verified else 'UNVERIFIED',
            verification_date=today_in_morocco(), institution_relevant=True,
            obsolete_holder=False, nomination_unconfirmed=bool(person and not verified),
            public_professional_only=True, metadata={'source_type': 'OFFICIAL' if official else 'SECONDARY',
                'official_profile_evidence': bool(profile_evidence and official)})

    def _identity(self, item):
        return (folded(item.person) + '|' + folded(item.institution_name) if item.person else
                folded(item.institution_name) + '|' + (urlsplit(item.official_site or item.url).hostname or '').lower())

    def _add(self, item):
        if not item: return
        key = self._identity(item)
        if key in self.seen or (item.profile_type == 'INSTITUTION' and item.url in self.seen_urls) or self.known_unchanged(item):
            self.report.metrics['unchanged_skipped'] += 1
            return
        self.seen.add(key)
        self.seen_urls.add(item.url)
        self.report.candidates.append(item); self.report.observations.append(item)
        self.report.metrics['final_kept'] += 1
        self.report.metrics['institutions_newly_discovered'] += int(item.profile_type == 'INSTITUTION')
        self.report.metrics['decision_makers_identified'] += int(item.profile_type == 'PERSON')
        self.report.metrics['current_roles_verified'] += int(item.role_verified)
        self.report.metrics['appointments_detected'] += int(item.activity_type == 'NEW_APPOINTMENT')

    def _direct(self):
        def consume(item, result):
            if 'role_records' in item:
                candidate=self._candidate(item['title'],item['url'],item['evidence'],item['institution'],profile_evidence=True)
                if candidate:
                    records=[RoleEvidence(**{**r,'evidence_date':parse_date(r['evidence_date'])}) for r in item['role_records']]
                    self.leadership_records.setdefault(candidate.institution_name,[]).extend(records)
                    candidate=self.apply_leadership(candidate,records)
                    candidate.metadata['normalized_role']=item.get('normalized_role')
                    self._add(candidate)
                return
            if result.source.name=='Morocco appointments' and '/actualites/' in (item.get('url') or '') and any(t in folded(item.get('title','')) for t in ('urbanisme','culture','patrimoine','nomination')):
                self.activity_links=getattr(self,'activity_links',[])+[item.get('url')]
            signal = folded((item.get('title') or '') + ' ' + (item.get('evidence') or ''))
            if not item.get('profile_evidence') and not any(term in signal for term in ('nomm', 'directeur', 'directrice', 'president',
                    'gouvernance', 'organigramme', 'convention', 'programme')):
                return
            candidate=self._candidate(item.get('title') or result.source.name,
                item.get('url') or result.url, item.get('evidence') or item.get('title') or '',
                item.get('institution') or result.source.name, item.get('date'),
                profile_evidence=item.get('profile_evidence', False))
            if candidate and item.get('person_name'):
                record=RoleEvidence(item['person_name'],item['role_title'],candidate.institution_name,
                    item['url'],item.get('source_type','GOVERNANCE'),None,item['evidence'])
                self.leadership_records.setdefault(candidate.institution_name,[]).append(record)
            self._add(candidate)
        run_source_adapters(self, consume)
        if getattr(self, 'source_adapters', None):
            return
        limit = self.config['RADAR3_INSTITUTION_FETCH_LIMIT']
        for feed in self.config.get('RADAR3_DIRECT_FEEDS', ()):
            try:
                base, page = self.pages.get(feed)
                links = [(urljoin(base, href), label.strip()) for href, label in page.links
                         if len(label.strip()) > 25 and any(k in folded(label) for k in
                         ('patrimoine', 'urbanisme', 'rehabilitation', 'amenagement', 'nomination', 'programme'))]
                for url, label in list(dict.fromkeys(links))[:limit]:
                    if self.source_recent(url, self.config.get('RADAR3_REFRESH_STABLE_DAYS', 30)):
                        continue
                    try:
                        final, detail = self.pages.get(url)
                        institution = next((x for x in ('Ministère de la Culture', 'Al Omrane', 'Agence urbaine')
                                            if folded(x) in folded(detail.text)), 'Institution publique')
                        self._add(self._candidate(' '.join(detail.h1).strip() or label, final, detail.text,
                                                  institution=institution))
                    except (OSError, ValueError, TimeoutError): pass
            except (OSError, ValueError, TimeoutError): pass

    def collect(self, radar):
        self._direct()
        self._verify_leadership()
        fetched = 0
        fallback = paid_search_budget(self.config, 3) if hasattr(self, 'source_adapters') else self.config['RADAR3_SEARCH_MAX_CALLS']
        budget = 0 if len(self.report.candidates) >= self.config.get('RADAR3_DIRECT_MIN_YIELD', 1) else fallback
        if sources_unchanged(self.report): budget = 0
        self.report.metrics['escalation_level'] = 0 if budget == 0 else 1
        queries = QUERIES[:min(self.config['RADAR3_SEARCH_MAX_CALLS'], budget)]
        for query, themes in query_batches(queries, self.config.get('RADAR3_SEARCH_BATCH_SIZE', 3)):
            if len(self.report.candidates) >= self.config.get('RADAR3_TARGET_OBSERVATIONS', 4):
                break
            self.report.metrics['search_calls'] += 1
            try:
                response = self.provider.search(query, recency_days=180, domains=self.domains)
                self.report.usage_events.append(response); self.report.queries_executed += len(themes)
                self.report.successful_queries += 1
                for hit in response.hits:
                    item = self._candidate(hit.title, hit.url, hit.evidence, hit.institution,
                                           hit.publication_date, hit.location)
                    if item is None and fetched < self.config.get('RADAR3_SEARCH_DETAIL_FETCH_LIMIT', 10):
                        try:
                            final, detail = self.pages.get(hit.url); fetched += 1
                            institution = hit.institution or (urlsplit(final).hostname or '')
                            item = self._candidate(' '.join(detail.h1).strip() or hit.title, final,
                                detail.text, institution, hit.publication_date, hit.location)
                        except (OSError, ValueError, TimeoutError):
                            pass
                    self._add(item)
            except SearchProviderError as error:
                self.report.usage_events.append(error.response)
                self.report.query_errors.append({'query': query, 'kind': error.kind})
                if len(self.report.query_errors) >= 3 and not self.report.successful_queries:
                    self.report.health = 'FAILED'; raise ProviderUnavailable('Radar 3 search unavailable.')
            self.on_progress()
        if not self.report.candidates:
            self.report.health = 'DEGRADED'; self.report.health_reasons.append('no_relevant_institutional_activity')
        elif any(v in {'FAILED', 'BLOCKED', 'COOLDOWN'} for v in self.report.metrics.get('source_health', {}).values()):
            self.report.health = 'PARTIAL'; self.report.health_reasons.append('some_official_sources_unavailable')
        self.report.metrics['collector_health'] = self.report.health
        return self.report.candidates
