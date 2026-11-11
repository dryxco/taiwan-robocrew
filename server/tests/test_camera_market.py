"""Composition, physics preservation and repeatability of camera-only scenery."""
import xml.etree.ElementTree as ET
from unittest.mock import patch

import mujoco
import numpy as np
import pytest

from server.camera_market import decorate_camera_market
from server.humanoid import augment_scene
from server.simulation import Robot
from server.workstation_visuals import decorate_scene


def composed_scene(robot_id):
    captured = []
    compile_model = mujoco.MjModel.from_xml_string

    def capture(xml):
        captured.append(xml)
        return compile_model(xml)

    with patch.object(mujoco.MjModel, 'from_xml_string', side_effect=capture):
        Robot(robot_id)
    return decorate_scene(augment_scene(captured[0]), robot_id)


@pytest.mark.parametrize('robot_id', ['jipai', 'pepper', 'tea'])
def test_background_preserves_composed_task_and_physics(robot_id):
    source = composed_scene(robot_id)
    result = decorate_camera_market(source, robot_id)
    assert decorate_camera_market(result, robot_id) == result
    before, after = ET.fromstring(source), ET.fromstring(result)
    for element in list(after.find('worldbody')):
        if element.get('name', '').startswith('camera_market_'):
            after.find('worldbody').remove(element)
    for element in list(after.find('asset')):
        if element.get('name', '').startswith('camera_market_'):
            after.find('asset').remove(element)
    assert ET.tostring(before) == ET.tostring(after)
    base = mujoco.MjModel.from_xml_string(source)
    model = mujoco.MjModel.from_xml_string(result)
    assert (model.nq, model.nv, model.nu, model.neq) == (base.nq, base.nv, base.nu, base.neq)
    for attr in ('qpos0', 'eq_data', 'eq_obj1id', 'eq_obj2id', 'actuator_gainprm'):
        np.testing.assert_array_equal(getattr(base, attr), getattr(model, attr))
    for i in range(model.ngeom):
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith('camera_market_'):
            assert model.geom_contype[i] == model.geom_conaffinity[i] == 0
    data, original = mujoco.MjData(model), mujoco.MjData(base)
    for _ in range(20):
        mujoco.mj_step(model, data)
        mujoco.mj_step(base, original)
    np.testing.assert_allclose(data.qpos, original.qpos, atol=1e-12)


def test_invalid_inputs_and_existing_sky():
    with pytest.raises(ValueError):
        decorate_camera_market('<mujoco/>', 'jipai')
    with pytest.raises(ValueError):
        decorate_camera_market('<mujoco><worldbody/></mujoco>', 'unknown')
    xml = '<mujoco><asset><texture name="sky" type="skybox"/></asset><worldbody/></mujoco>'
    result = ET.fromstring(decorate_camera_market(xml, 'jipai'))
    assert len(result.findall("asset/texture[@type='skybox']")) == 1
