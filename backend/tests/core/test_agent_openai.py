from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from openai import APITimeoutError, RateLimitError

from backend.app.core.agent_errors import InvalidAnalysisError, OpenAITimeoutError, OpenAIRateLimitError
from backend.app.core.agent_schemas import Candidate
from backend.app.core.radar_registry import RADARS
from backend.app.integrations.openai.client import OpenAIService
from backend.scripts.test_agent import MockAnalyzer


def sdk_response():
    return SimpleNamespace(status='completed', model='gpt-5.6-luna',
                           output_parsed=MockAnalyzer().analyze_candidate(None, None).analysis,
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                                                 input_tokens_details=SimpleNamespace(cached_tokens=10)))


def test_candidate_request_is_stateless_and_tracks_usage():
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        client = sdk.return_value.__enter__.return_value
        client.responses.parse.return_value = sdk_response()
        response = OpenAIService('test').analyze_candidate(Candidate(title='Example'), RADARS['RADAR_1_MARKETS'].get_analysis_context())
        kwargs = client.responses.parse.call_args.kwargs
    assert response.usage.cached_tokens == 10 and response.usage.input_tokens == 100
    assert kwargs['store'] is False
    assert not {'tools', 'previous_response_id', 'conversation'} & kwargs.keys()
    assert 'RADAR_1_MARKETS' in kwargs['instructions']
    assert sdk.call_args.kwargs['max_retries'] == 0


@pytest.mark.parametrize('kind', ['timeout', 'rate_limit'])
def test_transient_errors_retry_exactly_three_times(kind):
    request = httpx.Request('POST', 'https://example.com')
    error = APITimeoutError(request=request) if kind == 'timeout' else RateLimitError(
        'limited', response=httpx.Response(429, request=request), body=None)
    expected = OpenAITimeoutError if kind == 'timeout' else OpenAIRateLimitError
    sleep = Mock()
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        client = sdk.return_value.__enter__.return_value
        client.responses.parse.side_effect = error
        with pytest.raises(expected) as failure:
            OpenAIService('test', sleep=sleep).analyze_candidate(Candidate(title='Example'), RADARS['RADAR_1_MARKETS'].get_analysis_context())
        assert client.responses.parse.call_count == 3
    assert failure.value.attempts == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_invalid_output_is_not_retried_and_usage_survives():
    response = sdk_response()
    response.output_parsed = None
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        client = sdk.return_value.__enter__.return_value
        client.responses.parse.return_value = response
        with pytest.raises(InvalidAnalysisError) as error:
            OpenAIService('test').analyze_candidate(Candidate(title='Example'), RADARS['RADAR_1_MARKETS'].get_analysis_context())
        assert client.responses.parse.call_count == 1
    assert error.value.usage.input_tokens == 100
