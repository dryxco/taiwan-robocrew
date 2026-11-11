import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from server.simulation import World


@pytest.fixture
def world():
    value = World()
    yield value
    value.close()


def command(world, worker, robot, kind, **values):
    now = values.pop('now', 100)
    return world.command(worker, dict(seq=world.seq.get(worker, -1) + 1,
                         sent_at=now * 1000, robot_id=robot, type=kind, **values), now=now)


def activate(world, worker, robot):
    assert command(world, worker, robot, 'claim') is None
    assert command(world, worker, robot, 'activate') is None


def complete(world, worker, rid):
    robot = world.robots[rid]
    for _ in range(10):
        stage = robot.stage
        if stage == 'complete':
            return
        assert command(world, worker, rid, 'control', action=stage) is None
        assert robot.status == ('VERIFYING' if stage == 'deliver' else 'AUTO')
        for _ in range(6000):
            world.tick_robot(robot, now=100)
            if robot.stage != stage:
                break
        else:
            pytest.fail(f'{rid} stalled at {stage}: {robot.food}, phase {robot.phase}')
    pytest.fail('workflow failed to complete')


@pytest.mark.parametrize('rid', ['jipai', 'pepper', 'tea'])
def test_verified_orders_reward_owner_once_and_repeat(world, rid):
    activate(world, 'alice', rid)
    initial = world.robots[rid].original_food_rgba.copy()
    complete(world, 'alice', rid)
    robot = world.robots[rid]
    assert robot.delivered
    assert len(world.ledger) == 1
    reward = next(iter(world.ledger.values()))
    assert reward['worker_id'] == 'alice'
    if rid != 'tea':
        assert not np.allclose(initial, robot.model.geom_rgba[robot.food_geom])
    for _ in range(10):
        world.tick_robot(robot, now=100)
    assert len(world.ledger) == 1
    assert command(world, 'bob', rid, 'next_order') == 'lease_required'
    robot.frames['first_person'] = b'old-order'
    robot.frame_timestamp = 99999
    assert command(world, 'alice', rid, 'next_order') is None
    assert robot.frame_timestamp == 0 and not robot.frames
    assert robot.stage == 'pick' and robot.status == 'SAFE_HOLD'
    assert command(world, 'alice', rid, 'next_order') == 'order_not_complete'
    assert command(world, 'alice', rid, 'activate') is None
    complete(world, 'alice', rid)
    assert len(world.ledger) == 2
    assert len({row['order_id'] for row in world.ledger.values()}) == 2
    assert command(world, 'alice', rid, 'release') is None
    assert command(world, 'bob', rid, 'next_order') is None
    assert robot.lease.owner is None
    assert all(row['worker_id'] == 'alice' for row in world.ledger.values())


def test_same_robot_exclusive_and_one_robot_per_worker(world):
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda w: command(world, w, 'tea', 'claim'), ['alice', 'bob']))
    assert sorted(str(v) for v in results) == ['None', 'robot_busy']
    owner = world.robots['tea'].lease.owner
    assert command(world, owner, 'jipai', 'claim') is None
    assert world.robots['tea'].lease.owner is None
    assert world.robots['tea'].lease.hold_reason == 'switched_robot'
    assert sum(r.lease.owner == owner for r in world.robots.values()) == 1


def test_simultaneous_workers_finish_independent_orders(world):
    for worker, rid in [('alice', 'tea'), ('bob', 'jipai'), ('carol', 'pepper')]:
        activate(world, worker, rid)
    with ThreadPoolExecutor(3) as pool:
        futures = [pool.submit(complete, world, worker, rid) for worker, rid in
                   [('alice', 'tea'), ('bob', 'jipai'), ('carol', 'pepper')]]
        for future in futures:
            future.result(timeout=30)
    assert {r['worker_id'] for r in world.ledger.values()} == {'alice', 'bob', 'carol'}


def test_target_is_bounded_smooth_and_stationary(world):
    activate(world, 'alice', 'tea')
    robot = world.robots['tea']
    start = robot.data.mocap_pos[robot.gripper].copy()
    assert command(world, 'alice', 'tea', 'control', x=1, y=-1) is None
    world.tick_robot(robot, now=100)
    assert np.linalg.norm(robot.data.mocap_pos[robot.gripper] - start) <= .55 * .005 + 1e-9
    for _ in range(1000):
        world.tick_robot(robot, now=100)
    np.testing.assert_allclose(robot.data.mocap_pos[robot.gripper, :2], [.65, -.48])
    for _ in range(50):
        assert command(world, 'alice', 'tea', 'control', x=1, y=-1) is None
        world.tick_robot(robot, now=100)
    np.testing.assert_allclose(robot.data.mocap_pos[robot.gripper, :2], [.65, -.48])
    assert command(world, 'alice', 'tea', 'control', x=1.01) == 'invalid_control'
    assert robot.status == 'SAFE_HOLD'


def test_pinch_edge_and_manual_targets_do_not_interrupt_autonomy(world):
    activate(world, 'alice', 'tea')
    robot = world.robots['tea']
    assert robot.status == 'REMOTE'
    assert command(world, 'alice', 'tea', 'control', pinch=True) is None
    assert robot.status == 'AUTO'
    for _ in range(3000):
        assert command(world, 'alice', 'tea', 'control', pinch=True, x=1, y=1) is None
        world.tick_robot(robot, now=100)
        if robot.stage != 'pick':
            break
    assert robot.stage == 'tray'
    assert command(world, 'alice', 'tea', 'control', pinch=True) is None
    assert robot.action is None
    assert command(world, 'alice', 'tea', 'control', pinch=False) is None
    assert command(world, 'alice', 'tea', 'control', pinch=True) is None
    assert robot.action == 'tray'


def test_stale_frame_and_input_timeout(world):
    activate(world, 'alice', 'tea')
    robot = world.robots['tea']
    robot.frame_timestamp = 100000
    assert command(world, 'alice', 'tea', 'control', frame_timestamp=100000) is None
    assert command(world, 'alice', 'tea', 'control', frame_timestamp=98000) == 'stale_frame'
    assert robot.lease.hold_reason == 'stale_frame'
    assert robot.frame_timestamp == 100000
    assert command(world, 'alice', 'tea', 'activate') is None
    assert command(world, 'alice', 'tea', 'control', pinch=True) is None
    world.tick_robot(robot, now=100.751)
    assert robot.status == 'SAFE_HOLD' and robot.action is None
    assert robot.lease.hold_reason == 'input_timeout'
    assert robot.frame_timestamp == 100000


def test_retry_cannot_duplicate_completed_reward(world):
    activate(world, 'alice', 'tea')
    complete(world, 'alice', 'tea')
    seq = world.seq['alice']
    assert world.command('alice', dict(seq=seq, sent_at=100000, robot_id='tea', type='control', action='deliver'), now=100) == 'invalid_sequence'
    world.tick(now=100)
    assert len(world.ledger) == 1
    assert next(iter(world.ledger.values()))['worker_id'] == 'alice'


def test_slow_renderer_does_not_block_any_physics_or_commands(world, monkeypatch):
    entered, unblock = threading.Event(), threading.Event()
    def slow():
        entered.set()
        unblock.wait(3)
    for robot in world.robots.values():
        monkeypatch.setattr(robot, 'render', lambda: None)
    monkeypatch.setattr(world.robots['tea'], 'render', slow)
    world.start()
    try:
        assert entered.wait(1)
        assert command(world, 'alice', 'tea', 'claim', now=time.time()) is None
        before = [r.data.time for r in world.robots.values()]
        time.sleep(.06)
        after = [r.data.time for r in world.robots.values()]
        assert all(b > a for a, b in zip(before, after))
        assert world.state()['robots']
    finally:
        unblock.set()


def test_frame_endpoint_timestamp(world):
    from server.app import app, frame
    app.state.world = world
    robot = world.robots['tea']
    robot.frames['first_person'] = b'jpeg'
    robot.frame_timestamps['first_person'] = 123
    response = frame('tea')
    assert response.headers['x-frame-timestamp'] == '123'
    assert response.body == b'jpeg'


def test_render_publishes_snapshot_timestamp_only_on_success(world, monkeypatch):
    import server.simulation as simulation
    robot = world.robots['tea']
    class Renderer:
        def __init__(self, model, **kwargs):
            assert model is not robot.model
        def update_scene(self, data, camera):
            assert data is not robot.data
        def render(self):
            return np.zeros((4, 4, 3), dtype=np.uint8)
        def close(self):
            pass
    monkeypatch.setattr(simulation.mujoco, 'Renderer', Renderer)
    monkeypatch.setattr(simulation.time, 'time', lambda: 100)
    assert robot.frame_timestamp == 0
    robot.render()
    assert robot.renderer_error is None
    assert robot.frame_timestamp == 100000
    assert len(robot.frames) == 3
    assert set(robot.frame_timestamps.values()) == {100000}
    monkeypatch.setattr(simulation.time, 'time', lambda: 101)
    world.tick_robot(robot, now=100)
    assert robot.frame_timestamp == 100000
    def fail():
        raise RuntimeError('camera stopped')
    monkeypatch.setattr(robot.renderer, 'render', fail)
    robot.render()
    assert robot.frame_timestamp == 100000
    assert robot.renderer_error == 'RuntimeError: camera stopped'


def test_physics_failure_is_isolated_to_one_robot(world, monkeypatch):
    def fail(_):
        raise RuntimeError('local failure')
    monkeypatch.setattr(world.robots['tea'], 'step', fail)
    for robot in world.robots.values():
        monkeypatch.setattr(robot, 'render', lambda: None)
    world.start()
    deadline = time.monotonic() + 1
    while world.robots['tea'].error is None and time.monotonic() < deadline:
        time.sleep(.005)
    time.sleep(.03)
    assert world.robots['tea'].lease.hold_reason == 'simulation_error'
    assert all(world.robots[rid].data.time > 0 for rid in ('pepper', 'jipai'))
    assert command(world, 'alice', 'jipai', 'claim', now=time.time()) is None
    assert command(world, 'alice', 'jipai', 'activate', now=time.time()) is None


def test_idle_lease_expiry_events_and_measured_metrics(world):
    activate(world, 'alice', 'tea')
    robot = world.robots['tea']
    world.tick_robot(robot, now=100)
    world.tick_robot(robot, now=100.1)
    assert world.state()['metrics']['alice']['intervention_seconds'] == pytest.approx(.1)
    world.tick_robot(robot, now=100.8)
    assert robot.lease.hold_reason == 'input_timeout'
    world.tick_robot(robot, now=101)
    assert world.state()['metrics']['alice']['wait_seconds'] == pytest.approx(.2)
    world.tick_robot(robot, now=115.01)
    assert robot.lease.owner is None
    events = world.state()['events']
    assert any(event['type'] == 'claim' and event['worker_id'] == 'alice' for event in events)
    assert any(event['reason'] == 'input_timeout' for event in events)
    assert events[-1]['reason'] == 'lease_expired'
    assert command(world, 'bob', 'tea', 'claim', now=115.02) is None
    for _ in range(205):
        command(world, 'alice', 'tea', 'claim', now=115.03)
    assert len(world.state()['events']) == 200
    assert world.state()['events'][-1]['reason'] == 'robot_busy'


def test_hand_gestures_trigger_assistance_once_without_overwriting_path(world):
    activate(world, 'hands', 'jipai')
    robot = world.robots['jipai']
    def gesture(closed, x=0):
        hand = dict(tracked=True, pinch=closed, x=x, y=0)
        return command(world, 'hands', 'jipai', 'control', hands=dict(left=hand, right=hand))
    assert gesture(False) is None
    assert robot.action is None and robot.direct_hands
    assert gesture(True) is None
    assert robot.action == 'pick' and not robot.direct_hands
    target = robot.target.copy()
    assert gesture(True, 1) is None
    np.testing.assert_array_equal(robot.target, target)
    # Holding the gesture across an assisted segment cannot chain stages.
    robot.stage, robot.action = 'season', None
    assert gesture(True) is None
    assert robot.action is None
    assert gesture(False) is None
    assert gesture(True) is None
    assert robot.action == 'season'
    robot.stage, robot.action = 'bag', None
    assert gesture(False) is None
    assert robot.action == 'bag'


def test_rehearsal_restart_requires_owner_and_does_not_reward(world):
    activate(world, 'performer', 'pepper')
    robot = world.robots['pepper']
    assert command(world, 'other', 'pepper', 'rehearse') == 'lease_required'
    robot.data.qpos[:3] = [30, 30, .03]
    assert command(world, 'performer', 'pepper', 'rehearse') is None
    assert robot.stage == 'pick' and not robot.lease.active
    assert np.linalg.norm(robot.food[:2]) < 1
    assert not world.ledger
    assert command(world, 'performer', 'pepper', 'activate') is None
    complete(world, 'performer', 'pepper')
    assert robot.delivered
