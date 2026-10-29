"""Marks that keep unfinished Generated.N collections out of later processing and deletion.

A marked collection (and every object in it) stays in the scene exactly as it came out of the
failed run, normally ``Highpoly_Generated.N`` plus whatever Retopo passes finished, so it can be
finished by hand. Phase 2 skips marked collections and the clear operators leave them alone.
"""
import time

SKIP_KEY = 'polygroups_skip'
REASON_KEY = 'polygroups_skip_reason'
FAILED_KEY = 'polygroups_failed'
FAILED_AT_KEY = 'polygroups_failed_at'
FAILED_COLOR = 'COLOR_05'


def is_marked(collection):
    return collection is not None and bool(collection.get(SKIP_KEY))


def is_marked_object(obj):
    return bool(obj.get(SKIP_KEY)) or any(is_marked(col) for col in obj.users_collection)


def mark(collection, reason=''):
    """Flag the collection and all of its objects as skipped."""
    collection[SKIP_KEY] = 1
    collection[REASON_KEY] = str(reason)
    collection.color_tag = FAILED_COLOR
    for obj in collection.all_objects:
        obj[SKIP_KEY] = 1


def unmark(collection):
    for key in (SKIP_KEY, REASON_KEY):
        if key in collection:
            del collection[key]
    for obj in collection.all_objects:
        if SKIP_KEY in obj:
            del obj[SKIP_KEY]


def mark_failed_file(collection, error=''):
    """Phase 1 stamp, saved inside the Generated.N blend of a file that did not finish."""
    collection[FAILED_KEY] = 1
    collection[REASON_KEY] = str(error)
    collection[FAILED_AT_KEY] = time.time()


def clear_stamp(collection):
    """Drop the Phase 1 failure stamp once the file was fixed by hand."""
    for key in (FAILED_KEY, FAILED_AT_KEY, REASON_KEY):
        if collection is not None and key in collection and not collection.get(SKIP_KEY):
            del collection[key]


def stamped_failure(collection, file_mtime, grace=120.0):
    """Reason stored by Phase 1, or '' when the file was edited after the failure."""
    if collection is None or not collection.get(FAILED_KEY):
        return ''
    failed_at = float(collection.get(FAILED_AT_KEY, 0) or 0)
    if file_mtime and failed_at and file_mtime > failed_at + grace:
        return ''
    return str(collection.get(REASON_KEY, '')) or 'Phase 1 did not finish this file'
