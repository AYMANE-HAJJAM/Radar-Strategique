"""Explicit one-request live check. Never imported or executed by the test suite."""
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    logging.disable(logging.CRITICAL)
    model = os.getenv('OPENAI_MODEL', '')
    key = os.getenv('OPENAI_API_KEY', '')
    result = {'status': 'failure', 'model': model or None}
    if not key or not model:
        result['status'] = 'failure_missing_configuration'
    else:
        try:
            with OpenAI(api_key=key, timeout=20, max_retries=0) as client:
                response = client.responses.create(model=model, input='Reply OK.', store=False,
                                                    max_output_tokens=32, reasoning={'effort': 'none'})
            result['status'] = 'success' if response.status == 'completed' else 'failure_incomplete'
            if response.usage:
                result['usage'] = {'input_tokens': response.usage.input_tokens, 'output_tokens': response.usage.output_tokens}
        except Exception as error:
            # Class names are safe diagnostics; exception bodies may contain credentials.
            result['status'] = 'failure_' + type(error).__name__
    print(json.dumps(result))
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
