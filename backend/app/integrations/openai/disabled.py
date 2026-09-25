from app.integrations.openai.base import SearchProviderError


class DisabledSearchProvider:
    def search(self, *args, **kwargs):
        raise SearchProviderError('paid_search_disabled')
