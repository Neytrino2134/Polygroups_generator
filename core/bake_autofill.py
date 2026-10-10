"""Apply a frozen projection mask to requested bake textures before sealing/saving."""
import json
from dataclasses import dataclass
import bpy
import numpy as np
from .bake_artifact_mask import _gutter_ownership
from .bake_artifact_fill import fill_region


@dataclass
class AutofillPlan:
    target: object
    run: str
    region: tuple
    size: tuple
    mask: object
    ownership: object
    donors: object
    swizzle: tuple
    base_name: str
    normal_name: str
    blur_radius: int

    @classmethod
    def create(cls, session, mask, radius):
        # Repair uses the prepared mask at native dimensions, including conservative
        # manual output resampling. The diagnostic texture itself is never altered.
        height, width = session.domain.shape
        if mask.shape != (height, width):
            yy = np.arange(height) * mask.shape[0] // height
            xx = np.arange(width) * mask.shape[1] // width
            mask = mask[np.ix_(yy, xx)]
        rows, columns = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
        if not len(rows):
            region = (slice(0, 0), slice(0, 0))
        else:
            halo = max(2*radius, session.settings.bake_artifact_autofill_blur, 2)
            region = (slice(max(0, rows[0]-halo), min(height, rows[-1]+halo+1)),
                      slice(max(0, columns[0]-halo), min(width, columns[-1]+halo+1)))
        cropped = mask[region].copy()
        domain, owners = session.domain[region], session.ownership[region]
        hit = session.domain if session.hit is None else session.hit
        donors = domain & hit[region] & ~cropped & (owners > 0)
        expanded = _gutter_ownership(owners, domain, radius) if np.any(donors) else owners.copy()
        return cls(session.target, session.frozen.run, region, (width, height), cropped, expanded, donors,
            session.swizzle, session.target.get('polygroups_bake_base_color_image', '') if session.settings.bake_base_color else '',
            session.frozen.normal_name, session.settings.bake_artifact_autofill_blur)

    def apply(self, report):
        from .bake_projection import META_PROP, RUN_PROP, ARTIFACT_PROP, pixels
        from ..operators.baking import _write_pixels
        if self.target.get(RUN_PROP) != self.run:
            raise ValueError('Autofill mask belongs to a different bake run')
        image = bpy.data.images.get(self.target.get(ARTIFACT_PROP, ''))
        if image is None or image.get(RUN_PROP) != self.run:
            raise ValueError('Missing current-run artifact mask for Autofill')
        metadata = json.loads(image[META_PROP])
        status = dict(enabled=True, blur_radius=self.blur_radius, method='inward boundary averaging, Gaussian blur', textures={})
        patches = []
        repaired = np.zeros(self.mask.shape, dtype=bool)
        for kind, name in (('base_color', self.base_name), ('normal', self.normal_name)):
            texture = bpy.data.images.get(name) if name else None
            if texture is None:
                if name:
                    raise ValueError('Missing requested Autofill texture: ' + kind)
                continue
            if tuple(texture.size) != self.size:
                raise ValueError('Autofill texture size changed: ' + kind)
            if not np.any(self.mask) or not np.any(self.donors):
                status['textures'][kind] = dict(filled=0, unfilled=int(np.count_nonzero(self.mask)), waves=0)
                continue
            rgba = pixels(texture)
            original = rgba[self.region].copy()
            try:
                updated, filled, counts = fill_region(original, self.mask, self.ownership, self.donors,
                    self.blur_radius, self.swizzle if kind == 'normal' else None)
            except ValueError as error:
                report({'WARNING'}, f'Autofill {kind} skipped: {error}')
                status['textures'][kind] = dict(filled=0, unfilled=int(np.count_nonzero(self.mask)), error=str(error))
                continue
            status['textures'][kind] = counts
            if counts['filled']:
                patches.append((texture, original, updated))
                repaired |= filled
            del rgba
        # Compute all patches before writing; restore original regions if a write fails.
        written = []
        try:
            for texture, original, updated in patches:
                rgba = pixels(texture)
                rgba[self.region] = updated
                written.append((texture, original))
                _write_pixels(texture, rgba.ravel())
                del rgba
            alpha = bpy.data.images.get(self.target.get('polygroups_bake_alpha_image', ''))
            if alpha is not None and tuple(alpha.size) == self.size and np.any(repaired):
                rgba = pixels(alpha)
                written.append((alpha, rgba[self.region].copy()))
                local = rgba[self.region]
                local[repaired] = (1, 1, 1, 1)
                _write_pixels(alpha, rgba.ravel())
        except Exception:
            for texture, original in reversed(written):
                rgba = pixels(texture)
                rgba[self.region] = original
                _write_pixels(texture, rgba.ravel())
            raise
        if any(counts['unfilled'] for counts in status['textures'].values()):
            report({'WARNING'}, 'Autofill: some masked texels have no healthy boundary pixels in the same UV island; left unchanged')
        metadata['autofill'] = status
        image[META_PROP] = json.dumps(metadata, sort_keys=True)
        return status
