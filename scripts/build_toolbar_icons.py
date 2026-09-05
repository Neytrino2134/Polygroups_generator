"""Run with Blender --background --factory-startup --python this_file.
Rebuild the toolbar geometry assets after changing the source PNG icons.
"""
from pathlib import Path

def build_icon(path):
    """Encode the PNG as colored triangles for Blender's large tool buttons.

    Preview IDs use the small UI-icon drawing path even on large tool buttons.
    Geometry icons use the toolbar's full, centered drawing rectangle instead.
    """
    import bpy
    from array import array

    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        # Geometry icon colors are sRGB bytes, not scene-linear values.
        image.colorspace_settings.name = 'Non-Color'
        width, height = image.size
        scale = 64 / max(width, height)
        width, height = max(1, round(width * scale)), max(1, round(height * scale))
        image.scale(width, height)
        pixels = array('f', [0.0]) * (width * height * 4)
        image.pixels.foreach_get(pixels)
        coords, colors = bytearray(), bytearray()
        step = 255 / max(width, height)
        offset_x = (255 - width * step) / 2
        offset_y = (255 - height * step) / 2
        for y in range(height):
            bottom, top = round(offset_y + y * step), round(offset_y + (y + 1) * step)
            for x in range(width):
                index = (y * width + x) * 4
                rgba = bytes(max(0, min(255, round(c * 255))) for c in pixels[index:index + 4])
                if rgba[3] == 0:
                    continue
                left, right = round(offset_x + x * step), round(offset_x + (x + 1) * step)
                coords.extend((left, bottom, right, bottom, right, top,
                               left, bottom, right, top, left, top))
                colors.extend(rgba * 6)
        return bytes((86, 67, 79, 0, 255, 255, 0, 0)) + bytes(coords) + bytes(colors)
    finally:
        bpy.data.images.remove(image)


if __name__ == "__main__":
    import runpy
    root = Path(__file__).resolve().parents[1]
    filenames = runpy.run_path(str(root / "custom_icons.py"))["_FILES"]
    output = root / "icons" / "toolbar"
    output.mkdir(exist_ok=True)
    for filename in filenames.values():
        source = root / "icons" / filename
        (output / (source.stem + ".dat")).write_bytes(build_icon(source))
    print(f"Built {len(filenames)} toolbar icons")
