"""Limits a Phase 2 run to one Generated.N collection (Do Selected Phase 2).

``generated`` holds the Generated.N names of the run, ``assets`` the *_Collection assets that
Prepare LODs / Rename built from them. ``None`` means no limit (the normal Phase 2 run).
"""
import re

SCOPE = dict(generated=None, assets=None)
NUMBER = re.compile(r'^Generated\.(\d+)$', re.I)
# Generated.N collection property: text of the Phase 2 errors the collection continued after.
WARNING_KEY = 'polygroups_phase2_warning'


def active():
    return SCOPE['generated'] is not None


def begin(generated_names):
    SCOPE.update(generated=set(generated_names) if generated_names else None, assets=None)


def clear():
    SCOPE.update(generated=None, assets=None)


def keep_generated(collections):
    """Generated.N collections of the run (all of them outside Do Selected)."""
    names = SCOPE['generated']
    return list(collections) if names is None else [col for col in collections if col.name in names]


def keep_assets(collections):
    """*_Collection assets of the run; before Prepare has run, Do Selected has none."""
    if SCOPE['generated'] is None:
        return list(collections)
    names = SCOPE['assets'] or set()
    return [col for col in collections if col.name in names]


def add_assets(names):
    if SCOPE['generated'] is not None:
        SCOPE['assets'] = set(SCOPE['assets'] or ()) | set(names)


def generated_number(name):
    match = NUMBER.fullmatch(name or '')
    return int(match.group(1)) if match else None
