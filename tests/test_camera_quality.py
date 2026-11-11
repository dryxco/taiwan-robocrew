"""Camera policy contracts; no OpenGL context or physics stepping required."""
import io

import mujoco
import numpy as np
from PIL import Image
import pytest

from server.camera_quality import CameraProfile, CameraQuality


def test_defaults_and_renderer_sizes():
    quality = CameraQuality()
    assert quality.for_camera('first_person') == CameraProfile(960, 640, 90)
    for camera in ('top', 'wrist'):
        assert quality.for_camera(camera) == CameraProfile(480, 320, 80)
        assert quality.renderer_kwargs(camera) == {'width': 480, 'height': 320}
    assert quality.renderer_kwargs() == {'width': 960, 'height': 640}
    with pytest.raises(ValueError, match='Unknown camera'):
        quality.for_camera('missing')


def test_environment_configuration():
    quality = CameraQuality.from_env({
        'NIGHTSHIFT_FIRST_PERSON_WIDTH': '1200',
        'NIGHTSHIFT_FIRST_PERSON_JPEG_QUALITY': '92',
        'NIGHTSHIFT_SECONDARY_WIDTH': '600',
        'NIGHTSHIFT_SECONDARY_JPEG_QUALITY': '85',
    })
    assert quality.first_person == CameraProfile(1200, 800, 92)
    assert quality.secondary == CameraProfile(600, 400, 85)
    assert CameraQuality.from_env({}) == CameraQuality()


@pytest.mark.parametrize('key,value', [
    ('WIDTH', '481'), ('WIDTH', '0'), ('WIDTH', '-3'), ('WIDTH', 'abc'),
    ('JPEG_QUALITY', '0'), ('JPEG_QUALITY', '96'), ('JPEG_QUALITY', '80.5'),
])
def test_invalid_environment_is_actionable(key, value):
    with pytest.raises(ValueError, match='Invalid NIGHTSHIFT_FIRST_PERSON'):
        CameraQuality.from_env({f'NIGHTSHIFT_FIRST_PERSON_{key}': value})


@pytest.mark.parametrize('dimensions', [(480, 300, 80), (0, 0, 80), (480, 320, True)])
def test_invalid_profiles(dimensions):
    with pytest.raises(ValueError):
        CameraProfile(*dimensions)


def test_offscreen_capacity_does_not_change_physics():
    model = mujoco.MjModel.from_xml_string('''<mujoco>
        <option timestep="0.005"/>
        <visual><global offwidth="480" offheight="320"/></visual>
        <worldbody><body><freejoint/><geom type="sphere" size=".1"/></body></worldbody>
    </mujoco>''')
    mass, inertia, gravity = model.body_mass.copy(), model.body_inertia.copy(), model.opt.gravity.copy()
    quality = CameraQuality()
    quality.configure_offscreen(model)
    assert (model.vis.global_.offwidth, model.vis.global_.offheight) == (960, 640)
    assert model.opt.timestep == .005
    np.testing.assert_array_equal(model.body_mass, mass)
    np.testing.assert_array_equal(model.body_inertia, inertia)
    np.testing.assert_array_equal(model.opt.gravity, gravity)
    model.vis.global_.offwidth, model.vis.global_.offheight = 1500, 1000
    quality.configure_offscreen(model)
    assert (model.vis.global_.offwidth, model.vis.global_.offheight) == (1500, 1000)


@pytest.mark.parametrize('camera', ['first_person', 'top', 'wrist'])
@pytest.mark.parametrize('shared', [False, True])
def test_jpeg_dimensions_and_quality(camera, shared):
    quality = CameraQuality()
    profile = quality.for_camera(camera)
    size = quality.renderer_kwargs(None if shared else camera)
    pixels = np.random.default_rng(5).integers(0, 256, (size['height'], size['width'], 3), dtype=np.uint8)
    encoded = quality.encode_jpeg(pixels, camera)
    decoded = Image.open(io.BytesIO(encoded))
    decoded.load()
    assert decoded.format == 'JPEG'
    assert decoded.size == (profile.width, profile.height)
    assert decoded.mode == 'RGB'
    reference = io.BytesIO()
    Image.new('RGB', (3, 2)).save(reference, format='JPEG', quality=profile.jpeg_quality)
    # Quantization tables verify the encoded quality, not only a mocked save call.
    assert decoded.quantization == Image.open(io.BytesIO(reference.getvalue())).quantization


def test_does_not_upscale_or_distort_source():
    quality = CameraQuality()
    with pytest.raises(ValueError, match='smaller'):
        quality.encode_jpeg(np.zeros((320, 480, 3), dtype=np.uint8), 'first_person')
    with pytest.raises(ValueError, match='3:2'):
        quality.encode_jpeg(np.zeros((640, 1000, 3), dtype=np.uint8), 'first_person')
