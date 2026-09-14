"""Shared render resolution presets for the add-on panel."""

ASPECT_RATIOS = {
    "SQUARE": (1, 1),
    "WIDE": (16, 9),
    "PORTRAIT": (3, 4),
}

PRESET_SIZES = {
    "1K": 1024,
    "2K": 2048,
    "4K": 4096,
}


def preset_resolution(aspect, size):
    width, height = ASPECT_RATIOS[aspect]
    longest = PRESET_SIZES[size]
    if width >= height:
        return longest, longest * height // width
    return longest * width // height, longest
