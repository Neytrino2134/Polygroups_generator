"""Normalize user asset words consistently across finalization pipelines."""
import re


def asset_name(value):
    words = re.sub(r'[^\w]+', '_', value.strip(), flags=re.UNICODE).strip('_').split('_')
    return '_'.join(word[:1].upper() + word[1:] for word in words if word)
