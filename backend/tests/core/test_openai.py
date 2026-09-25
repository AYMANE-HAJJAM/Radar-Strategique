from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError

from backend.app.integrations.openai.client import Analysis, OpenAIService, OpenAIServiceError


def test_structured_analysis_request():
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(
        status='completed', output_parsed=Analysis(relevant=True, category='funding', summary='Résumé.', score=80))
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        sdk.return_value.__enter__.return_value = client
        result = OpenAIService('test-key', 'custom-model').analyze_text('Programme PME')
    assert result == {'relevant': True, 'category': 'funding', 'summary': 'Résumé.', 'score': 80}
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs['model'] == 'custom-model'
    assert kwargs['store'] is False
    assert kwargs['text_format'] is Analysis
    assert 'tools' not in kwargs


@pytest.mark.parametrize('response', [
    SimpleNamespace(status='completed', output_parsed=None),
    SimpleNamespace(status='incomplete', output_parsed=None),
])
def test_refusal_and_incomplete_response(response):
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        sdk.return_value.__enter__.return_value.responses.parse.return_value = response
        with pytest.raises(OpenAIServiceError):
            OpenAIService('test-key').analyze_text('hello')


def test_openai_outage_and_secret_safe_logging(caplog):
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        sdk.return_value.__enter__.return_value.responses.parse.side_effect = APIConnectionError(
            message='secret-api-key', request=httpx.Request('POST', 'https://example.com'))
        with pytest.raises(OpenAIServiceError, match='indisponible'):
            OpenAIService('secret-api-key', sleep=lambda _: None).analyze_text('hello')
    assert 'secret-api-key' not in caplog.text


def test_missing_key_and_input_validation():
    with pytest.raises(OpenAIServiceError, match='not configured'):
        OpenAIService('').analyze_text('hello')
    with pytest.raises(ValueError):
        OpenAIService('test').analyze_text(' ')
    with pytest.raises(ValueError):
        Analysis(relevant=True, category='x', summary='x', score=101)
