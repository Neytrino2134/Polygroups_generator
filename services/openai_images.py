import base64
import json
import urllib.error
import urllib.request


OPENAI_IMAGE_GENERATIONS_URL = "https://api.openai.com/v1/images/generations"


class OpenAIImageError(Exception):
    pass


def generate_image_bytes(
    api_key,
    prompt,
    model,
    size,
    quality,
    output_format,
    timeout=180,
):
    if not api_key:
        raise OpenAIImageError("OpenAI API key is missing")

    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "n": 1,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_IMAGE_GENERATIONS_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_data = error.read().decode("utf-8", errors="replace")
        raise OpenAIImageError(_extract_error_message(error_data)) from error
    except urllib.error.URLError as error:
        raise OpenAIImageError(str(error.reason)) from error

    result = json.loads(response_data)
    images = result.get("data") or []
    if not images:
        raise OpenAIImageError("OpenAI response did not contain generated image data")

    b64_image = images[0].get("b64_json")
    if not b64_image:
        raise OpenAIImageError("OpenAI response did not contain b64_json image data")

    return base64.b64decode(b64_image)


def _extract_error_message(error_data):
    try:
        payload = json.loads(error_data)
    except json.JSONDecodeError:
        return error_data or "OpenAI image request failed"

    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("message") or "OpenAI image request failed"

    return "OpenAI image request failed"
