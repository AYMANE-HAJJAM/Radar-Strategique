from decimal import Decimal, InvalidOperation

from app.core.agent_schemas import TokenUsage


class CostService:
    """USD estimates; absent/unknown pricing or usage stays null, never guessed."""
    def __init__(self, prices=None):
        self.prices = prices or {}

    @classmethod
    def from_config(cls, config):
        names = ('INPUT', 'CACHED', 'OUTPUT')
        values = [config.get(f'OPENAI_{name}_PRICE_PER_MILLION', '') for name in names]
        if not all(value != '' for value in values):
            return cls()
        try:
            rates = tuple(Decimal(str(value)) for value in values)
            if any(not rate.is_finite() or rate < 0 for rate in rates):
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValueError('OpenAI prices must be finite nonnegative USD amounts.') from None
        return cls({config['OPENAI_MODEL']: rates})

    def estimate(self, model, usage: TokenUsage):
        rates = self.prices.get(model)
        if rates is None or not usage.available or usage.cached_tokens > usage.input_tokens:
            return None
        regular, cached, output = rates
        return ((usage.input_tokens - usage.cached_tokens) * regular + usage.cached_tokens * cached
                + usage.output_tokens * output) / Decimal(1000000)

    def record(self, run, model, usage, attempts=1, *, count_ai_call=True):
        usage = usage or TokenUsage(available=False)
        previous_calls = run.ai_calls
        if count_ai_call:
            run.ai_calls += attempts
            metadata = dict(run.run_metadata or {})
            metadata['classification_models'] = sorted(set(metadata.get('classification_models', [])) | ({model} if model else set()))
            metadata['classification_usage_complete'] = (metadata.get('classification_usage_complete', True)
                                                         and usage.available and attempts == 1)
            run.run_metadata = metadata
        run.input_tokens += usage.input_tokens
        run.output_tokens += usage.output_tokens
        run.cached_tokens += usage.cached_tokens
        estimate = self.estimate(model, usage) if attempts == 1 else None
        # A retried/failed request may be billable with no usage returned.
        if estimate is None or (previous_calls and run.estimated_ai_cost is None):
            run.estimated_ai_cost = None
        else:
            run.estimated_ai_cost = (run.estimated_ai_cost or Decimal(0)) + estimate
