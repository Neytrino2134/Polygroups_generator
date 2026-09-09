import re


GENERATED_INDEX_PATTERN = re.compile(r"^Generated\.(\d+)$", re.IGNORECASE)
GENERATED_PLAIN_PATTERN = re.compile(r"^Generated$", re.IGNORECASE)
TRAILING_INDEX_PATTERN = re.compile(r"\.(\d+)$")
TEMP_INDEX_PATTERN = re.compile(r"\.Temp\.(\d+)$", re.IGNORECASE)


def generated_collection_info(obj):
    """Return (collection, zero-padded index) for a direct Generated.N owner."""
    matches = []
    for collection in getattr(obj, "users_collection", ()):
        match = GENERATED_INDEX_PATTERN.match(collection.name)
        if match:
            matches.append((collection, match.group(1)))
    if not matches:
        return None, ""
    matches.sort(key=lambda item: (int(item[1]), item[0].name.lower()))
    return matches[0]


def indexed_object_name(name, index):
    name = TEMP_INDEX_PATTERN.sub("", name)
    suffix = f".{index}"
    if TRAILING_INDEX_PATTERN.search(name):
        return TRAILING_INDEX_PATTERN.sub(suffix, name)
    return f"{name}{suffix}"


def plain_generated_collection(obj):
    return next(
        (
            collection
            for collection in getattr(obj, "users_collection", ())
            if GENERATED_PLAIN_PATTERN.match(collection.name)
        ),
        None,
    )


def temporary_generated_name(name, fallback_index, preserve_existing=True):
    match = (TEMP_INDEX_PATTERN.search(name) or TRAILING_INDEX_PATTERN.search(name)) if preserve_existing else None
    index = match.group(1) if match else f"{fallback_index:03d}"
    base = TEMP_INDEX_PATTERN.sub("", name)
    base = TRAILING_INDEX_PATTERN.sub("", base)
    return f"{base}.Temp.{index}"


def fix_object_generated_index(obj):
    collection, index = generated_collection_info(obj)
    if collection is None:
        return False
    expected = indexed_object_name(obj.name, index)
    if obj.name == expected:
        return False
    obj.name = expected
    return True


def bake_collection_name(obj):
    collection, _index = generated_collection_info(obj)
    return collection.name if collection is not None else ""
