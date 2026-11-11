"""Official, unscaled YAM v1 chains with simulated joint servo control and DLS IK.

The left arm carries food; the right arm moves a seasoning tool. No hardware IO.
"""
from __future__ import annotations

import copy
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

ASSETS = Path(__file__).resolve().parent / 'assets' / 'yam'
MAX_JOINT_SPEED = 1.5  # rad/s command slew limit; not a hardware specification


def augment_scene(xml: str) -> str:
    """Append two official chains after food, retaining qpos/equality ordering."""
    root = ET.fromstring(xml)
    compiler = root.find('compiler')
    if compiler is None:
        compiler = ET.SubElement(root, 'compiler')
    compiler.set('angle', 'radian')
    option = root.find('option')
    if option is not None:
        option.set('integrator', 'implicitfast')
    world = root.find('worldbody')
    if world is None:
        raise ValueError('scene requires worldbody')
    target = world.find("body[@name='gripper']")
    if target is None:
        raise ValueError('scene requires gripper mocap target')
    for geom in target.findall('geom'):
        geom.set('rgba', '0 0 0 0')
        geom.set('contype', '0')
        geom.set('conaffinity', '0')
    camera = target.find("camera[@name='wrist']")
    if camera is not None:
        target.remove(camera)
    first_person = world.find("camera[@name='first_person']")
    if first_person is not None:
        first_person.set('pos', '0 .85 1.65')
        first_person.set('xyaxes', '-1 0 0 0 -.63 .78')
        first_person.set('fovy', '70')
    if world.find("camera[@name='operator']") is None:
        ET.SubElement(world, 'camera', name='operator', pos='0 -1.5 1.65',
                      xyaxes='1 0 0 0 .35 .94', fovy='70')
    asset = root.find('asset')
    if asset is None:
        asset = ET.SubElement(root, 'asset')
    actuator = root.find('actuator')
    if actuator is None:
        actuator = ET.SubElement(root, 'actuator')
    source = ET.parse(ASSETS / 'yam.xml').getroot()
    for side, pos in [('left', '0 .24 1.04'), ('right', '.30 .34 1.18')]:
        for original in source.find('asset'):
            mesh = copy.deepcopy(original)
            mesh.set('name', f'{side}_{mesh.get("name")}')
            mesh.set('file', str(ASSETS / 'assets' / mesh.get('file')))
            asset.append(mesh)
        body = copy.deepcopy(source.find('worldbody/body'))
        for element in body.iter():
            if element.get('name'):
                element.set('name', f'{side}_{element.get("name")}')
            if element.get('mesh'):
                element.set('mesh', f'{side}_{element.get("mesh")}')
            if element.tag == 'joint':
                element.set('damping', '2')
                element.set('armature', '.03')
                ET.SubElement(actuator, 'position', name=element.get('name') + '_servo',
                              joint=element.get('name'), kp='250', kv='22',
                              ctrlrange=element.get('range'), forcerange='-10 10')
            if element.tag == 'geom':
                # Mesh contacts are excluded in this prototype; food-fixture contacts remain.
                element.set('contype', '0')
                element.set('conaffinity', '0')
        body.set('pos', pos)
        body.set('quat', '1 0 0 0')
        # Gravity compensation is an explicit simulated controller approximation.
        for link in body.iter('body'):
            link.set('gravcomp', '1')
        flange = body.find(f".//body[@name='{side}_gripper']")
        tcp = ET.SubElement(flange, 'body', name=f'{side}_tcp', pos='0 0 .10', quat='0 1 0 0')
        ET.SubElement(tcp, 'geom', name=f'{side}_palm', type='box', size='.095 .025 .018',
                      mass='.12', rgba='.12 .16 .19 1', contype='0', conaffinity='0')
        for index, sign in enumerate((-1, 1)):
            finger = ET.SubElement(tcp, 'body', name=f'{side}_finger{index}',
                                   pos=f'{sign * .07} 0 -.045')
            name = f'{side}_finger{index}_slide'
            ET.SubElement(finger, 'joint', name=name, type='slide', axis=f'{-sign} 0 0',
                          range='0 .045', damping='2', armature='.005')
            ET.SubElement(finger, 'geom', type='box', size='.008 .022 .04', mass='.02',
                          rgba='.14 .70 .72 1', contype='0', conaffinity='0')
            ET.SubElement(actuator, 'position', name=name + '_servo', joint=name,
                          kp='200', kv='5', ctrlrange='0 .045', forcerange='-2 2')
        ET.SubElement(tcp, 'site', name=f'{side}_tcp_site', size='.005', rgba='0 1 0 0')
        if side == 'left' and camera is not None:
            tcp.append(camera)
        if side == 'right':
            ET.SubElement(tcp, 'geom', name='right_seasoning_tool', type='cylinder',
                          pos='0 0 .06', size='.025 .045', mass='.08',
                          rgba='.80 .52 .16 1', contype='0', conaffinity='0')
        x, y, z = map(float, pos.split())
        ET.SubElement(world, 'geom', name=f'{side}_mount', type='cylinder',
                      pos=f'{x} {y} {(z + .70) / 2}', size=f'.045 {(z - .70) / 2}',
                      rgba='.20 .23 .26 1', contype='0', conaffinity='0')
        world.append(body)
    grasp = root.find("equality/weld[@name='grasp']")
    if grasp is None:
        raise ValueError('scene requires grasp equality')
    grasp.set('body1', 'left_tcp')
    ET.SubElement(root.find('equality'), 'weld', name='right_grasp', body1='right_tcp',
                  body2='food', active='false', relpose='0 0 -.07 1 0 0 0', solref='.015 1')
    return ET.tostring(root, encoding='unicode')


class DualYamController:
    """IK runs on scratch data; only joint actuators move the live simulation.

    Call step before each mj_step. Call snapshot after mj_step for current state.
    hold() latches the present servo targets until the next non-hold step.
    """

    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData):
        self.model, self.data = model, data
        self.scratch = mujoco.MjData(model)
        self.arms = {}
        for side in ('left', 'right'):
            joints = [model.joint(f'{side}_joint{i}') for i in range(1, 7)]
            self.arms[side] = dict(
                q=np.array([j.qposadr[0] for j in joints]),
                v=np.array([j.dofadr[0] for j in joints]),
                a=np.array([model.actuator(f'{side}_joint{i}_servo').id for i in range(1, 7)]),
                limits=np.array([j.range.copy() for j in joints]),
                site=model.site(f'{side}_tcp_site').id,
                fingers=np.array([model.actuator(f'{side}_finger{i}_slide_servo').id for i in range(2)]),
                weld=model.equality('grasp' if side == 'left' else 'right_grasp').id,
            )
        self.targets = {'left': np.array([-.231, -.0825, 1.08]), 'right': np.array([0., .132, 1.25])}
        self.commands = {}
        self.gripper_closed = {'left': False, 'right': False}
        self.grip_commands = {'left': 0., 'right': 0.}
        self.last_weld = {'left': False, 'right': False}
        self.ik_errors = {'left': float('inf'), 'right': float('inf')}
        self.held = False
        self.orientation_errors = {'left': 0., 'right': 0.}
        self.rejected = {'left': False, 'right': False}
        self.reset()

    def solve(self, side, target, seed=None, iterations=80, orientation=None):
        """Return bounded joint solution and position error; never mutate live qpos."""
        arm = self.arms[side]
        self.scratch.qpos[:] = self.data.qpos
        q = np.array(seed if seed is not None else self.data.qpos[arm['q']], dtype=float)
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros_like(jacp)
        for _ in range(iterations):
            self.scratch.qpos[arm['q']] = q
            mujoco.mj_kinematics(self.model, self.scratch)
            mujoco.mj_comPos(self.model, self.scratch)
            position = self.scratch.site_xpos[arm['site']]
            rotation = self.scratch.site_xmat[arm['site']].reshape(3, 3)
            # Keep the tool vertical; free yaw avoids an artificial wrist singularity.
            if orientation is None:
                orient = np.cross(rotation[:, 2], np.array([0., 0, 1.]))
                if rotation[2, 2] < -.99:
                    orient = np.array([1., 0, 0])
                orient = orient[:2]
            else:
                quat = np.zeros(4)
                mujoco.mju_mat2Quat(quat, rotation.ravel())
                orient = np.zeros(3)
                mujoco.mju_subQuat(orient, orientation, quat)
            error = np.r_[np.asarray(target) - position, .35 * orient]
            if np.linalg.norm(error) < 1e-5:
                break
            mujoco.mj_jacSite(self.model, self.scratch, jacp, jacr, arm['site'])
            jac = np.vstack((jacp[:, arm['v']], .35 * jacr[:len(orient), arm['v']]))
            dq = jac.T @ np.linalg.solve(jac @ jac.T + .025**2 * np.eye(len(error)), error)
            q = np.clip(q + dq * min(1., .2 / max(np.linalg.norm(dq), 1e-9)), arm['limits'][:, 0] + 1e-4, arm['limits'][:, 1] - 1e-4)
        self.scratch.qpos[arm['q']] = q
        mujoco.mj_forward(self.model, self.scratch)
        rotation = self.scratch.site_xmat[arm['site']].reshape(3, 3)
        if orientation is None:
            angle = np.arccos(np.clip(rotation[2, 2], -1, 1))
        else:
            quat = np.zeros(4)
            mujoco.mju_mat2Quat(quat, rotation.ravel())
            delta = np.zeros(3)
            mujoco.mju_subQuat(delta, orientation, quat)
            angle = np.linalg.norm(delta)
        self.orientation_errors[side] = float(angle)
        return q, float(np.linalg.norm(np.asarray(target) - self.scratch.site_xpos[arm['site']]))

    def reset(self, target_position=None):
        """Initialize ONLY robot joints before running physics; never reposition food."""
        if target_position is not None:
            self.targets['left'] = np.asarray(target_position, dtype=float).copy()
        for side, arm in self.arms.items():
            seed = [-2.2, 2.3, 1.8, -1., 0, 0] if side == 'left' else [-2.4, 2.2, 1.8, -1., 0, 0]
            q, error = self.solve(side, self.targets[side], seed, 180)
            self.data.qpos[arm['q']] = q
            self.data.qvel[arm['v']] = 0
            self.data.ctrl[arm['a']] = q
            self.commands[side] = q.copy()
            self.ik_errors[side] = error
            self.rejected[side] = error >= .015 or self.orientation_errors[side] >= .12
        self.held = False
        mujoco.mj_forward(self.model, self.data)

    def hold(self):
        """Freeze commanded poses, retaining any live food weld."""
        self.held = True

    def set_grasp(self, side: str, closed: bool) -> bool:
        """Explicit open/close; attach only near food, never teleport or double-weld.

        Returns whether this arm holds the food. Closing away from food still closes
        the physical fingers but does not attach. Opening releases only this arm.
        """
        if side not in self.arms:
            raise ValueError('side must be left or right')
        arm = self.arms[side]
        self.gripper_closed[side] = bool(closed)
        if not closed:
            self.data.eq_active[arm['weld']] = 0
        elif not self.data.eq_active[arm['weld']]:
            food_id = self.model.body('food').id
            occupied = any(self.data.eq_active[i] and
                (self.model.eq_obj1id[i] == food_id or self.model.eq_obj2id[i] == food_id)
                for i in range(self.model.neq) if i != arm['weld'])
            tcp = self.data.body(f'{side}_tcp')
            pickup = tcp.xpos + tcp.xmat.reshape(3, 3) @ self.model.eq_data[arm['weld'], 3:6]
            if not occupied and np.linalg.norm(self.data.body('food').xpos - pickup) < .035:
                # Capture the actual relative pose: enabling a grasp must not
                # snap/rotate the food to a preconfigured pose through the hand.
                food = self.data.body('food')
                relative = tcp.xmat.reshape(3, 3).T @ (food.xpos - tcp.xpos)
                inverse = tcp.xquat.copy(); inverse[1:] *= -1
                relative_quat = np.empty(4)
                mujoco.mju_mulQuat(relative_quat, inverse, food.xquat)
                self.model.eq_data[arm['weld'], 3:6] = relative
                self.model.eq_data[arm['weld'], 6:10] = relative_quat
                self.data.eq_active[arm['weld']] = 1
        self.last_weld[side] = bool(self.data.eq_active[arm['weld']])
        return self.last_weld[side]

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
                targets['right'] = np.array([0., .132, 1.25])
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
                q, error = self.solve(side, targets[side], self.commands[side], 80,
                                      orientation=orientations[side])
                self.ik_errors[side] = error
                self.rejected[side] = error >= .015 or self.orientation_errors[side] >= .12
                if self.rejected[side]:
                    continue
                if side == 'left' and left_orientation is None:
                    q[5] = np.clip(twist, -.6, .6)
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

    def snapshot(self):
        tcp = self.data.site_xpos[self.arms['left']['site']].copy()
        error = float(np.linalg.norm(tcp - self.targets['left']))
        return {'embodiment': 'dual_yam', 'active_arm': 'left', 'tcp': tcp.tolist(),
                'target': self.targets['left'].tolist(), 'ik_error': error,
                'reachable': not self.rejected['left'],
                'valid': bool(np.all(np.isfinite(self.data.qpos)) and error < .035),
                'held': self.held, 'arms': {side: {
                    'gripper_closed': self.gripper_closed[side],
                    'grasped': bool(self.data.eq_active[a['weld']]),
                    'joint_positions': self.data.qpos[a['q']].tolist(),
                    'joint_velocities': self.data.qvel[a['v']].tolist(),
                    'tcp': self.data.site_xpos[a['site']].tolist(),
                    'ik_error': float(np.linalg.norm(self.data.site_xpos[a['site']] - self.targets[side])),
                    'solver_error': self.ik_errors[side],
                    'orientation_error': self.orientation_errors[side],
                    'reachable': not self.rejected[side],
                    'rejection_reason': 'unreachable_pose' if self.rejected[side] else None,
                } for side, a in self.arms.items()}}
