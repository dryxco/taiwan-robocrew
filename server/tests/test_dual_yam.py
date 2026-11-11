"""Numerical embodiment tests: no renderer, external service, or real robot needed."""
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from server.dual_yam import ASSETS, MAX_JOINT_SPEED, DualYamController, augment_scene
# Deliberately independent of runtime XML construction; coordinates use the agreed
# compact 0.55 task layout, while robot dimensions remain official/unscaled.
XML = """<mujoco model="dual_yam_test">
<option timestep=".005" gravity="0 0 -9.81"/>
<visual><global offwidth="480" offheight="320"/></visual>
<worldbody>
<light pos="0 0 3"/>
<geom name="floor" type="plane" size="3 3 .1" rgba=".08 .1 .12 1"/>
<geom name="counter" type="box" pos="0 0 .65" size=".85 .65 .05" rgba=".24 .3 .31 1"/>
<geom name="tray" type="box" pos="-.231 -.0825 .715" size=".088 .0935 .015" rgba=".55 .59 .62 1"/>
<geom name="season_zone" type="box" pos="0 .132 .71" size=".088 .077 .01" rgba=".76 .35 .16 1"/>
<geom name="bag_base" type="box" pos=".209 .11 .715" size=".0715 .0715 .015" rgba=".65 .46 .25 1"/>
<geom name="bag_back" type="box" pos=".209 .1815 .80" size=".0715 .0055 .09" rgba=".65 .46 .25 1"/>
<geom name="bag_left" type="box" pos=".1375 .11 .80" size=".0055 .0715 .09" rgba=".65 .46 .25 1"/>
<geom name="bag_right" type="box" pos=".2805 .11 .80" size=".0055 .0715 .09" rgba=".65 .46 .25 1"/>
<geom name="delivery" type="box" pos=".2365 -.187 .715" size=".1045 .077 .015" rgba=".16 .55 .42 1"/>
<body name="food" pos="-.231 -.0825 .77"><freejoint/><geom type="box" size=".04125 .03025 .025" mass=".15" rgba=".84 .47 .14 1"/></body>
<body name="gripper" mocap="true" pos="-.231 -.0825 1.08"><geom type="sphere" size=".01" contype="0" conaffinity="0"/><camera name="wrist" pos="0 -.06 .06" xyaxes="1 0 0 0 1 0"/></body>
<camera name="first_person" pos="0 -1.25 1.45" xyaxes="1 0 0 0 .48 .88"/>
<camera name="top" pos="0 0 2.6" xyaxes="1 0 0 0 1 0"/>
</worldbody><equality><weld name="grasp" body1="gripper" body2="food" active="false" relpose="0 0 -.07 1 0 0 0" solref=".015 1"/></equality></mujoco>"""


@pytest.fixture
def rig():
    model = mujoco.MjModel.from_xml_string(augment_scene(XML))
    data = mujoco.MjData(model)
    return model, data, DualYamController(model, data)


def advance(rig, endpoint, seconds=4, stage='pick'):
    model, data, controller = rig
    target = controller.targets['left'].copy()
    endpoint = np.asarray(endpoint) * [.55, .55, 1.]
    for _ in range(round(seconds / model.opt.timestep)):
        delta = np.asarray(endpoint) - target
        target += delta * min(1., .25 * model.opt.timestep / max(np.linalg.norm(delta), 1e-9))
        controller.step(target, stage, model.opt.timestep, bool(data.eq_active[0]))
        mujoco.mj_step(model, data)
    return controller.snapshot()


def test_official_chains_and_original_scene_indices(rig):
    model, data, controller = rig
    assert model.jnt_type[0] == mujoco.mjtJoint.mjJNT_FREE
    assert model.jnt_qposadr[0] == 0
    assert model.eq('grasp').id == 0
    assert model.eq_obj1id[0] == model.body('left_tcp').id
    assert model.body('gripper').mocapid[0] == 0
    assert model.nu == 16
    original = ET.parse(ASSETS / 'yam.xml').getroot()
    for side in ('left', 'right'):
        for i, joint in enumerate(original.findall('.//joint'), 1):
            assert model.joint(f'{side}_joint{i}').type[0] == mujoco.mjtJoint.mjJNT_HINGE
            assert np.allclose(model.joint(f'{side}_joint{i}').range, np.fromstring(joint.get('range'), sep=' '))
        for mesh in ('base', 'link1', 'link2', 'link3', 'link4', 'link5'):
            assert model.mesh(f'{side}_{mesh}').id >= 0
    pepper = XML.replace('</equality>', '<weld body1="gripper" body2="food" active="false"/></equality>')
    assert mujoco.MjModel.from_xml_string(augment_scene(pepper)).neq == 3


def test_step_uses_actuators_without_teleporting_any_body(rig):
    model, data, controller = rig
    before = data.qpos.copy()
    controls = data.ctrl.copy()
    controller.step([0, .24, 1.08], 'season', .005)
    assert np.array_equal(data.qpos, before)
    assert np.max(np.abs(data.ctrl - controls)) <= MAX_JOINT_SPEED * .005 + 1e-12
    mujoco.mj_step(model, data)
    assert not np.array_equal(data.qpos[7:], before[7:])


def test_main_task_path_is_dynamically_reachable(rig):
    model, data, controller = rig
    for target in [[-.42, -.15, .84], [-.42, -.15, 1.1], [0, .24, 1.08],
                   [.38, .2, 1.1], [.38, .2, .84], [.43, -.34, 1.1],
                   [.43, -.34, .84], [0, .055, .97], [0, -.15, 1.12]]:
        state = advance(rig, target)
        assert state['ik_error'] < .012, (target, state)
        assert state['reachable']
        for arm in controller.arms.values():
            assert np.all(data.qpos[arm['q']] >= arm['limits'][:, 0] - .002)
            assert np.all(data.qpos[arm['q']] <= arm['limits'][:, 1] + .002)


def test_food_follows_physical_weld_and_hold_retains_grasp(rig):
    model, data, controller = rig
    advance(rig, [-.42, -.15, .84])
    assert np.linalg.norm(data.body('food').xpos - (data.body('left_tcp').xpos - [0, 0, .07])) < .04
    data.eq_active[0] = 1
    advance(rig, [-.42, -.15, 1.1])
    advance(rig, [0, .24, 1.08], stage='season')
    assert np.linalg.norm(data.body('food').xpos - [0, .132, 1.01]) < .02
    assert data.body('food').xmat[8] > .99
    controls = data.ctrl.copy()
    for _ in range(200):
        controller.step(None, 'hold', .005, True)
        mujoco.mj_step(model, data)
    assert np.array_equal(data.ctrl, controls)
    assert data.eq_active[0]
    assert np.linalg.norm(data.body('food').xpos - [0, .132, 1.01]) < .02
    assert controller.snapshot()['held']


def test_unreachable_and_invalid_inputs_are_visible(rig):
    _, data, controller = rig
    state = controller.step([5, 5, 5], 'pick', .005)
    assert not state['reachable']
    assert not state['valid']
    with pytest.raises(ValueError):
        controller.step([np.nan, 0, 1], 'pick', .005)
    with pytest.raises(ValueError):
        controller.step([0, 0, 1], 'pick', float('nan'))
    with pytest.raises(ValueError):
        controller.step([0, 0, 1], 'pick', .005, twist=float('nan'))


def test_right_seasoning_arm_and_bounded_twist_move(rig):
    model, data, controller = rig
    before = data.qpos[controller.arms['right']['q']].copy()
    for _ in range(160):
        controller.step(controller.targets['left'], 'season', .005, twist=2.)
        mujoco.mj_step(model, data)
    assert np.linalg.norm(data.qpos[controller.arms['right']['q']] - before) > .005
    assert abs(data.qpos[controller.arms['left']['q']][-1] - .6) < .02


def test_arms_accept_independent_targets_and_bad_target_holds_only_that_arm(rig):
    model, data, controller = rig
    left_target = controller.targets['left'].copy()
    right_target = controller.targets['right'] + [.025, -.025, -.03]
    for _ in range(300):
        controller.step(left_target, 'manual', .005, right_target_position=right_target)
        mujoco.mj_step(model, data)
    state = controller.snapshot()
    assert state['arms']['right']['ik_error'] < .012
    assert state['arms']['left']['ik_error'] < .012
    previous = controller.commands['right'].copy()
    for _ in range(30):
        controller.step(left_target, 'manual', .005, right_target_position=[4, 4, 4])
        mujoco.mj_step(model, data)
    assert np.array_equal(controller.commands['right'], previous)
    assert not controller.snapshot()['arms']['right']['reachable']
    assert controller.snapshot()['arms']['right']['rejection_reason'] == 'unreachable_pose'
    assert controller.snapshot()['arms']['left']['reachable']


def test_optional_wxyz_orientation_and_invalid_quaternion(rig):
    model, data, controller = rig
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, data.site_xmat[controller.arms['left']['site']])
    for _ in range(100):
        controller.step(controller.targets['left'], 'manual', .005, left_orientation=quat)
        mujoco.mj_step(model, data)
    assert controller.snapshot()['arms']['left']['orientation_error'] < .02
    before = data.ctrl.copy()
    with pytest.raises(ValueError):
        controller.step(controller.targets['left'], 'manual', .005, right_orientation=[0, 0, 0, 0])
    assert np.array_equal(data.ctrl, before)


def test_direct_grippers_and_proximity_gated_explicit_handover(rig):
    model, data, controller = rig
    assert not controller.set_grasp('right', True)  # Closing in air cannot summon food.
    advance(rig, [-.42, -.15, .84])
    assert controller.set_grasp('left', True)
    advance(rig, [0, .24, 1.08])
    shared = controller.targets['left'].copy()
    for _ in range(500):
        controller.step(shared, 'manual', .005, True, right_target_position=shared)
        mujoco.mj_step(model, data)
    assert not controller.set_grasp('right', True)  # Never two competing food welds.
    before = data.qpos.copy()
    assert not controller.set_grasp('left', False)
    assert controller.set_grasp('right', True)
    assert np.array_equal(before, data.qpos)
    assert not data.eq_active[model.equality('grasp').id]
    assert data.eq_active[model.equality('right_grasp').id]
    for _ in range(100):
        controller.step(shared, 'manual', .005, right_target_position=shared)
        mujoco.mj_step(model, data)
    assert controller.snapshot()['arms']['right']['gripper_closed']
    assert np.linalg.norm(data.body('food').xpos - [0, .132, 1.01]) < .02
    assert data.qpos[model.joint('right_finger0_slide').qposadr[0]] > .02
    assert not controller.set_grasp('right', False)
