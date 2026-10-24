"""Text-only API clients. Catalog checked against official docs 2026-10-24."""
import json
import urllib.error
import urllib.request
from urllib.parse import quote

OPENAI_MODELS = (
    ('gpt-6-luna', 'GPT-6 Luna | Light / Translation', 'Efficient current model for simple text and translation'),
    ('gpt-6.1-sol', 'GPT-6.1 Sol | Balanced', 'Current balanced general-purpose model'),
    ('gpt-6-astra', 'GPT-6 Astra | Flagship', 'Current flagship for demanding reasoning and writing'),
    ('gpt-5.4-mini', 'GPT-5.4 Mini | Previous generation', 'Previous-generation small general-purpose model'),
    ('gpt-5.4', 'GPT-5.4 | Previous generation', 'Previous-generation general-purpose model'),
    ('gpt-5.4-pro', 'GPT-5.4 Pro | Previous generation', 'More compute for difficult tasks; may take longer'),
    ('gpt-5.2', 'GPT-5.2 | Previous generation', 'Previous-generation professional model'),
    ('gpt-5.2-pro', 'GPT-5.2 Pro | Previous generation', 'Previous-generation professional reasoning'),
    ('CUSTOM', 'Custom Model ID', 'Enter an API model ID available to your account'),
)
GOOGLE_MODELS = (
    ('gemini-3.5-flash-lite', 'Gemini 3.5 Flash-Lite | Light / Translation', 'Current fast, cost-efficient text model'),
    ('gemini-3.1-flash-lite', 'Gemini 3.1 Flash-Lite | Light', 'Efficient general text model'),
    ('gemini-3.8-flash', 'Gemini 3.8 Flash | Balanced', 'Current high-capability Flash model'),
    ('gemini-3.6-flash', 'Gemini 3.6 Flash | Previous Flash', 'Previous-generation Flash model'),
    ('gemini-4-argon', 'Gemini 4 Argon | Flagship', 'Current flagship reasoning model'),
    ('gemini-3.1-pro-preview', 'Gemini 3.1 Pro | Preview', 'Pro reasoning model; preview availability may change'),
    ('gemini-3-flash-preview', 'Gemini 3 Flash | Preview', 'Preview Flash model'),
    ('gemini-2.5-flash-lite', 'Gemini 2.5 Flash-Lite | Limited legacy access', 'Available only to previous users of the 2.5 family'),
    ('gemini-2.5-flash', 'Gemini 2.5 Flash | Limited legacy access', 'Available only to previous users of the 2.5 family'),
    ('gemini-2.5-pro', 'Gemini 2.5 Pro | Limited legacy access', 'Available only to previous users of the 2.5 family'),
    ('CUSTOM', 'Custom Model ID', 'Enter a text model ID supported by generateContent'),
)


class TextGenerationError(Exception):
    pass


def generate_text(provider, api_key, model, prompt, instructions='', max_tokens=8192, timeout=600):
    if not api_key:
        raise TextGenerationError('API key is missing')
    if not prompt.strip() or not model.strip():
        raise TextGenerationError('Prompt and model ID are required')
    if provider == 'OPENAI':
        url = 'https://api.openai.com/v1/responses'
        payload = {'model': model, 'input': prompt, 'max_output_tokens': max_tokens, 'store': False}
        if instructions.strip():
            payload['instructions'] = instructions
        headers = {'Authorization': 'Bearer ' + api_key}
    elif provider == 'GOOGLE':
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(model, safe='-._') + ':generateContent'
        payload = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                   'generationConfig': {'maxOutputTokens': max_tokens}}
        if instructions.strip():
            payload['systemInstruction'] = {'parts': [{'text': instructions}]}
        headers = {'x-goog-api-key': api_key}
    else:
        raise TextGenerationError('Unknown text provider')
    headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode('utf-8')).get('error', {}).get('message', '')
        except (ValueError, AttributeError):
            detail = ''
        detail = str(detail).replace(api_key, '[redacted]')[:500]
        raise TextGenerationError(f'API HTTP {error.code}: {detail}') from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise TextGenerationError('API request failed: connection, timeout or invalid response') from None
    if provider == 'OPENAI':
        parts = [part for item in data.get('output', []) if item.get('type') == 'message'
                 for part in item.get('content', [])]
        text = '\n'.join(part.get('text', '') for part in parts if part.get('type') == 'output_text')
        refusal = next((part.get('refusal') for part in parts if part.get('type') == 'refusal'), None)
        incomplete = data.get('status') == 'incomplete'
        if not text.strip():
            raise TextGenerationError('Request refused' if refusal else
                'No text returned. Increase Max Output Tokens if reasoning used the output budget.')
    else:
        candidates = data.get('candidates', [])
        candidate = candidates[0] if candidates else {}
        text = '\n'.join(part.get('text', '') for part in candidate.get('content', {}).get('parts', [])
                         if not part.get('thought', False) and 'text' in part)
        incomplete = candidate.get('finishReason') == 'MAX_TOKENS'
        if not text.strip():
            reason = data.get('promptFeedback', {}).get('blockReason') or candidate.get('finishReason', 'empty response')
            raise TextGenerationError('No text returned: ' + str(reason))
    return text, ('Partial result: output token limit reached' if incomplete else 'Completed')
