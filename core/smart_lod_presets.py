"""Smart LODs presets: LOD count plus a triangle budget per LOD, stored in the blend.

Two presets ship with the add-on: Unreal and Unity. The Start Phase 2 pipeline switch (Unreal / FAB or
Unity) selects the matching preset, and ReBake / ReLOD read the same preset instead of the live fields.
"""
MAX_LODS = 10
TARGET_PREFIX = "smart_lods_target_"

# (name, LOD count, triangle budget of LOD0..LOD9; only the first ``count`` are used)
DEFAULTS = (
    ("Unreal", 6, (6000, 3000, 1500, 750, 350, 200, 100, 75, 50, 30)),
    ("Unity", 5, (2900, 1500, 1000, 500, 150, 100, 75, 50, 30, 20)),
)
ENGINE_PRESET = {"FAB": "Unreal", "UNITY": "Unity"}


def preset_name_for_engine(engine):
    return ENGINE_PRESET.get(engine, "Unreal")


def default_values(name):
    for default_name, count, targets in DEFAULTS:
        if default_name.casefold() == name.casefold():
            return count, tuple(targets)
    return DEFAULTS[0][1], tuple(DEFAULTS[0][2])


def seed(settings):
    """Add the default presets once per blend; returns True when something was added."""
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
