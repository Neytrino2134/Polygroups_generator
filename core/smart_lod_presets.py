"""Smart LODs presets backed by a global user-config library and scene UI mirrors.

Two presets ship with the add-on: Unreal and Unity. The Start Phase 2 pipeline switch (Unreal / FAB or
Unity) selects the matching preset, and ReBake / ReLOD read the same preset instead of the live fields.
"""
import json
import os
import tempfile
from pathlib import Path

import bpy

MAX_LODS = 10
TARGET_PREFIX = "smart_lods_target_"

# (name, LOD count, triangle budget of LOD0..LOD9; only the first ``count`` are used)
DEFAULTS = (
    ("Unreal", 6, (6000, 3000, 1500, 750, 350, 200, 100, 75, 50, 30)),
    ("Unity", 5, (2900, 1500, 1000, 500, 150, 100, 75, 50, 30, 20)),
)
ENGINE_PRESET = {"FAB": "Unreal", "UNITY": "Unity"}


def preset_path():
    return Path(bpy.utils.user_resource('CONFIG')) / 'airetopo' / 'smart_lod_presets.json'


def _records(settings):
    return [dict(name=preset.name, count=preset.count, targets=list(preset.targets))
            for preset in settings.smart_lods_presets]


def _load():
    path = preset_path()
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or document.get('version') != 1:
        raise ValueError('Invalid global Smart LODs preset library')
    records = document.get('presets')
    removed = document.get('removed', [])
    if not isinstance(records, list) or not isinstance(removed, list) or not all(isinstance(name, str) for name in removed):
        raise ValueError('Invalid global Smart LODs preset list')
    names = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid Smart LODs preset')
        name, count, targets = record.get('name'), record.get('count'), record.get('targets')
        if (not isinstance(name, str) or not name.strip() or name.casefold() in names
                or type(count) is not int or not 1 <= count <= MAX_LODS
                or not isinstance(targets, list) or len(targets) != MAX_LODS
                or any(type(value) is not int or value < 1 for value in targets)):
            raise ValueError('Invalid Smart LODs preset values')
        names.add(name.casefold())
    return dict(version=1, presets=records, removed=removed)


def _store(document):
    path = preset_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.smart-lods-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _populate(settings, records):
    if _records(settings) != records:
        active = settings.smart_lods_preset_active
        settings.smart_lods_presets.clear()
        for record in records:
            write(settings.smart_lods_presets.add(), record['name'], record['count'], record['targets'])
        # Library synchronization must not change this scene's live triangle budgets.
        settings['smart_lods_preset_active'] = active if find(settings, active) else ''
    settings.smart_lods_presets_seeded = True


def synchronize(settings):
    """Import legacy scene-only names once, then prefer globally saved values."""
    document = _load()
    seed(settings)
    records = _records(settings)
    if document is None:
        document = dict(version=1, presets=records, removed=[])
        _store(document)
    else:
        known = {record['name'].casefold() for record in document['presets']} | set(document['removed'])
        additions = [record for record in records if record['name'].casefold() not in known]
        if additions:
            document['presets'].extend(additions)
            _store(document)
    _populate(settings, document['presets'])
    return document


def save_global(settings, name, count=None, targets=None, remove=False):
    """Persist an explicit preset edit before publishing it to scene UI mirrors."""
    document = synchronize(settings)
    key = name.casefold()
    records = document['presets']
    index = next((index for index, record in enumerate(records) if record['name'].casefold() == key), None)
    if remove:
        if index is not None:
            records.pop(index)
        document['removed'] = sorted(set(document['removed']) | {key})
    else:
        record = dict(name=name, count=count, targets=list(targets))
        if index is None:
            records.append(record)
        else:
            records[index] = record
        document['removed'] = [name for name in document['removed'] if name != key]
    _store(document)
    refresh_scenes(records)


def refresh_scenes(records):
    for scene in bpy.data.scenes:
        mirror = getattr(scene, 'polygroups_mesh_finalization_settings', None)
        if mirror is not None:
            _populate(mirror, records)


def preset_name_for_engine(engine):
    return ENGINE_PRESET.get(engine, "Unreal")


def default_values(name):
    for default_name, count, targets in DEFAULTS:
        if default_name.casefold() == name.casefold():
            return count, tuple(targets)
    return DEFAULTS[0][1], tuple(DEFAULTS[0][2])


def seed(settings):
    """Initialize a scene's preset UI before loading/migrating the global library."""
    if settings.smart_lods_presets_seeded:
        return False
    settings.smart_lods_presets_seeded = True
    for name, count, targets in DEFAULTS:
        if find(settings, name) is None:
            write(settings.smart_lods_presets.add(), name, count, targets)
    return True


def find(settings, name):
    for preset in settings.smart_lods_presets:
        if preset.name.casefold() == name.casefold():
            return preset
    return None


def write(preset, name, count, targets):
    preset.name = name
    preset.count = count
    preset.targets = [max(1, int(value)) for value in targets][:MAX_LODS]


def read_current(settings):
    return settings.smart_lods_count, tuple(getattr(settings, TARGET_PREFIX + str(i)) for i in range(1, MAX_LODS + 1))


def apply_values(settings, count, targets):
    """Write a preset into the live Smart LODs fields."""
    settings.smart_lods_count = count
    for index, value in enumerate(targets, 1):
        setattr(settings, TARGET_PREFIX + str(index), value)


def engine_values(settings, engine):
    """(count, targets) of the preset that belongs to the pipeline engine; defaults when it was removed."""
    name = preset_name_for_engine(engine)
    preset = find(settings, name)
    if preset is not None:
        return preset.count, tuple(preset.targets)
    return default_values(name)


def select_engine_preset(settings, engine):
    """Select and apply the Unreal / Unity preset for the pipeline switch."""
    seed(settings)
    name = preset_name_for_engine(engine)
    count, targets = engine_values(settings, engine)
    if find(settings, name) is not None:
        settings.smart_lods_preset_active = name
    apply_values(settings, count, targets)


def save_to_engine(settings, engine):
    """Write the live count and budgets into the engine's preset (creating the defaults first)."""
    seed(settings)
    preset = find(settings, preset_name_for_engine(engine))
    count, targets = read_current(settings)
    write(preset, preset.name, count, targets)
