"""Physics and complete workflow regression checks for visual-only dressing."""
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from server import simulation
from server.workstation_visuals import decorate_scene
from server.tests.test_simulation import test_physical_workflow_and_idempotent_credit as workflow


def install_decorator(monkeypatch, snapshots=None):
    # Capture raw input even after the runtime installs the public hook.
    monkeypatch.setattr(simulation, 'decorate_scene', lambda xml, robot_id: xml, raising=False)
    real = mujoco.MjModel
    ids = iter(('jipai', 'pepper', 'tea'))

    def compile_scene(xml):
        rid = next(ids)
        decorated = decorate_scene(xml, rid)
        if snapshots is not None:
            snapshots.append((xml, decorated))
        return real.from_xml_string(decorated)

    proxy = SimpleNamespace(**vars(mujoco))
    proxy.MjModel = SimpleNamespace(from_xml_string=compile_scene)
    monkeypatch.setattr(simulation, 'mujoco', proxy)


@pytest.mark.parametrize('rid', ['jipai', 'pepper', 'tea'])
def test_decorated_workflow(monkeypatch, rid):
    install_decorator(monkeypatch)
    workflow(rid)


def test_decoration_preserves_physics_and_camera_contract(monkeypatch):
    snapshots = []
    install_decorator(monkeypatch, snapshots)
    simulation.World()
    for original_xml, decorated_xml in snapshots:
        original = mujoco.MjModel.from_xml_string(original_xml)
        decorated = mujoco.MjModel.from_xml_string(decorated_xml)
        for field in ('nq', 'nv', 'neq', 'nmocap'):
            assert getattr(original, field) == getattr(decorated, field)
        # Static decoration may add a zero-mass body but cannot alter originals.
        for i in range(original.nbody):
            name = mujoco.mj_id2name(original, mujoco.mjtObj.mjOBJ_BODY, i)
            j = mujoco.mj_name2id(decorated, mujoco.mjtObj.mjOBJ_BODY, name) if name else 0
            for field in ('body_mass', 'body_inertia', 'body_pos', 'body_quat'):
                np.testing.assert_allclose(getattr(original, field)[i], getattr(decorated, field)[j], atol=1e-12)
        for field in ('eq_data', 'eq_type', 'cam_pos', 'cam_quat', 'cam_fovy'):
            np.testing.assert_array_equal(getattr(original, field), getattr(decorated, field))
        old_tree, new_tree = ET.fromstring(original_xml), ET.fromstring(decorated_xml)
        originals = old_tree.findall('.//geom')
        preserved = [g for g in new_tree.findall('.//geom') if not g.get('name', '').startswith('workstation_')]
        assert len(originals) == len(preserved)
        for old, new in zip(originals, preserved):
            assert {k:v for k,v in old.attrib.items() if k not in ('rgba', 'material')} == {
                k:v for k,v in new.attrib.items() if k not in ('rgba', 'material')}
        for geom in new_tree.findall('.//geom'):
            if geom.get('name', '').startswith('workstation_'):
                assert all(geom.get(attr) == '0' for attr in ('contype', 'conaffinity', 'mass'))
                assert geom.get('group') == '2'


def test_idempotence_and_input_errors():
    once = decorate_scene(simulation.XML, 'jipai')
    assert decorate_scene(once, 'jipai') == once
    with pytest.raises(ValueError, match='Unknown workstation'):
        decorate_scene(simulation.XML, 'unknown')
    with pytest.raises(ValueError, match='worldbody'):
        decorate_scene('<mujoco/>', 'tea')
