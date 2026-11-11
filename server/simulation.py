"""Local P0 rigid-body shared-autonomy simulation, with no real-world actuation."""
from __future__ import annotations
import io
import copy
from collections import deque
import math
import threading
import time
from pathlib import Path
from dataclasses import dataclass

import mujoco
import numpy as np
from PIL import Image

XML = '''<mujoco model="night_shift">
<option timestep="0.005" gravity="0 0 -9.81"/>
<visual><global offwidth="480" offheight="320"/><headlight ambient=".4 .4 .4"/></visual>
<worldbody>
<light pos="0 0 3" diffuse=".9 .85 .7"/>
<geom name="floor" type="plane" size="3 3 .1" rgba=".08 .1 .12 1"/>
<geom name="counter" type="box" pos="0 0 .65" size=".85 .65 .05" rgba=".24 .3 .31 1"/>
<geom name="tray" type="box" pos="-.42 -.15 .715" size=".16 .17 .015" rgba=".55 .59 .62 1"/>
<geom name="season_zone" type="box" pos="0 .24 .71" size=".16 .14 .01" rgba=".76 .35 .16 1"/>
<geom name="bag_base" type="box" pos=".38 .2 .715" size=".13 .13 .015" rgba=".65 .46 .25 1"/>
<geom name="bag_back" type="box" pos=".38 .33 .80" size=".13 .01 .09" rgba=".65 .46 .25 1"/>
<geom name="bag_left" type="box" pos=".25 .2 .80" size=".01 .13 .09" rgba=".65 .46 .25 1"/>
<geom name="bag_right" type="box" pos=".51 .2 .80" size=".01 .13 .09" rgba=".65 .46 .25 1"/>
<geom name="delivery" type="box" pos=".43 -.34 .715" size=".19 .14 .015" rgba=".16 .55 .42 1"/>
<body name="food" pos="-.42 -.15 .77"><freejoint/><geom type="box" size=".075 .055 .025" mass=".15" rgba=".84 .47 .14 1" friction="1 .005 .0001"/></body>
<body name="gripper" mocap="true" pos="-.42 -.15 1.08">
<geom type="box" size=".095 .025 .025" rgba=".85 .87 .87 1" contype="0" conaffinity="0"/>
<geom type="box" pos="-.09 0 -.045" size=".012 .026 .05" rgba=".2 .65 .7 1" contype="0" conaffinity="0"/>
<geom type="box" pos=".09 0 -.045" size=".012 .026 .05" rgba=".2 .65 .7 1" contype="0" conaffinity="0"/>
<camera name="wrist" pos="0 -.06 .06" xyaxes="1 0 0 0 1 0" fovy="85"/>
</body>
<camera name="first_person" pos="0 -1.25 1.45" xyaxes="1 0 0 0 .48 .88" fovy="65"/>
<camera name="top" pos="0 0 2.6" xyaxes="1 0 0 0 1 0" fovy="55"/>
</worldbody>
<equality><weld name="grasp" body1="gripper" body2="food" active="false" relpose="0 0 -.07 1 0 0 0" solref=".015 1"/></equality>
</mujoco>'''

@dataclass
class Lease:
    owner: str | None = None
    active: bool = False
    last_input: float = 0
    hold_reason: str | None = None


class Robot:
    def __init__(self, robot_id):
        self.id = robot_id
        self.grasp_offset = .13 if robot_id == "tea" else .07
        xml = XML
        backdrop = Path(__file__).parent / 'assets' / 'market_backdrop.xml'
        if backdrop.exists():
            import xml.etree.ElementTree as ET
            extra = ET.parse(backdrop).getroot()
            if extra.tag == 'mujoco':
                extra = extra.find('worldbody')
            if extra is not None:
                xml = xml.replace('</worldbody>', ''.join(ET.tostring(child, encoding='unicode') for child in extra) + '</worldbody>')
        if robot_id == 'pepper':
            xml = xml.replace('<body name="food"', '<geom name="oven" type="cylinder" pos="0 .27 .87" size=".20 .17" rgba=".27 .19 .14 1"/><body name="oven_anchor" mocap="true" pos="0 .055 .9"/><body name="food"')
            xml = xml.replace('<geom type="box" size=".075 .055 .025" mass=".15"', '<geom type="ellipsoid" size=".055 .055 .035" mass=".15"')
            xml = xml.replace('</equality>', '<weld body1="oven_anchor" body2="food" active="false" relpose="0 0 0 1 0 0 0"/></equality>')
        elif robot_id == 'tea':
            xml = xml.replace('<geom type="box" size=".075 .055 .025" mass=".15" rgba=".84 .47 .14 1" friction="1 .005 .0001"/>', '<geom type="cylinder" size=".045 .07" mass=".15" rgba=".72 .48 .23 1" friction="1 .005 .0001"/><geom type="cylinder" pos="0 0 .073" size=".05 .006" mass=".01" rgba=".9 .9 .85 1"/>')
            xml = xml.replace('pos="-.42 -.15 .77"', 'pos="-.42 -.15 .82"')
        xml = xml.replace('-.42 -.15', '-.30 -.15')
        # Compact the task fixtures to the reach of the unscaled YAM arms.
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        worldbody = root.find('worldbody')
        task_names = {'tray', 'season_zone', 'bag_base', 'bag_back', 'bag_left', 'bag_right', 'delivery', 'food', 'oven', 'oven_anchor'}
        for element in worldbody:
            if element.get('name') not in task_names:
                continue
            for node in element.iter():
                if node.get('pos'):
                    pos = list(map(float, node.get('pos').split()))
                    pos[0] *= .55; pos[1] *= .55
                    node.set('pos', ' '.join(map(str, pos)))
                if node.tag == 'geom' and node.get('size'):
                    size = list(map(float, node.get('size').split()))
                    count = 1 if node.get('type') == 'cylinder' else min(2, len(size))
                    for index in range(count): size[index] *= .55
                    node.set('size', ' '.join(map(str, size)))
        if robot_id == 'jipai':
            asset = root.find('asset')
            if asset is None: asset = ET.SubElement(root, 'asset')
            vertices = []
            for z, radius in [(-.022,.78),(0.,1.),(.022,.76)]:
                for i in range(20):
                    angle = i * math.tau / 20
                    wobble = 1 + .055*math.sin(i*2.3)
                    vertices.extend([.061*radius*wobble*math.cos(angle),.043*radius*wobble*math.sin(angle),z])
            ET.SubElement(asset,'mesh',name='chicken_shape',vertex=' '.join(map(str,vertices)))
            food_geom = worldbody.find("body[@name='food']/geom")
            food_geom.set('type','mesh');food_geom.set('mesh','chicken_shape');food_geom.set('name','food_chicken')
            food_geom.attrib.pop('size',None)
        if robot_id == 'pepper':
            bun = worldbody.find("geom[@name='delivery']")
            bun.set('priority', '1')
            bun.set('condim', '6')
            bun.set('friction', '1 .02 .02')
        xml = ET.tostring(root, encoding='unicode')
        from server.workstation_visuals import decorate_scene
        xml = decorate_scene(xml, robot_id)
        if robot_id == 'pepper':
            root = ET.fromstring(xml)
            for node in root.iter('geom'):
                name = node.get('name', '')
                if name == 'oven':
                    node.set('pos', '0 -.19 .87')
                    node.set('size', '.09 .17')
                elif name.startswith(('workstation_brick_', 'workstation_oven_')):
                    position = list(map(float, node.get('pos').split()))
                    position[0] = position[0] * .55
                    position[1] = position[1] * .55 - .3385
                    node.set('pos', ' '.join(map(str, position)))
                    size = list(map(float, node.get('size').split()))
                    for index in range(1 if node.get('type') == 'cylinder' else 2): size[index] *= .55
                    node.set('size', ' '.join(map(str, size)))
            root.find(".//body[@name='oven_anchor']").set('pos', '0 -.07175 .9')
            xml = ET.tostring(root, encoding='unicode')
        from server.humanoid import augment_scene, HumanoidController
        from server.market_life import decorate_market_life
        xml = decorate_market_life(augment_scene(xml))
        self.model = mujoco.MjModel.from_xml_string(xml)
        if robot_id == 'tea':
            for name in ('grasp', 'right_grasp'):
                self.model.eq_data[self.model.equality(name).id, 5] = -self.grasp_offset
        if robot_id == "tea":
            # Multiple cylinder contacts prevent resting-cup rocking without fixing the free body.
            self.model.opt.enableflags |= int(mujoco.mjtEnableBit.mjENBL_MULTICCD)
        self.data = mujoco.MjData(self.model)
        self.gripper = int(self.model.body('gripper').mocapid[0])
        mujoco.mj_forward(self.model, self.data)
        self.controller = HumanoidController(self.model, self.data)
        # Frame the work surface from the head mount, accounting for the working lean.
        camera_id = self.model.camera('first_person').id
        camera_body = self.data.body(int(self.model.cam_bodyid[camera_id]))
        rotation = camera_body.xmat.reshape(3, 3)
        camera_position = np.array([0., -.10, 1.48])
        forward = np.array([0., -.80, .80]) - camera_position
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0., 0., 1.]); right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        local_rotation = rotation.T @ np.column_stack([right, up, -forward])
        self.model.cam_pos[camera_id] = rotation.T @ (camera_position - camera_body.xpos)
        mujoco.mju_mat2Quat(self.model.cam_quat[camera_id], local_rotation.ravel())
        self.model.cam_fovy[camera_id] = 100
        counter = self.model.geom('counter').id
        self.model.geom_pos[counter, 1] = -.23
        self.model.geom_size[counter, 1] = .42
        mujoco.mj_forward(self.model, self.data)
        self.data.mocap_pos[self.gripper] = np.array(self.controller.snapshot()["tcp"]) / [.55, .55, 1]
        self.lease = Lease()
        self.stage = 'pick'
        self.action = None
        self.phase = 0
        self.dwell = 0.0
        self.cook_time = 0.0
        self.attached = False
        self.cooked = False
        self.trayed = False
        self.seasoned = False
        self.bagged = False
        self.delivered = False
        self.lock = threading.RLock()
        self.frame_lock = threading.Lock()
        self.target = self.data.mocap_pos[self.gripper, :2].copy()
        self.pinched = False
        self.right_target = np.array(self.controller.snapshot()["arms"]["right"]["tcp"])
        self.hand_twist = 0.0
        self.direct_hands = False
        self.order_number = 1
        self.frame_timestamp = 0
        self.frame_timestamps = {}
        self.error = None
        self.render_model = None
        self.render_data = None
        self.food_geom = int(self.model.body('food').geomadr[0])
        self.original_food_rgba = self.model.geom_rgba[self.food_geom].copy()
        self.frames = {}
        self.renderer_error = None
        self.renderer = None
        from server.camera_quality import CameraQuality
        self.camera_quality = CameraQuality.from_env()

    @property
    def food(self):
        return self.data.body('food').xpos.copy() / np.array([.55, .55, 1])

    def hold(self, reason):
        self.lease.active = False
        self.lease.hold_reason = reason
        self.target[:] = self.data.mocap_pos[self.gripper, :2]
        self.action = None
        self.phase = 0
        self.dwell = 0

    def move(self, target, dt):
        delta = np.asarray(target) - self.data.mocap_pos[self.gripper]
        distance = np.linalg.norm(delta)
        self.data.mocap_pos[self.gripper] += delta * min(1, .55 * dt / max(distance, 1e-9))
        actual = np.array(self.controller.snapshot()["tcp"]) / [.55, .55, 1]
        return np.linalg.norm(np.asarray(target) - actual) < .018

    def step(self, dt):
        if self.id == 'pepper' and self.attached and self.data.eq_active[1] and np.linalg.norm(self.food - [0, -.13045455, .9]) < .05:
            self.cook_time += dt
            if self.cook_time >= 3:
                self.cooked = True
                if self.stage == 'cook':
                    self.stage = 'retrieve'
                    self.action = None
        if self.lease.active:
            if self.action:
                self.auto_step(dt)
                # Do not resume a stale hand target when the bounded action finishes.
                self.target[:] = self.data.mocap_pos[self.gripper, :2]
            else:
                target = self.data.mocap_pos[self.gripper].copy()
                target[:2] = np.clip(self.target, [-.65, -.48], [.65, .48])
                if self.id == 'tea' and not self.data.eq_active[0]:
                    # Approach the cup from above its lid. Raise before crossing
                    # its footprint so manual depth input cannot enter the cup.
                    food = self.data.body('food').xpos
                    if np.linalg.norm(target[:2] * .55 - food[:2]) < .10:
                        clearance = food[2] + self.grasp_offset
                        target[2] = max(target[2], clearance)
                        tcp = np.asarray(self.controller.snapshot()['tcp'])
                        if tcp[2] < clearance - .015:
                            target[:2] = tcp[:2] / .55
                self.move(target, dt)
        if self.cooked:
            self.model.geom_rgba[self.food_geom] = [.38, .14, .035, 1]
        elif self.seasoned:
            self.model.geom_rgba[self.food_geom] = [.88, .24, .055, 1]
        from server.market_life import update_market_life
        update_market_life(self.model, self.data, self.data.time, self.delivered, self.order_number)
        self.controller.step(self.data.mocap_pos[self.gripper] * [.55, .55, 1] if self.lease.active else None, self.action or self.stage, dt, bool(self.data.eq_active[0]), right_target_position=self.right_target if self.direct_hands else None, twist=self.hand_twist)
        mujoco.mj_step(self.model, self.data)

    def auto_step(self, dt):
        action = self.action
        if action == 'pick':
            target = self.food + [0, 0, self.grasp_offset] if self.phase == 0 else np.array([-.30, -.15, 1.1])
            if self.move(target, dt):
                if self.phase == 0 and self.controller.set_grasp('left', True):
                    self.phase = 1
                elif self.phase == 1 and self.food[2] > .94:
                    self.stage = {'jipai': 'season', 'pepper': 'attach', 'tea': 'tray'}[self.id]
                    self.action = None
        elif action == 'attach':
            if self.move([0, -.13045455, .97], dt) and np.linalg.norm(self.food - [0, -.13045455, .9]) < .04:
                self.data.eq_active[0] = 0
                self.data.eq_active[1] = 1
                self.attached = True
                self.stage = 'cook'
                self.action = None
        elif action == 'cook':
            pass
        elif action == 'retrieve':
            targets = [self.food + [0, 0, self.grasp_offset], [0, -.15, 1.12]]
            if self.move(targets[self.phase], dt):
                if self.phase == 0 and self.cooked:
                    self.data.eq_active[1] = 0
                    self.data.eq_active[0] = 1
                    self.attached = False
                    self.phase = 1
                elif self.phase == 1 and self.food[2] > .98:
                    self.stage = 'deliver'
                    self.action = None
        elif action == 'tray':
            targets = [[.43, -.34, 1.1], [.43, -.34, .94]]
            if self.phase < 2 and self.move(targets[self.phase], dt):
                self.phase += 1
                if self.phase == 2:
                    self.data.eq_active[0] = 0
            if self.phase == 2:
                self.dwell += dt
                upright = self.data.body('food').xmat[8] > .95
                if self.dwell > .5 and np.linalg.norm(self.food[:2] - [.43, -.34]) < .09 and .78 < self.food[2] < .85 and upright and np.linalg.norm(self.data.qvel[:3]) < .1:
                    self.trayed = True
                    self.stage = 'deliver'
                    self.action = None
        elif action == 'season':
            target = [0, .24, 1.08 + .025 * math.sin(self.data.time * 18)]
            if self.move(target, dt) and np.linalg.norm(self.food[:2] - [0, .24]) < .10 and self.food[2] > .9 and self.data.eq_active[0]:
                self.dwell += dt
                if self.dwell > 1.0:
                    self.seasoned = True
                    self.stage = 'bag'
                    self.action = None
        elif action == 'bag':
            targets = [[.38, .2, 1.1], [.38, .2, .84]]
            if self.phase < 2 and self.move(targets[self.phase], dt):
                self.phase += 1
                if self.phase == 2:
                    self.data.eq_active[0] = 0
            if self.phase == 2:
                self.dwell += dt
                if self.dwell > .5 and np.linalg.norm(self.food[:2] - [.38, .2]) < .085 and .73 < self.food[2] < .80 and np.linalg.norm(self.data.qvel[:3]) < .1:
                    self.bagged = True
                    self.stage = 'deliver'
                    self.action = None
        elif action == 'deliver':
            if self.id == 'tea':
                if self.trayed and np.linalg.norm(self.food[:2] - [.43, -.34]) < .09 and .78 < self.food[2] < .85 and self.data.body('food').xmat[8] > .95 and np.linalg.norm(self.data.qvel[:3]) < .1:
                    self.delivered = True
                    self.stage = 'complete'
                    self.action = None
                return
            # P0: bag is a fixed fixture; transfer the verified rigid serving to the pickup zone.
            carry_height = 1.23 if self.id == 'pepper' else 1.1
            targets = [self.food + [0, 0, self.grasp_offset], [.38, .2, carry_height], [.43, -.34, carry_height], [.43, -.34, .94 if self.id == 'pepper' else .84]]
            if self.phase < 4 and self.move(targets[self.phase], dt):
                if self.phase == 0:
                    self.data.eq_active[0] = 1
                self.phase += 1
                if self.phase == 4:
                    self.data.eq_active[0] = 0
            if self.phase == 4:
                self.dwell += dt
                if self.dwell > .5 and np.linalg.norm(self.food[:2] - [.43, -.34]) < .09 and .73 < self.food[2] < .8 and np.linalg.norm(self.data.qvel[:3]) < .1 and ((self.id == 'jipai' and self.seasoned and self.bagged) or (self.id == 'pepper' and self.cooked)):
                    self.delivered = True
                    self.stage = 'complete'
                    self.action = None

    @property
    def order_id(self):
        return f'order-{self.id}-{self.order_number}'

    @property
    def status(self):
        if not self.lease.active:
            return 'SAFE_HOLD'
        if self.action == 'deliver' or self.delivered:
            return 'VERIFYING'
        return 'AUTO' if self.action else 'REMOTE'

    def next_order(self):
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.model.geom_rgba[self.food_geom] = self.original_food_rgba
        self.controller.reset()
        self.stage = 'pick'
        self.action = None
        self.phase = 0
        self.dwell = self.cook_time = 0.0
        self.attached = self.cooked = self.trayed = False
        self.seasoned = self.bagged = self.delivered = False
        self.pinched = False
        self.order_number += 1
        self.hold('activation_required')
        with self.frame_lock:
            self.frames = {}
            self.frame_timestamps = {}
            self.frame_timestamp = 0

    def render(self):
        if self.renderer_error:
            return
        try:
            # Rendering owns its model/data and GL context; only snapshot copying
            # takes the physics lock, never GL calls or JPEG encoding.
            if self.render_model is None:
                with self.lock:
                    self.render_model = copy.copy(self.model)
                self.render_data = mujoco.MjData(self.render_model)
                self.camera_quality.configure_offscreen(self.render_model)
                self.renderer = mujoco.Renderer(self.render_model, **self.camera_quality.renderer_kwargs())
            with self.lock:
                self.render_data = copy.copy(self.data)
                self.render_model.geom_rgba[:] = self.model.geom_rgba
                order_number = self.order_number
                captured_at = int(time.time() * 1000)
            frames = {}
            for camera in ('first_person', 'top', 'wrist', 'operator'):
                self.renderer.update_scene(self.render_data, camera=camera)
                frames[camera] = self.camera_quality.encode_jpeg(self.renderer.render(), camera)
            with self.lock:
                if order_number != self.order_number:
                    return
                with self.frame_lock:
                    self.frames = frames
                    self.frame_timestamp = captured_at
                    self.frame_timestamps = dict.fromkeys(frames, self.frame_timestamp)
        except Exception as exc:
            self.renderer_error = f'{type(exc).__name__}: {exc}'


class World:
    def __init__(self):
        self.robots = {rid: Robot(rid) for rid in ('jipai', 'pepper', 'tea')}
        self.seq = {}
        self.ledger = {}
        self.lock = threading.RLock()  # Serializes lease transfers, never physics/render.
        self.ledger_lock = threading.Lock()
        self.telemetry_lock = threading.Lock()
        self.events = deque(maxlen=200)
        self.metrics = {}
        self.observations = {}
        self.event_seq = 0
        self.stop = threading.Event()
        self.threads = []
        self.error = None

    def record_event(self, kind, worker=None, robot=None, reason=None, now=None, **details):
        with self.telemetry_lock:
            self.event_seq += 1
            self.events.append(dict(id=self.event_seq, type=kind, worker_id=worker,
                                    robot_id=robot, reason=reason,
                                    timestamp_ms=int((time.time() if now is None else now) * 1000), **details))

    def command(self, worker, cmd, now=None):
        error = self._command(worker, cmd, now)
        if error or cmd.get('type') != 'control':
            self.record_event('rejected' if error else cmd.get('type'), worker,
                              cmd.get('robot_id'), error, now)
        return error

    def _command(self, worker, cmd, now=None):
        now = time.time() if now is None else now
        with self.lock:
            seq = cmd.get('seq')
            if type(seq) is not int or seq <= self.seq.get(worker, -1):
                self.disconnect(worker, release=False, reason='invalid_sequence')
                return 'invalid_sequence'
            stamp = cmd.get('sent_at')
            if type(stamp) not in (int, float) or not math.isfinite(stamp) or not -250 <= now * 1000 - stamp <= 1000:
                self.disconnect(worker, release=False, reason='stale_input')
                return 'stale_input'
            self.seq[worker] = seq
            robot = self.robots.get(cmd.get('robot_id'))
            if robot is None:
                return 'unknown_robot'
            if cmd.get('type') == 'claim':
                with robot.lock:
                    if robot.lease.owner not in (None, worker):
                        return 'robot_busy'
                for other in self.robots.values():
                    with other.lock:
                        if other.id != robot.id and other.lease.owner == worker:
                            other.hold('switched_robot')
                            other.lease.owner = None
                with robot.lock:
                    if robot.lease.owner is None:
                        robot.lease.owner = worker
                        robot.hold('activation_required')
                    robot.lease.last_input = now
                return None
            with robot.lock:
                return self._robot_command(robot, worker, cmd, now)

    def _robot_command(self, robot, worker, cmd, now):
        lease = robot.lease
        kind = cmd.get('type')
        if kind == 'next_order':
            if lease.owner not in (None, worker):
                return 'lease_required'
            if not robot.delivered:
                return 'order_not_complete'
            robot.next_order()
            return None
        if lease.owner != worker:
            return 'lease_required'
        if kind == 'rehearse':
            # Explicit simulator rehearsal restart; no completion/reward is issued.
            robot.next_order()
            robot.direct_hands = False
            lease.last_input = now
            return None
        if kind == 'activate':
            if robot.error:
                return 'simulation_unavailable'
            lease.active = True
            lease.hold_reason = None
            lease.last_input = now
        elif kind == 'hold':
            robot.hold('operator_hold')
        elif kind == 'release':
            robot.hold('released')
            lease.owner = None
        elif kind == 'control':
            if not lease.active:
                return 'activation_required'
            if 'frame_timestamp' in cmd:
                stamp = cmd['frame_timestamp']
                with robot.frame_lock:
                    latest = max(robot.frame_timestamp, getattr(robot, "visual_timestamp", 0))
                if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                        or stamp <= 0 or stamp > latest or not 0 <= now * 1000 - stamp <= 1000):
                    robot.hold('stale_frame')
                    return 'stale_frame'
            for axis in ('x', 'y'):
                value = cmd.get(axis, 0)
                if type(value) not in (float, int) or not math.isfinite(value) or not -1 <= value <= 1:
                    robot.hold('invalid_control')
                    return 'invalid_control'
            action = cmd.get('action')
            if action is not None and (action != robot.stage or action == 'complete'):
                return 'wrong_stage'
            for flag in ('pinch', 'shake'):
                if flag in cmd and type(cmd[flag]) is not bool:
                    robot.hold('invalid_control')
                    return 'invalid_control'
            hands = cmd.get('hands')
            if hands is not None:
                if not isinstance(hands, dict) or set(hands) != {'left', 'right'}:
                    robot.hold('invalid_hands'); return 'invalid_hands'
                for side, hand in hands.items():
                    if not isinstance(hand, dict) or type(hand.get('tracked')) is not bool or type(hand.get('pinch')) is not bool:
                        robot.hold('invalid_hands'); return 'invalid_hands'
                    for extra, limit in (('depth', .12), ('twist', .6)):
                        value = hand.get(extra, 0)
                        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
                            robot.hold('invalid_hands'); return 'invalid_hands'
                    for axis in ('x', 'y'):
                        value = hand.get(axis)
                        if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
                            robot.hold('invalid_hands'); return 'invalid_hands'
                if not any(hand['tracked'] for hand in hands.values()):
                    robot.hold('tracking_lost'); return 'tracking_lost'
                # Consume edges even during assisted motion: holding a pinch must
                # never automatically execute the next order step.
                pinch = any(h['tracked'] and h['pinch'] for h in hands.values())
                closing = pinch and not robot.pinched
                opening = not pinch and robot.pinched
                robot.pinched = pinch
                if not action and robot.action is None:
                    if closing and robot.stage in ('pick', 'retrieve', 'deliver'):
                        action = robot.stage
                    elif opening and robot.stage in ('bag', 'attach', 'tray'):
                        action = robot.stage
                    elif robot.stage == 'season' and (closing or cmd.get('shake')):
                        action = robot.stage
                robot.direct_hands = not bool(action or robot.action)
                for side, hand in hands.items():
                    if action or robot.action: continue
                    if not hand['tracked']: continue
                    if side == 'left':
                        robot.target[:] = [hand['x'] * .65, hand['y'] * .48]
                        current = robot.data.mocap_pos[robot.gripper, 2]
                        robot.data.mocap_pos[robot.gripper, 2] += float(np.clip(.96 - hand.get('depth', 0) - current, -.008, .008))
                        robot.hand_twist += float(np.clip(hand.get('twist', 0) - robot.hand_twist, -.04, .04))
                    else:
                        robot.right_target[:2] = [hand['x'] * .65 * .55, hand['y'] * .48 * .55]
                        robot.right_target[2] += float(np.clip(.96 - hand.get('depth', 0) - robot.right_target[2], -.008, .008))
                    robot.controller.set_grasp(side, hand['pinch'])
                lease.last_input = now
                if action and robot.action is None:
                    robot.action, robot.phase, robot.dwell = action, 0, 0
                return None
            robot.direct_hands = False
            lease.last_input = now
            pinch = cmd.get('pinch', False)
            pinch_edge = pinch and not robot.pinched
            robot.pinched = pinch
            if not action and ((pinch_edge and robot.stage in ('pick', 'bag', 'deliver', 'attach', 'cook', 'retrieve', 'tray')) or (cmd.get('shake') and robot.stage == 'season')):
                action = robot.stage
            if action and robot.action is None:
                robot.action, robot.phase, robot.dwell = action, 0, 0
            elif robot.action is None and not robot.delivered:
                robot.target[:] = [cmd.get('x', 0) * .65, cmd.get('y', 0) * .48]
        else:
            return 'unknown_command'
        return None

    def disconnect(self, worker, release=True, reason='disconnected'):
        with self.lock:
            for robot in self.robots.values():
                with robot.lock:
                    if robot.lease.owner == worker:
                        robot.hold(reason)
                        self.record_event('hold', worker, robot.id, reason)
                        if release:
                            robot.lease.owner = None

    def tick_robot(self, robot, now=None):
        now = time.time() if now is None else now
        with robot.lock:
            # These counters measure sampled elapsed wall time while a worker
            # owns a lease: manual REMOTE time versus autonomy/held waiting.
            previous = self.observations.get(robot.id)
            if previous:
                stamp, owner, status = previous
                if owner:
                    with self.telemetry_lock:
                        metrics = self.metrics.setdefault(owner, {'worker_id': owner, 'intervention_seconds': 0.0, 'wait_seconds': 0.0})
                        key = 'intervention_seconds' if status == 'REMOTE' else 'wait_seconds'
                        metrics[key] += max(0, now - stamp)
            if robot.lease.active and now - robot.lease.last_input > .75:
                robot.hold('input_timeout')
                self.record_event('hold', robot.lease.owner, robot.id, 'input_timeout', now)
            if robot.lease.owner and not robot.lease.active and now - robot.lease.last_input > 15:
                self.record_event('release', robot.lease.owner, robot.id, 'lease_expired', now)
                robot.hold('lease_expired')
                robot.lease.owner = None
            step_started = time.monotonic()
            robot.step(.005)
            robot.last_step_ms = (time.monotonic() - step_started) * 1000
            self.observations[robot.id] = (now, robot.lease.owner, robot.status)
            if robot.delivered:
                with self.ledger_lock:
                    is_new = robot.order_id not in self.ledger
                    self.ledger.setdefault(robot.order_id, {'id': f'credit-{robot.order_id}', 'order_id': robot.order_id, 'robot_id': robot.id, 'worker_id': robot.lease.owner, 'amount': 12, 'currency': 'TEST', 'verified': True})
                    if is_new:
                        self.record_event('verified_reward', robot.lease.owner, robot.id, now=now, order_id=robot.order_id, amount=12, currency='TEST')

    def tick(self, now=None):
        for robot in self.robots.values():
            self.tick_robot(robot, now)

    def state(self):
        robots, orders = [], []
        for robot in self.robots.values():
            with robot.lock:
                robots.append({'id': robot.id, 'name': {'jipai': 'Hot Star Jipai', 'pepper': 'Pepper Bun', 'tea': 'Bubble Tea'}[robot.id], 'status': robot.status, 'owner': robot.lease.owner, 'active': robot.lease.active, 'stage': robot.stage, 'action': robot.action, 'hold_reason': robot.lease.hold_reason, 'position': robot.data.mocap_pos[robot.gripper].tolist(), 'embodiment': robot.controller.snapshot(), 'order_number': robot.order_number, 'food_position': robot.food.tolist(), 'grasped': bool(robot.data.eq_active[0]), 'seasoned': robot.seasoned, 'cooked': robot.cooked, 'cook_time': robot.cook_time, 'attached': robot.attached, 'trayed': robot.trayed, 'bagged': robot.bagged, 'delivered': robot.delivered, 'simulation_time': robot.data.time, 'camera_error': robot.renderer_error, 'simulation_error': robot.error, 'frame_timestamp': robot.frame_timestamp, 'cameras': {view: f'/api/robots/{robot.id}/frame?view={view}' for view in ('first_person', 'top', 'wrist', 'operator')}})
                orders.append({'id': robot.order_id, 'robot_id': robot.id, 'item': {'jipai': 'Taiwanese fried chicken', 'pepper': 'Oven pepper bun', 'tea': 'Lidded bubble tea'}[robot.id], 'status': 'completed' if robot.delivered else 'in_progress', 'stage': robot.stage, 'test_credit': 12})
        with self.ledger_lock:
            ledger = list(self.ledger.values())
        with self.telemetry_lock:
            events = list(self.events)
            metrics = {worker: dict(value) for worker, value in self.metrics.items()}
        return {'robots': robots, 'orders': orders, 'ledger': ledger, 'events': events, 'metrics': metrics, 'server_time': int(time.time() * 1000), 'simulation': 'MuJoCo', 'simulation_error': self.error, 'test_mode': True}

    def start(self):
        if self.threads:
            return
        for robot in self.robots.values():
            for target, name in ((self.run_robot, 'physics'), (self.run_renderer, 'camera')):
                thread = threading.Thread(target=target, args=(robot,), name=f'{robot.id}-{name}', daemon=True)
                self.threads.append(thread)
                thread.start()

    def run_robot(self, robot):
        try:
            while not self.stop.is_set():
                start = time.monotonic()
                self.tick_robot(robot)
                # Expensive IK must yield between steps: immediate lock re-entry
                # starves visual snapshots and incoming control commands.
                self.stop.wait(max(.001, .005 - (time.monotonic() - start)))
        except Exception as exc:
            with robot.lock:
                robot.error = f'{type(exc).__name__}: {exc}'
                robot.hold('simulation_error')

    def run_renderer(self, robot):
        try:
            while not self.stop.is_set():
                start = time.monotonic()
                if time.monotonic() - getattr(robot, "render_requested_at", 0) < 3:
                    robot.render()
                self.stop.wait(max(0, .25 - (time.monotonic() - start)))
        finally:
            if robot.renderer:
                robot.renderer.close()

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=5)
