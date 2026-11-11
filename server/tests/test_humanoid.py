"""Full G1 asset, fixed-base, IK, actuator and camera integration checks."""
import mujoco
import numpy as np
import pytest

from server.humanoid import HumanoidController, augment_scene
from server.tests.test_dual_yam import XML


@pytest.fixture
def rig():
    model = mujoco.MjModel.from_xml_string(augment_scene(XML))
    data = mujoco.MjData(model)
    return model, data, HumanoidController(model, data)


def test_full_body_fixed_base_and_original_food_indices(rig):
    model, data, controller = rig
    assert model.joint(0).qposadr[0] == 0
    assert model.joint(0).type[0] == mujoco.mjtJoint.mjJNT_FREE
    assert model.eq('grasp').id == 0
    assert model.eq_obj1id[0] == model.body('left_tcp').id
    for name in ('pelvis', 'torso_link', 'left_ankle_roll_link', 'right_ankle_roll_link', 'chef_hat'):
        assert model.body(name).id > 0
    assert model.mesh('head_link').id >= 0
    assert model.body('pelvis').jntnum[0] == 0
    assert model.nu == 18
    assert all(len(arm['q']) == 7 for arm in controller.arms.values())
    before = data.qpos[:7].copy()
    controller.reset()
    np.testing.assert_array_equal(before, data.qpos[:7])
    assert controller.snapshot()['fixed_base']


def test_fixture_tcp_workspace_and_low_food_center_rejection(rig):
    _, _, controller = rig
    # TCP is 7cm above food center, as specified by the existing grasp weld.
    for target in [[-.231, -.0825, .84], [-.231, -.0825, 1.1], [0, .132, 1.08],
                   [.209, .11, .84], [.2365, -.187, .84], [0, .03025, .9]]:
        _, error = controller.solve('left', target, iterations=240)
        assert error < .012, (target, error)
        assert controller.orientation_errors['left'] < .03
    state = controller.step([-.231, -.0825, .77], 'pick', .005)
    assert not state['reachable']
    assert state['arms']['left']['rejection_reason'] == 'unreachable_pose'


def test_both_arms_move_via_servos_and_bad_commands_hold(rig):
    model, data, controller = rig
    before = data.qpos.copy()
    left = controller.targets['left'] + [.025, -.02, -.025]
    right = controller.targets['right'] + [-.02, -.02, .025]
    controller.step(left, 'manual', .005, right_target_position=right)
    np.testing.assert_array_equal(data.qpos, before)
    for _ in range(350):
        controller.step(left, 'manual', .005, right_target_position=right)
        mujoco.mj_step(model, data)
    for arm in controller.arms.values():
        assert np.linalg.norm(data.qpos[arm['q']] - before[arm['q']]) > .01
    state = controller.snapshot()
    assert state['ik_error'] < .015
    assert state['arms']['right']['ik_error'] < .015
    controls = data.ctrl.copy()
    controller.step([5, 5, 5], 'manual', .005, right_target_position=[5, 5, 5])
    np.testing.assert_array_equal(data.ctrl, controls)
    with pytest.raises(ValueError):
        controller.step([np.nan, 0, 1], 'manual', .005)
    assert not controller.set_grasp('right', True)


def test_cameras_render_full_humanoid(rig):
    model, data, _ = rig
    with mujoco.Renderer(model, height=240, width=320) as renderer:
        for camera in ('first_person', 'operator', 'wrist'):
            renderer.update_scene(data, camera=camera)
            pixels = renderer.render()
            assert pixels.shape == (240, 320, 3)
            assert pixels.std() > 5
