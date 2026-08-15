import base64
import json
import urllib.error
import urllib.request


GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class GeminiImageError(Exception):
    pass


def generate_image_bytes(
    api_key,
    prompt,
    model,
    aspect_ratio,
    image_size,
    timeout=180,
):
    if not api_key:
        raise GeminiImageError("Google Gemini API key is missing")

    payload = {
        "model": model,
        "input": prompt,
        "response_format": {
            "type": "image",
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GEMINI_INTERACTIONS_URL,
        data=data,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_data = error.read().decode("utf-8", errors="replace")
        raise GeminiImageError(_extract_error_message(error_data)) from error
    except urllib.error.URLError as error:
        raise GeminiImageError(str(error.reason)) from error

    result = json.loads(response_data)
    b64_image = _find_image_data(result)
    if not b64_image:
        raise GeminiImageError("Gemini response did not contain generated image data")

    return base64.b64decode(b64_image)


def _find_image_data(result):
    output_image = result.get("output_image")
    if isinstance(output_image, dict) and output_image.get("data"):
        return output_image["data"]

    for step in result.get("steps") or []:
        for block in step.get("content") or []:
            if block.get("type") == "image" and block.get("data"):
                return block["data"]

    for candidate in result.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict) and inline_data.get("data"):
                return inline_data["data"]

    return None


def _extract_error_message(error_data):
    try:
        payload = json.loads(error_data)
    except json.JSONDecodeError:
        return error_data or "Gemini image request failed"

    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("message") or "Gemini image request failed"

    return "Gemini image request failed"
