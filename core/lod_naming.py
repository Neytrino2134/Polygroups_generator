"""Shared zero-based engine LOD naming; legacy dotted levels remain readable."""
import re

LOD_SUFFIX = re.compile(r'[._]LOD[._]?(\d+)$', re.I)


def lod_base(name, engine='UNITY'):
    base = LOD_SUFFIX.sub('', name)
    if engine == 'UNREAL':
        base = re.sub(r'_(?:HIGH|MID|LOW)$', '', base, flags=re.I)
    return base


def lod_name(name, index, engine='UNITY'):
    return f'{lod_base(name, engine)}{"_" if engine == "UNREAL" else "."}LOD{index}'


def lod_index(obj):
    value = obj.get('polygroups_lod_index')
    if value is not None:
        return int(value)
    match = LOD_SUFFIX.search(obj.name)
    if match is None:
        raise ValueError(f'No LOD index on {obj.name}')
    return int(match.group(1))
