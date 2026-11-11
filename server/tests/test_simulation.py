import time
import pytest
from server.simulation import World


def command(w, worker, kind, robot='jipai', **extra):
    return w.command(worker, dict(type=kind, robot_id=robot, seq=w.seq.get(worker, -1) + 1, sent_at=time.time()*1000, **extra))


def test_exclusive_lease_and_explicit_activation():
    w = World()
    assert command(w, 'alice', 'claim') is None
    assert command(w, 'bob', 'claim') == 'robot_busy'
    assert command(w, 'alice', 'control') == 'activation_required'
    assert command(w, 'alice', 'activate') is None
    assert command(w, 'alice', 'claim', 'tea') is None
    assert w.robots['jipai'].lease.owner is None
    assert not w.robots['tea'].lease.active
    assert not w.robots['jipai'].lease.active
    assert command(w, 'alice', 'control', 'tea') == 'activation_required'


def test_stale_sequence_age_disconnect_timeout():
    w = World()
    command(w, 'a', 'claim')
    command(w, 'a', 'activate')
    assert w.command('a', dict(type='control', robot_id='jipai', seq=0, sent_at=time.time()*1000)) == 'invalid_sequence'
    assert not w.robots['jipai'].lease.active
    command(w, 'a', 'activate')
    assert w.command('a', dict(type='control', robot_id='jipai', seq=4, sent_at=0)) == 'stale_input'
    assert not w.robots['jipai'].lease.active
    command(w, 'a', 'activate')
    w.tick(time.time()+1)
    assert w.robots['jipai'].lease.hold_reason == 'input_timeout'
    w.disconnect('a')
    assert w.robots['jipai'].lease.owner is None


@pytest.mark.parametrize('rid', ['jipai', 'pepper', 'tea'])
def test_physical_workflow_and_idempotent_credit(rid):
    w = World()
    command(w, 'a', 'claim', rid)
    command(w, 'a', 'activate', rid)
    r = w.robots[rid]
    assert command(w, 'a', 'control', rid, action='deliver') == 'wrong_stage'
    for i in range(20000):
        if i % 20 == 0:
            assert command(w, 'a', 'control', rid, action=r.stage if not r.delivered else None) is None
        w.tick()
        if r.delivered:
            break
    assert r.delivered, (r.stage, r.phase, r.food, r.data.mocap_pos[r.gripper], r.dwell)
    assert len(w.ledger) == 1
    for _ in range(100):
        w.tick()
    assert len(w.ledger) == 1
    assert list(w.ledger.values())[0]['currency'] == 'TEST'
    assert all(not other.delivered for other in w.robots.values() if other.id != rid)


def test_invalid_control_holds_robot():
    w = World()
    command(w, 'a', 'claim')
    command(w, 'a', 'activate')
    assert command(w, 'a', 'control', x=float('nan')) == 'invalid_control'
    assert not w.robots['jipai'].lease.active
