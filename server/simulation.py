"""Local P0 rigid-body shared-autonomy simulation, with no real-world actuation."""
from __future__ import annotations
import io
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
            xml = xml.replace('<geom type="box" size=".075 .055 .025" mass=".15"', '<geom type="ellipsoid" size=".055 .035 .055" mass=".15"')
            xml = xml.replace('</equality>', '<weld body1="oven_anchor" body2="food" active="false" relpose="0 0 0 1 0 0 0"/></equality>')
        elif robot_id == 'tea':
            xml = xml.replace('<geom type="box" size=".075 .055 .025" mass=".15" rgba=".84 .47 .14 1" friction="1 .005 .0001"/>', '<geom type="cylinder" size=".045 .07" mass=".15" rgba=".72 .48 .23 1" friction="1 .005 .0001"/><geom type="cylinder" pos="0 0 .073" size=".05 .006" mass=".01" rgba=".9 .9 .85 1"/>')
            xml = xml.replace('pos="-.42 -.15 .77"', 'pos="-.42 -.15 .82"')
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        self.gripper = int(self.model.body('gripper').mocapid[0])
        mujoco.mj_forward(self.model, self.data)
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
        self.velocity = np.zeros(2)
        self.frames = {}
        self.renderer_error = None
        self.renderer = None

    @property
    def food(self):
        return self.data.body('food').xpos.copy()

    def hold(self, reason):
        self.lease.active = False
        self.lease.hold_reason = reason
        self.velocity[:] = 0
        self.action = None
        self.phase = 0
        self.dwell = 0

    def move(self, target, dt):
        delta = np.asarray(target) - self.data.mocap_pos[self.gripper]
        distance = np.linalg.norm(delta)
        self.data.mocap_pos[self.gripper] += delta * min(1, .55 * dt / max(distance, 1e-9))
        return distance < .012

    def step(self, dt):
        if self.id == 'pepper' and self.attached and self.data.eq_active[1] and np.linalg.norm(self.food - [0, .055, .9]) < .05:
            self.cook_time += dt
            if self.cook_time >= 3:
                self.cooked = True
                if self.stage == 'cook':
                    self.stage = 'retrieve'
                    self.action = None
        if self.lease.active:
            self.data.mocap_pos[self.gripper, :2] += self.velocity * dt * .3
            self.data.mocap_pos[self.gripper, :2] = np.clip(self.data.mocap_pos[self.gripper, :2], [-.65, -.48], [.65, .48])
            if self.action:
                self.auto_step(dt)
        mujoco.mj_step(self.model, self.data)

    def auto_step(self, dt):
        action = self.action
        if action == 'pick':
            target = self.food + [0, 0, .07] if self.phase == 0 else np.array([-.42, -.15, 1.1])
            if self.move(target, dt):
                if self.phase == 0 and np.linalg.norm(self.food - (self.data.mocap_pos[self.gripper] - [0, 0, .07])) < .035:
                    self.data.eq_active[0] = 1
                    self.phase = 1
                elif self.phase == 1 and self.food[2] > .94:
                    self.stage = {'jipai': 'season', 'pepper': 'attach', 'tea': 'tray'}[self.id]
                    self.action = None
        elif action == 'attach':
            if self.move([0, .055, .97], dt) and np.linalg.norm(self.food - [0, .055, .9]) < .04:
                self.data.eq_active[0] = 0
                self.data.eq_active[1] = 1
                self.attached = True
                self.stage = 'cook'
                self.action = None
        elif action == 'cook':
            pass
        elif action == 'retrieve':
            targets = [self.food + [0, 0, .07], [0, -.15, 1.12]]
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
            targets = [[.43, -.34, 1.1], [.43, -.34, .88]]
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
            targets = [self.food + [0, 0, .07], [.38, .2, 1.1], [.43, -.34, 1.1], [.43, -.34, .84]]
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

    def render(self):
        if self.renderer_error:
            return
        try:
            if self.renderer is None:
                self.renderer = mujoco.Renderer(self.model, height=320, width=480)
            for camera in ('first_person', 'top', 'wrist'):
                self.renderer.update_scene(self.data, camera=camera)
                output = io.BytesIO()
                Image.fromarray(self.renderer.render()).save(output, format='JPEG', quality=75)
                self.frames[camera] = output.getvalue()
        except Exception as exc:
            self.renderer_error = f'{type(exc).__name__}: {exc}'


class World:
    def __init__(self):
        self.robots = {rid: Robot(rid) for rid in ('jipai', 'pepper', 'tea')}
        self.seq = {}
        self.ledger = {}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.error = None

    def command(self, worker, cmd, now=None):
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
            lease = robot.lease
            kind = cmd.get('type')
            if kind == 'claim':
                if lease.owner not in (None, worker):
                    return 'robot_busy'
                for other in self.robots.values():
                    if other.id != robot.id and other.lease.owner == worker:
                        other.hold('switched_robot')
                        other.lease.owner = None
                if lease.owner is None:
                    lease.owner = worker
                    robot.hold('activation_required')
                lease.last_input = now
                return None
            if lease.owner != worker:
                return 'lease_required'
            if kind == 'activate':
                if self.error:
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
                for axis in ('x', 'y'):
                    value = cmd.get(axis, 0)
                    if type(value) not in (float, int) or not math.isfinite(value) or not -1 <= value <= 1:
                        robot.hold('invalid_control')
                        return 'invalid_control'
                action = cmd.get('action')
                if action is not None and action != robot.stage:
                    return 'wrong_stage'
                for flag in ('pinch', 'shake'):
                    if flag in cmd and type(cmd[flag]) is not bool:
                        return 'invalid_control'
                lease.last_input = now
                robot.velocity[:] = [cmd.get('x', 0), cmd.get('y', 0)]
                # Gestures request the next bounded shared-autonomy step.
                if not action and ((cmd.get('pinch') and robot.stage in ('pick', 'bag', 'deliver', 'attach', 'cook', 'retrieve', 'tray')) or (cmd.get('shake') and robot.stage == 'season')):
                    action = robot.stage
                if action and robot.action is None:
                    robot.action, robot.phase, robot.dwell = action, 0, 0
                    robot.velocity[:] = 0
            else:
                return 'unknown_command'
            return None

    def disconnect(self, worker, release=True, reason='disconnected'):
        with self.lock:
            for robot in self.robots.values():
                if robot.lease.owner == worker:
                    robot.hold(reason)
                    if release:
                        robot.lease.owner = None

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for robot in self.robots.values():
                if robot.lease.active and now - robot.lease.last_input > .75:
                    robot.hold('input_timeout')
                robot.step(.005)
                if robot.delivered:
                    order_id = f'order-{robot.id}'
                    self.ledger.setdefault(order_id, {'id': f'credit-{order_id}', 'order_id': order_id, 'robot_id': robot.id, 'amount': 12, 'currency': 'TEST', 'verified': True})

    def state(self):
        with self.lock:
            robots = []
            orders = []
            for robot in self.robots.values():
                robots.append({'id': robot.id, 'name': {'jipai': 'Hot Star Jipai', 'pepper': 'Pepper Bun', 'tea': 'Bubble Tea'}[robot.id], 'status': 'active' if robot.lease.active else 'held' if robot.lease.owner else 'available', 'owner': robot.lease.owner, 'active': robot.lease.active, 'stage': robot.stage, 'action': robot.action, 'hold_reason': robot.lease.hold_reason, 'position': robot.data.mocap_pos[robot.gripper].tolist(), 'food_position': robot.food.tolist(), 'grasped': bool(robot.data.eq_active[0]), 'seasoned': robot.seasoned, 'cooked': robot.cooked, 'cook_time': robot.cook_time, 'attached': robot.attached, 'trayed': robot.trayed, 'bagged': robot.bagged, 'delivered': robot.delivered, 'simulation_time': robot.data.time, 'camera_error': robot.renderer_error, 'cameras': {view: f'/api/robots/{robot.id}/frame?view={view}' for view in ('first_person', 'top', 'wrist')}})
                orders.append({'id': f'order-{robot.id}', 'robot_id': robot.id, 'item': {'jipai': 'Taiwanese fried chicken', 'pepper': 'Oven pepper bun', 'tea': 'Lidded bubble tea'}[robot.id], 'status': 'completed' if robot.delivered else 'in_progress', 'stage': robot.stage, 'test_credit': 12})
            return {'robots': robots, 'orders': orders, 'ledger': list(self.ledger.values()), 'server_time': int(time.time() * 1000), 'simulation': 'MuJoCo', 'simulation_error': self.error, 'test_mode': True}

    def start(self):
        self.thread = threading.Thread(target=self.run, name='mujoco-worker', daemon=True)
        self.thread.start()

    def run(self):
        last_render = 0
        try:
            while not self.stop.is_set():
                start = time.monotonic()
                for _ in range(4):
                    self.tick()
                if start - last_render > .25:
                    with self.lock:
                        for robot in self.robots.values():
                            robot.render()
                    last_render = start
                self.stop.wait(max(0, .02 - (time.monotonic() - start)))
        except Exception as exc:
            with self.lock:
                self.error = f'{type(exc).__name__}: {exc}'
                for robot in self.robots.values():
                    robot.hold('simulation_error')
        finally:
            for robot in self.robots.values():
                if robot.renderer:
                    robot.renderer.close()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
