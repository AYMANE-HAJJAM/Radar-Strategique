class AgentError(RuntimeError):
    kind = 'unexpected'


class ActiveRunError(AgentError):
    kind = 'active_run'


class CollectorError(AgentError):
    kind = 'collector'


class InvalidCandidateError(AgentError):
    kind = 'invalid_candidate'


class OpenAIServiceError(AgentError):
    kind = 'openai'

    def __init__(self, message, *, usage=None, model=None, attempts=0):
        super().__init__(message)
        self.usage = usage
        self.model = model
        self.attempts = attempts


class OpenAITimeoutError(OpenAIServiceError):
    kind = 'openai_timeout'


class OpenAIRateLimitError(OpenAIServiceError):
    kind = 'openai_rate_limit'


class InvalidAnalysisError(OpenAIServiceError):
    kind = 'invalid_analysis'
