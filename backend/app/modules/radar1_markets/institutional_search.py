from urllib.parse import urlsplit


def official_institution(url, configured_domains=()):
    host = (urlsplit(url).hostname or '').lower()
    from app.modules.radar1_markets.policy import DEFAULT_WHITELIST, DEFAULT_AGGREGATORS, domain_match
    return domain_match(url, tuple(d for d in (configured_domains or DEFAULT_WHITELIST) if d not in DEFAULT_AGGREGATORS))
