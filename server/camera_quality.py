"""Camera-only resolution and JPEG policy, independent of simulation timing.

Set NIGHTSHIFT_FIRST_PERSON_WIDTH / NIGHTSHIFT_SECONDARY_WIDTH (height is
always two thirds of width), and corresponding *_JPEG_QUALITY variables.
Load once at startup; apply offscreen sizing to the render model before
creating renderers. Render at each profile's native size, or render at
``renderer_kwargs()`` and let ``encode_jpeg`` downsample secondary views.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Mapping

from PIL import Image


@dataclass(frozen=True)
class CameraProfile:
    width: int
    height: int
    jpeg_quality: int

    def __post_init__(self):
        if any(type(value) is not int for value in (self.width, self.height, self.jpeg_quality)):
            raise ValueError('Camera dimensions and JPEG quality must be integers')
        if self.width <= 0 or self.height <= 0 or self.width * 2 != self.height * 3:
            raise ValueError('Camera dimensions must be positive with a 3:2 aspect ratio')
        if not 1 <= self.jpeg_quality <= 95:
            raise ValueError('JPEG quality must be between 1 and 95')

    def renderer_kwargs(self) -> dict[str, int]:
        return {'width': self.width, 'height': self.height}


@dataclass(frozen=True)
class CameraQuality:
    first_person: CameraProfile = CameraProfile(960, 640, 90)
    secondary: CameraProfile = CameraProfile(480, 320, 80)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> CameraQuality:
        environ = os.environ if environ is None else environ

        def profile(name, default):
            prefix = f'NIGHTSHIFT_{name}'
            try:
                width = int(environ.get(f'{prefix}_WIDTH', default.width))
                quality = int(environ.get(f'{prefix}_JPEG_QUALITY', default.jpeg_quality))
                return CameraProfile(width, width * 2 // 3, quality)
            except (ValueError, TypeError) as exc:
                raise ValueError(f'Invalid {prefix} camera configuration: {exc}') from exc

        defaults = cls()
        return cls(profile('FIRST_PERSON', defaults.first_person),
                   profile('SECONDARY', defaults.secondary))

    def for_camera(self, camera: str) -> CameraProfile:
        if camera == 'first_person':
            return self.first_person
        if camera in ('top', 'wrist', 'operator'):
            return self.secondary
        raise ValueError(f'Unknown camera: {camera}')

    def renderer_kwargs(self, camera: str | None = None) -> dict[str, int]:
        """Native camera dimensions, or maximum dimensions for a shared renderer."""
        if camera is not None:
            return self.for_camera(camera).renderer_kwargs()
        return {'width': max(self.first_person.width, self.secondary.width),
                'height': max(self.first_person.height, self.secondary.height)}

    def configure_offscreen(self, render_model) -> None:
        """Grow only visual framebuffer capacity, before constructing a Renderer."""
        size = self.renderer_kwargs()
        visual = render_model.vis.global_
        visual.offwidth = max(visual.offwidth, size['width'])
        visual.offheight = max(visual.offheight, size['height'])

    def encode_jpeg(self, pixels, camera: str) -> bytes:
        """Encode native RGB pixels, optionally downsampling a shared render.

        Refuse undersized or differently shaped frames rather than silently
        upscaling blurry source pixels or distorting the camera projection.
        """
        profile = self.for_camera(camera)
        image = Image.fromarray(pixels)
        if image.width * 2 != image.height * 3:
            raise ValueError('Rendered frame must have a 3:2 aspect ratio')
        if image.width < profile.width or image.height < profile.height:
            raise ValueError('Rendered frame is smaller than configured camera dimensions')
        if image.size != (profile.width, profile.height):
            image = image.resize((profile.width, profile.height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=profile.jpeg_quality)
        return output.getvalue()
