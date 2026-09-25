from app.integrations.openai.base import SearchProviderError
from app.integrations.openai.search import OpenAISearchProvider


def build_search_provider(config, purpose='procurement'):
    if config['SEARCH_PROVIDER'] != 'openai':
        raise SearchProviderError('unknown_search_provider')
    return OpenAISearchProvider(config['OPENAI_API_KEY'], config['OPENAI_SEARCH_MODEL'], purpose=purpose,
        max_output_tokens=config.get('AI_SEARCH_MAX_OUTPUT_TOKENS', 1600),
        max_evidence_chars=config.get('AI_MAX_SNIPPET_CHARS', 500))
