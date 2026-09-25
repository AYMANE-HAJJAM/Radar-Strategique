import os
import json
from pathlib import Path

from dotenv import load_dotenv


def load_config():
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    url = os.getenv('DATABASE_URL', '')
    def positive(name, default):
        value = int(os.getenv(name, str(default)))
        if value < 1:
            raise ValueError(f'{name} must be positive.')
        return value
    def nonnegative(name, default=0):
        value = int(os.getenv(name, str(default)))
        if value < 0:
            raise ValueError(f'{name} must be zero or positive.')
        return value
    def confidence(number):
        manual = float(os.getenv(f'RADAR{number}_MANUAL_REVIEW_CONFIDENCE', '0.55'))
        automatic = float(os.getenv(f'RADAR{number}_AUTO_ACCEPT_CONFIDENCE', '0.80'))
        if not 0 <= manual <= automatic <= 1:
            raise ValueError(f'RADAR{number} confidence must satisfy 0 <= manual <= auto <= 1.')
        return {'auto_accept': automatic, 'manual_review': manual}
    def sources(name, defaults):
        value = os.getenv(name)
        if not value:
            return defaults
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError(f'{name} must be a JSON list.')
        return tuple(parsed)
    from app.core.source_catalog import DEFAULT_SOURCES
    for prefix in ('postgres://', 'postgresql://'):
        if url.startswith(prefix):
            url = 'postgresql+psycopg://' + url[len(prefix):]
    return dict(
        SECRET_KEY=os.getenv('SECRET_KEY'),
        FLASK_ENV=os.getenv('FLASK_ENV', 'development'),
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True, 'connect_args': {'connect_timeout': 5}},
        FRONTEND_URL=os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV', 'development') == 'production',
        SESSION_COOKIE_SAMESITE='None' if os.getenv('FLASK_ENV', 'development') == 'production' else 'Lax',
        OPENAI_API_KEY=os.getenv('OPENAI_API_KEY', ''),
        OPENAI_MODEL=os.getenv('OPENAI_MODEL_DEFAULT') or os.getenv('OPENAI_MODEL', 'gpt-5.6-luna'),
        OPENAI_MODEL_ESCALATION=os.getenv('OPENAI_MODEL_ESCALATION', 'gpt-5.6-sol'),
        RADAR_MODELS={f'RADAR_{number}_{suffix}': (os.getenv(f'RADAR{number}_MODEL') or
            os.getenv('OPENAI_MODEL_DEFAULT') or os.getenv('OPENAI_MODEL', 'gpt-5.6-luna'))
            for number, suffix in enumerate(('MARKETS', 'PROJECTS', 'INSTITUTIONS', 'POLICIES', 'FUNDING'), 1)},
        OPENAI_INPUT_PRICE_PER_MILLION=os.getenv('OPENAI_INPUT_PRICE_PER_MILLION', ''),
        OPENAI_CACHED_PRICE_PER_MILLION=os.getenv('OPENAI_CACHED_PRICE_PER_MILLION', ''),
        OPENAI_OUTPUT_PRICE_PER_MILLION=os.getenv('OPENAI_OUTPUT_PRICE_PER_MILLION', ''),
        AGENT_MAX_CANDIDATES=200,
        SEARCH_RUN_STALE_MINUTES=positive('SEARCH_RUN_STALE_MINUTES', 120),
        SOURCE_HTTP_TIMEOUT_SECONDS=positive('SOURCE_HTTP_TIMEOUT_SECONDS', 20),
        MAX_DAILY_SEARCH_CALLS=nonnegative('MAX_DAILY_SEARCH_CALLS'),
        MAX_DAILY_AI_CALLS=nonnegative('MAX_DAILY_AI_CALLS'),
        SEARCH_PROVIDER=os.getenv('SEARCH_PROVIDER', 'openai'),
        OPENAI_SEARCH_MODEL=os.getenv('OPENAI_SEARCH_MODEL') or os.getenv('OPENAI_MODEL', 'gpt-5.6-luna'),
        AI_MAX_SOURCE_CHARS=positive('AI_MAX_SOURCE_CHARS', 2400),
        AI_MAX_SNIPPET_CHARS=positive('AI_MAX_SNIPPET_CHARS', 500),
        AI_MAX_EVIDENCE_ITEMS=positive('AI_MAX_EVIDENCE_ITEMS', 4),
        AI_CLASSIFICATION_MAX_OUTPUT_TOKENS=positive('AI_CLASSIFICATION_MAX_OUTPUT_TOKENS', 500),
        AI_SEARCH_MAX_OUTPUT_TOKENS=positive('AI_SEARCH_MAX_OUTPUT_TOKENS', 1600),
        TARGETED_SEARCH_MAX_CALLS=positive('TARGETED_SEARCH_MAX_CALLS', 2),
        RADAR1_MAX_QUERIES_PER_RUN=positive('RADAR1_MAX_QUERIES_PER_RUN', 12),
        RADAR1_DISCOVERY_MAX_CALLS=nonnegative('RADAR1_DISCOVERY_MAX_CALLS', 10),
        RADAR1_RESOLUTION_MAX_CALLS=nonnegative('RADAR1_RESOLUTION_MAX_CALLS', 5),
        RADAR1_NORMAL_SEARCH_BUDGET=nonnegative('RADAR1_NORMAL_SEARCH_BUDGET', 2),
        RADAR1_NORMAL_RESOLUTION_BUDGET=nonnegative('RADAR1_NORMAL_RESOLUTION_BUDGET', 2),
        RADAR1_DIRECT_DISCOVERY_ENABLED=os.getenv('RADAR1_DIRECT_DISCOVERY_ENABLED', 'true').lower() == 'true',
        RADAR1_MIN_SEARCH_QUERIES=nonnegative('RADAR1_MIN_SEARCH_QUERIES', 6),
        RADAR1_AI_ENABLED=os.getenv('RADAR1_AI_ENABLED', 'false').lower(),
        RADAR1_TARGET_OBSERVATIONS=positive('RADAR1_TARGET_OBSERVATIONS', 15),
        RADAR1_MAX_RESOLUTION_QUERIES=positive('RADAR1_MAX_RESOLUTION_QUERIES', 4),
        RADAR1_TARGET_UNIQUE_OBSERVATIONS=positive('RADAR1_TARGET_UNIQUE_OBSERVATIONS', 15),
        RADAR1_MIN_PRODUCTIVE_FAMILIES=positive('RADAR1_MIN_PRODUCTIVE_FAMILIES', 4),
        RADAR1_SEARCH_MODE=os.getenv('RADAR1_SEARCH_MODE', 'normal_coverage'),
        RADAR1_ZERO_YIELD_QUERY_LIMIT=positive('RADAR1_ZERO_YIELD_QUERY_LIMIT', 4),
        RADAR1_QUERY_OBSERVATION_LIMIT=positive('RADAR1_QUERY_OBSERVATION_LIMIT', 20),
        RADAR1_MAX_CANDIDATES=positive('RADAR1_MAX_CANDIDATES', 100),
        RADAR1_MAX_AI_ANALYSES=positive('RADAR1_MAX_AI_ANALYSES', 40),
        RADAR1_MIN_DISCOVERIES=positive('RADAR1_MIN_DISCOVERIES', 10),
        RADAR1_SOURCE_WHITELIST=tuple(d.strip().lower() for d in os.getenv('RADAR1_SOURCE_WHITELIST', 'marchespublics.gov.ma,cpmaroc.com,marchefacile.ma,borjmarchepublic.ma,marchesfaciles.ma,culture.gov.ma,alomrane.gov.ma').split(',') if d.strip()),
        RADAR1_AGGREGATOR_DOMAINS=tuple(d.strip().lower() for d in os.getenv('RADAR1_AGGREGATOR_DOMAINS', 'cpmaroc.com,marchefacile.ma,borjmarchepublic.ma,marchesfaciles.ma').split(',') if d.strip()),
        RADAR1_DISCOVERY_DOMAINS=tuple(d.strip().lower() for d in os.getenv('RADAR1_DISCOVERY_DOMAINS', '').split(',') if d.strip()),
        RADAR1_KEYWORD_GROUPS=json.loads(os.getenv('RADAR1_KEYWORD_GROUPS', '{}')),
        MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD=positive('MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD', 20_000_000),
        RADAR1_OFFICIAL_DOMAINS=tuple(domain.strip().lower() for domain in os.getenv('RADAR1_OFFICIAL_DOMAINS', 'culture.gov.ma,alomrane.gov.ma').split(',') if domain.strip()),
        RADAR2_DISCOVERY_MAX_SEARCHES=positive('RADAR2_DISCOVERY_MAX_SEARCHES', 6),
        RADAR2_NORMAL_SEARCH_BUDGET=nonnegative('RADAR2_NORMAL_SEARCH_BUDGET', 2),
        RADAR2_DIRECT_MIN_YIELD=positive('RADAR2_DIRECT_MIN_YIELD', 2),
        RADAR2_AI_ENABLED=os.getenv('RADAR2_AI_ENABLED', 'conditional').lower(),
        RADAR2_SEARCH_BATCH_SIZE=positive('RADAR2_SEARCH_BATCH_SIZE', 1),
        RADAR2_SEARCH_DETAIL_FETCH_LIMIT=positive('RADAR2_SEARCH_DETAIL_FETCH_LIMIT', 10),
        RADAR2_RESOLUTION_MAX_SEARCHES=positive('RADAR2_RESOLUTION_MAX_SEARCHES', 4),
        RADAR2_AI_MAX_CALLS=positive('RADAR2_AI_MAX_CALLS', 4),
        RADAR2_TARGET_OBSERVATIONS=positive('RADAR2_TARGET_OBSERVATIONS', 12),
        RADAR2_SOURCE_REFRESH_DAYS=positive('RADAR2_SOURCE_REFRESH_DAYS', 7),
        RADAR2_DIRECT_PAGE_LIMIT=positive('RADAR2_DIRECT_PAGE_LIMIT', 12),
        RADAR2_SOURCE_WHITELIST=tuple(d.strip().lower() for d in os.getenv('RADAR2_SOURCE_WHITELIST', 'maroc.ma,culture.gov.ma,alomrane.gov.ma,micepp.gov.ma,interieur.gov.ma,mapnews.ma').split(',') if d.strip()),
        RADAR2_OFFICIAL_DOMAINS=tuple(d.strip().lower() for d in os.getenv('RADAR2_OFFICIAL_DOMAINS', 'maroc.ma,culture.gov.ma,alomrane.gov.ma,micepp.gov.ma,interieur.gov.ma').split(',') if d.strip()),
        RADAR2_SECONDARY_DOMAINS=tuple(d.strip().lower() for d in os.getenv('RADAR2_SECONDARY_DOMAINS', 'mapnews.ma').split(',') if d.strip()),
        RADAR2_DIRECT_FEEDS=tuple(u.strip() for u in os.getenv('RADAR2_DIRECT_FEEDS', 'https://www.maroc.ma/fr/actualites').split(',') if u.strip()),
        RADAR2_SOURCES=sources('RADAR2_SOURCES', DEFAULT_SOURCES['RADAR_2_PROJECTS']),
        RADAR3_INSTITUTION_FETCH_LIMIT=positive('RADAR3_INSTITUTION_FETCH_LIMIT', 12),
        RADAR3_SEARCH_MAX_CALLS=positive('RADAR3_SEARCH_MAX_CALLS', 5),
        RADAR3_NORMAL_SEARCH_BUDGET=nonnegative('RADAR3_NORMAL_SEARCH_BUDGET', 1),
        RADAR3_DIRECT_MIN_YIELD=positive('RADAR3_DIRECT_MIN_YIELD', 1),
        RADAR3_AI_ENABLED=os.getenv('RADAR3_AI_ENABLED', 'conditional').lower(),
        RADAR3_SEARCH_BATCH_SIZE=positive('RADAR3_SEARCH_BATCH_SIZE', 1),
        RADAR3_SEARCH_DETAIL_FETCH_LIMIT=positive('RADAR3_SEARCH_DETAIL_FETCH_LIMIT', 10),
        RADAR3_AI_MAX_CALLS=positive('RADAR3_AI_MAX_CALLS', 4),
        RADAR3_TARGET_OBSERVATIONS=positive('RADAR3_TARGET_OBSERVATIONS', 4),
        RADAR3_REFRESH_HIGH_DAYS=positive('RADAR3_REFRESH_HIGH_DAYS', 7),
        RADAR3_REFRESH_STABLE_DAYS=positive('RADAR3_REFRESH_STABLE_DAYS', 30),
        RADAR3_SOURCE_WHITELIST=tuple(d.strip().lower() for d in os.getenv('RADAR3_SOURCE_WHITELIST', 'maroc.ma,culture.gov.ma,interieur.gov.ma,micepp.gov.ma,alomrane.gov.ma,fnm.ma,auejsb.ma,mjcc.gov.ma,auf.org.ma,mapnews.ma').split(',') if d.strip()),
        RADAR3_OFFICIAL_DOMAINS=tuple(d.strip().lower() for d in os.getenv('RADAR3_OFFICIAL_DOMAINS', 'maroc.ma,culture.gov.ma,interieur.gov.ma,micepp.gov.ma,alomrane.gov.ma,fnm.ma,auejsb.ma,mjcc.gov.ma,auf.org.ma').split(',') if d.strip()),
        RADAR3_DIRECT_FEEDS=tuple(u.strip() for u in os.getenv('RADAR3_DIRECT_FEEDS', 'https://www.maroc.ma/fr/actualites').split(',') if u.strip()),
        RADAR3_SOURCES=sources('RADAR3_SOURCES', DEFAULT_SOURCES['RADAR_3_INSTITUTIONS']),
        RADAR4_DIRECT_SOURCE_LIMIT=positive('RADAR4_DIRECT_SOURCE_LIMIT', 12),
        RADAR4_SEARCH_MAX_CALLS=positive('RADAR4_SEARCH_MAX_CALLS', 5),
        RADAR4_NORMAL_SEARCH_BUDGET=nonnegative('RADAR4_NORMAL_SEARCH_BUDGET', 1),
        RADAR4_DIRECT_MIN_YIELD=positive('RADAR4_DIRECT_MIN_YIELD', 1),
        RADAR4_AI_ENABLED=os.getenv('RADAR4_AI_ENABLED', 'conditional').lower(),
        RADAR4_SEARCH_BATCH_SIZE=positive('RADAR4_SEARCH_BATCH_SIZE', 1),
        RADAR4_SEARCH_DETAIL_FETCH_LIMIT=positive('RADAR4_SEARCH_DETAIL_FETCH_LIMIT', 10),
        RADAR4_AI_MAX_CALLS=positive('RADAR4_AI_MAX_CALLS', 4),
        RADAR4_TARGET_OBSERVATIONS=positive('RADAR4_TARGET_OBSERVATIONS', 3),
        RADAR4_SOURCE_WHITELIST=tuple(d.strip().lower() for d in os.getenv('RADAR4_SOURCE_WHITELIST', 'sgg.gov.ma,maroc.ma,parlement.ma,chambredesrepresentants.ma,cese.ma,hcp.ma,culture.gov.ma,aut.gov.ma').split(',') if d.strip()),
        RADAR4_OFFICIAL_DOMAINS=tuple(d.strip().lower() for d in os.getenv('RADAR4_OFFICIAL_DOMAINS', 'sgg.gov.ma,maroc.ma,parlement.ma,chambredesrepresentants.ma,cese.ma,hcp.ma,culture.gov.ma,aut.gov.ma').split(',') if d.strip()),
        RADAR4_DIRECT_FEEDS=tuple(u.strip() for u in os.getenv('RADAR4_DIRECT_FEEDS', 'https://www.sgg.gov.ma/Legislation/ListeAvant-projets.aspx,https://www.maroc.ma/fr/actualites').split(',') if u.strip()),
        RADAR4_SOURCES=sources('RADAR4_SOURCES', DEFAULT_SOURCES['RADAR_4_POLICIES']),
        RADAR5_DIRECT_SOURCE_LIMIT=positive('RADAR5_DIRECT_SOURCE_LIMIT', 12),
        RADAR5_SEARCH_MAX_CALLS=positive('RADAR5_SEARCH_MAX_CALLS', 6),
        RADAR5_NORMAL_SEARCH_BUDGET=nonnegative('RADAR5_NORMAL_SEARCH_BUDGET', 2),
        RADAR5_DIRECT_MIN_YIELD=positive('RADAR5_DIRECT_MIN_YIELD', 2),
        RADAR5_AI_ENABLED=os.getenv('RADAR5_AI_ENABLED', 'conditional').lower(),
        RADAR5_SEARCH_BATCH_SIZE=positive('RADAR5_SEARCH_BATCH_SIZE', 1),
        RADAR5_SEARCH_DETAIL_FETCH_LIMIT=positive('RADAR5_SEARCH_DETAIL_FETCH_LIMIT', 10),
        RADAR5_AI_MAX_CALLS=positive('RADAR5_AI_MAX_CALLS', 4),
        RADAR5_TARGET_OBSERVATIONS=positive('RADAR5_TARGET_OBSERVATIONS', 12),
        **{f'RADAR{number}_MAX_INPUT_TOKENS_PER_RUN': positive(
            f'RADAR{number}_MAX_INPUT_TOKENS_PER_RUN', 20000 if number > 1 else 15000)
           for number in range(1, 6)},
        RADAR5_SOURCE_WHITELIST=tuple(d.strip().lower() for d in os.getenv('RADAR5_SOURCE_WHITELIST', 'worldbank.org,search.worldbank.org,afdb.org,eib.org,ebrd.com,afd.fr,europa.eu,kfw-entwicklungsbank.de,un.org,undp.org,maroc.ma').split(',') if d.strip()),
        RADAR5_DIRECT_FEEDS=tuple(u.strip() for u in os.getenv('RADAR5_DIRECT_FEEDS', 'https://www.worldbank.org/en/country/morocco/projects,https://www.afdb.org/en/countries/north-africa/morocco').split(',') if u.strip()),
        RADAR5_SOURCES=sources('RADAR5_SOURCES', DEFAULT_SOURCES['RADAR_5_FUNDING']),
        RADAR_CONFIDENCE={f'RADAR_{number}_{suffix}': confidence(number)
            for number, suffix in enumerate(('MARKETS', 'PROJECTS', 'INSTITUTIONS', 'POLICIES', 'FUNDING'), 1)},
    )
