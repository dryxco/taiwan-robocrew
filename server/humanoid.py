"""Full official Unitree G1, fixed lower body and servo-driven seven-DOF arms.

Simulation only: no walking, balance controller, hardware IO, or robot contacts.
"""
from __future__ import annotations

import copy
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from .dual_yam import DualYamController, MAX_JOINT_SPEED

ASSETS = Path(__file__).resolve().parent / 'assets' / 'g1'
ARM_JOINTS = ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow',
              'wrist_roll', 'wrist_pitch', 'wrist_yaw')
BASE_POSITION = (-.04, .25, .793)


def augment_scene(xml: str) -> str:
    """Append full G1 after food, preserving food qpos and existing weld indices."""
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('scene requires worldbody')
    source = ET.parse(ASSETS / 'g1.xml').getroot()
    compiler = root.find('compiler')
    if compiler is None:
        compiler = ET.SubElement(root, 'compiler')
    compiler.set('angle', 'radian')
    option = root.find('option')
    if option is None:
        option = ET.SubElement(root, 'option')
    option.set('integrator', 'implicitfast')
    for element in source.iter():
        for key in ('class', 'childclass'):
            if element.get(key):
                element.set(key, 'unitree_' + element.get(key))
    default = root.find('default')
    if default is None:
        default = ET.SubElement(root, 'default')
    default.extend(copy.deepcopy(list(source.find('default'))))
    asset = root.find('asset')
    if asset is None:
        asset = ET.SubElement(root, 'asset')
    for element in source.find('asset'):
        element = copy.deepcopy(element)
        if element.tag == 'mesh':
            element.set('file', str(ASSETS / 'assets' / element.get('file')))
        asset.append(element)
    actuator = root.find('actuator')
    if actuator is None:
        actuator = ET.SubElement(root, 'actuator')
    body = copy.deepcopy(source.find('worldbody/body'))
    body.remove(body.find('freejoint'))
    body.set('pos', ' '.join(map(str, BASE_POSITION)))
    body.set('quat', '.707106781 0 0 -.707106781')  # G1 +X faces world -Y.
    for link in body.iter('body'):
        link.set('gravcomp', '1')
        for joint in list(link.findall('joint')):
            name = joint.get('name')
            if not any(name == f'{side}_{part}_joint' for side in ('left', 'right') for part in ARM_JOINTS):
                link.remove(joint)  # Fixed legs and waist, no balancing approximation.
            else:
                joint.set('damping', '2')
                joint.set('armature', '.03')
                ET.SubElement(actuator, 'position', name=name + '_servo', joint=name,
                              kp='350', kv='30', ctrlrange=joint.get('range'), forcerange='-25 25')
        for geom in list(link.findall('geom')):
            if geom.get('class') in ('unitree_collision', 'unitree_foot'):
                link.remove(geom)
    target = world.find("body[@name='gripper']")
    if target is None:
        raise ValueError('scene requires gripper mocap target')
    for geom in target.findall('geom'):
        geom.set('rgba', '0 0 0 0')
        geom.set('contype', '0')
        geom.set('conaffinity', '0')
    wrist = target.find("camera[@name='wrist']")
    if wrist is not None:
        target.remove(wrist)
    for side in ('left', 'right'):
        hand = body.find(f".//body[@name='{side}_wrist_yaw_link']")
        tcp = ET.SubElement(hand, 'body', name=f'{side}_tcp', pos='.12 0 0',
                            quat='1 0 0 0')
        ET.SubElement(tcp, 'site', name=f'{side}_tcp_site', size='.005', rgba='0 0 0 0')
        for index, sign in enumerate((-1, 1)):
            finger = ET.SubElement(tcp, 'body', name=f'{side}_finger{index}', pos=f'{sign*.055} 0 -.035')
            name = f'{side}_finger{index}_slide'
            ET.SubElement(finger, 'joint', name=name, type='slide', axis=f'{-sign} 0 0', range='0 .035', damping='2')
            ET.SubElement(finger, 'geom', type='box', size='.006 .014 .025', mass='.02', rgba='0 0 0 0', contype='0', conaffinity='0')
            ET.SubElement(actuator, 'position', name=name+'_servo', joint=name, kp='200', kv='5', ctrlrange='0 .035', forcerange='-2 2')
        if side == 'left' and wrist is not None:
            tcp.append(wrist)
    torso = body.find(".//body[@name='torso_link']")
    torso.set('quat', '.984726539 0 .174108138 0')  # Fixed 20-degree work lean.
    # Upstream head mesh is rigidly attached to torso; hat shares that transform.
    hat = ET.SubElement(torso, 'body', name='chef_hat', pos='.004 0 .49')
    ET.SubElement(hat, 'geom', name='chef_hat_band', type='cylinder', size='.075 .025', rgba='.97 .97 .94 1', mass='0', contype='0', conaffinity='0')
    ET.SubElement(hat, 'geom', name='chef_hat_crown', type='ellipsoid', pos='0 0 .075', size='.09 .085 .085', rgba='1 1 .98 1', mass='0', contype='0', conaffinity='0')
    camera = world.find("camera[@name='first_person']")
    if camera is not None:
        world.remove(camera)
    # Forward of head surface and above shoulders: optical axis down toward fixtures.
    ET.SubElement(torso, 'camera', name='first_person', pos='.23 0 .43',
                  xyaxes='0 -1 0 .45 0 .893', fovy='90')
    camera = world.find("camera[@name='operator']")
    if camera is None:
        camera = ET.SubElement(world, 'camera', name='operator')
    camera.set('pos', '.9 -1.5 1.3')
    camera.set('xyaxes', '.832 .555 0 -.148 .222 .964')
    camera.set('fovy', '48')
    world.append(body)
    grasp = root.find("equality/weld[@name='grasp']")
    if grasp is None:
        raise ValueError('scene requires grasp equality')
    grasp.set('body1', 'left_tcp')
    ET.SubElement(root.find('equality'), 'weld', name='right_grasp', body1='right_tcp',
                  body2='food', active='false', relpose='0 0 -.07 1 0 0 0', solref='.015 1')
    return ET.tostring(root, encoding='unicode')


class HumanoidController(DualYamController):
    """DLS IK and actuator-only stepping; inherited grasp API uses actual TCPs."""

    def __init__(self, model, data):
        self.model, self.data = model, data
        self.scratch = mujoco.MjData(model)
        self.arms = {}
        for side in ('left', 'right'):
            names = [f'{side}_{part}_joint' for part in ARM_JOINTS]
            joints = [model.joint(name) for name in names]
            self.arms[side] = dict(q=np.array([j.qposadr[0] for j in joints]),
                v=np.array([j.dofadr[0] for j in joints]),
                a=np.array([model.actuator(name+'_servo').id for name in names]),
                limits=np.array([j.range.copy() for j in joints]),
                site=model.site(f'{side}_tcp_site').id,
                fingers=np.array([model.actuator(f'{side}_finger{i}_slide_servo').id for i in range(2)]),
                weld=model.equality('grasp' if side == 'left' else 'right_grasp').id)
        self.targets = {'left': np.array([0., .08, 1.05]), 'right': np.array([-.12, .08, .98])}
        self.commands = {}
        self.gripper_closed = dict.fromkeys(self.arms, False)
        self.grip_commands = dict.fromkeys(self.arms, 0.)
        self.last_weld = dict.fromkeys(self.arms, False)
        self.ik_errors = dict.fromkeys(self.arms, float('inf'))
        self.orientation_errors = dict.fromkeys(self.arms, 0.)
        self.rejected = dict.fromkeys(self.arms, False)
        self.held = False
        self.reset()

    def reset(self, target_position=None):
        self._solution_cache = {}
        if target_position is not None:
            self.targets['left'] = np.asarray(target_position, dtype=float).copy()
        for side, arm in self.arms.items():
            seed = [-.6, .2 if side == 'left' else -.2, 0, 1.0, 0, 0, 0]
            q, error = self.solve(side, self.targets[side], seed, 240)
            self.data.qpos[arm['q']] = q
            self.data.qvel[arm['v']] = 0
            self.data.ctrl[arm['a']] = q
            self.commands[side] = q.copy()
            self.ik_errors[side] = error
            self.rejected[side] = error >= .015 or self.orientation_errors[side] >= .12
        self.held = False
        mujoco.mj_forward(self.model, self.data)

    def snapshot(self):
        state = super().snapshot()
        state.update(embodiment='unitree_g1', fixed_base=True, locomotion=False)
        return state

    def step(self, target_position, stage, dt, grasped=False, *, twist=0.0,
             right_target_position=None, left_orientation=None, right_orientation=None):
        """Command independent arms; optional orientations are MuJoCo wxyz quaternions.

        None right target enables guided shaker assistance. Explicit right target
        selects independent control. Infeasible IK leaves that arm's servo goal fixed.
        stage='hold' freezes both arms; caller owns physics and grasp constraints.
        """
        if not np.isfinite(twist):
            raise ValueError('twist must be finite')
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError('dt must be finite and positive')
        if target_position is None or stage == 'hold':
            self.hold()
        else:
            targets = {'left': target_position, 'right': right_target_position}
            if targets['right'] is None:
                targets['right'] = np.array([-.12, .08, .98])
                if stage == 'season':
                    targets['right'] += [0, 0, .025 * np.sin(self.data.time * 8)]
            orientations = {'left': left_orientation, 'right': right_orientation}
            # Validate the entire command before mutating either arm.
            for side in self.arms:
                target = np.asarray(targets[side], dtype=float)
                if target.shape != (3,) or not np.all(np.isfinite(target)):
                    raise ValueError('target_position must contain three finite coordinates')
                targets[side] = target.copy()
                if orientations[side] is not None:
                    quat = np.asarray(orientations[side], dtype=float)
                    if quat.shape != (4,) or not np.all(np.isfinite(quat)) or np.linalg.norm(quat) < 1e-8:
                        raise ValueError('orientation must be a finite nonzero wxyz quaternion')
                    orientations[side] = quat / np.linalg.norm(quat)
            self.held = False
            for side, arm in self.arms.items():
                self.targets[side] = targets[side]
                cache = getattr(self, '_solution_cache', {})
                key = tuple(targets[side]) + (() if orientations[side] is None else tuple(orientations[side]))
                saved = cache.get(side)
                if saved is not None and saved[0] == key:
                    q, error, angle = saved[1:]
                    self.orientation_errors[side] = angle
                else:
                    q, error = self.solve(side, targets[side], self.commands[side], 80,
                                          orientation=orientations[side])
                    if error >= .015 or self.orientation_errors[side] >= .12:
                        # A straight Cartesian path can cross a local IK minimum.
                        # Try the calibrated neutral seed; retain the same acceptance limits.
                        seed = [-.6, .2 if side == 'left' else -.2, 0, 1., 0, 0, 0]
                        alternative, alternative_error = self.solve(side, targets[side], seed, 240,
                                                                   orientation=orientations[side])
                        q, error = alternative, alternative_error
                    cache[side] = (key, q.copy(), error, self.orientation_errors[side])
                    self._solution_cache = cache
                self.ik_errors[side] = error
                self.rejected[side] = error >= .015 or self.orientation_errors[side] >= .12
                if self.rejected[side]:
                    continue
                self.commands[side] += np.clip(q - self.commands[side],
                    -MAX_JOINT_SPEED * min(dt, .05), MAX_JOINT_SPEED * min(dt, .05))
        for side, arm in self.arms.items():
            self.data.ctrl[arm['a']] = self.commands[side]
            attached = bool(self.data.eq_active[arm['weld']])
            if attached:
                self.gripper_closed[side] = True
            elif self.last_weld[side]:
                self.gripper_closed[side] = False
            self.last_weld[side] = attached
            if not self.held:
                desired = .035 if self.gripper_closed[side] else 0.
                self.grip_commands[side] += float(np.clip(desired - self.grip_commands[side],
                                                         -.15 * min(dt, .05), .15 * min(dt, .05)))
            self.data.ctrl[arm['fingers']] = self.grip_commands[side]
        return self.snapshot()

