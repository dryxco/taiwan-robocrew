"""Decorative market customers. Cash/receipts are TEST simulation, never payments.

Append after all robot-specific XML substitutions. Call update under the physics
lock before mj_forward/mj_step; it only writes this module's mocap transforms.
"""
from __future__ import annotations

import math
import weakref
import xml.etree.ElementTree as ET

# Weak ownership prevents leaking completed Robot/MjData instances. Each camera
# snapshot receives already-updated mocap transforms through the normal copy.
_states = weakref.WeakKeyDictionary()


def decorate_market_life(xml: str) -> str:
    """Append collision-free customers without inserting joints or equalities."""
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('market life requires a worldbody')
    if world.find("body[@name='market_life_customer_0']") is not None:
        return xml

    def geom(parent, kind, pos, size, color):
        ET.SubElement(parent, 'geom', type=kind, pos=pos, size=size,
                      rgba=color, contype='0', conaffinity='0', group='2', mass='0')

    colors = ['.25 .57 .53 1', '.76 .39 .27 1', '.8 .63 .3 1', '.39 .48 .66 1']
    for i in range(7):
        x, y = ((.1 + (i % 2) * .16, 1.2 + i * .68) if i < 3
                else (-2.4 + (i - 3) * 1.5, 3.5 + (i % 2) * .5))
        body = ET.SubElement(world, 'body', name=f'market_life_customer_{i}',
                             mocap='true', pos=f'{x} {y} 0')
        geom(body, 'box', '0 0 1.08', '.18 .12 .25', colors[i % 4])
        geom(body, 'sphere', '0 0 1.52', '.16', '.77 .54 .39 1')
        geom(body, 'box', '0 .015 1.65', '.15 .13 .045', '.12 .12 .15 1')
        for side in (-1, 1):
            geom(body, 'capsule', f'{side * .10} 0 .43', '.065 .35', '.17 .2 .25 1')
            geom(body, 'capsule', f'{side * .24} -.06 1.03', '.05 .20', '.77 .54 .39 1')
        # Tiny facial marks face the first-person camera (-Y).
        for side in (-1, 1):
            geom(body, 'sphere', f'{side * .055} -.145 1.55', '.018', '.1 .09 .08 1')
    # Animated cash and paper bag remain beyond y=1, clear of all task fixtures.
    for name, color, size in [('cash_TEST', '.46 .65 .45 1', '.09 .035 .003'),
                              ('order_bag', '.76 .59 .36 1', '.11 .07 .14')]:
        body = ET.SubElement(world, 'body', name=f'market_life_{name}',
                             mocap='true', pos='.34 1.05 1.0')
        geom(body, 'box', '0 0 0', size, color)
    # Side order ledge and receipt stacks are visual-only, outside work volume.
    geom(world, 'box', '1.08 1.2 .8', '.2 .17 .035', '.3 .38 .37 1')
    for i in range(4):
        geom(world, 'box', f'1.08 1.2 {.845 + i * .008}', '.07 .09 .003', '.9 .85 .68 1')
    return ET.tostring(root, encoding='unicode')


def update_market_life(model, data, elapsed, delivered, order_number):
    """Animate queue/TEST cash; one departure per delivered order, no task writes.

    elapsed is monotonic seconds (data.time works, including next-order resets).
    Safe to call on an undecorated model. Cash motion is illustrative only; this
    function neither verifies delivery nor issues credit or payment events.
    """
    try:
        model.body('market_life_customer_0')
    except KeyError:
        return
    state = _states.get(data)
    if state is None:
        state = {'order': order_number, 'done': False, 'rotation': 0,
                 'departure': -100., 'time': elapsed}
        _states[data] = state
    if order_number != state['order'] or elapsed < state['time']:
        state.update(order=order_number, done=False, departure=-100.)
    state['time'] = elapsed
    if delivered and not state['done']:
        state.update(done=True, rotation=(state['rotation'] + 1) % 3, departure=elapsed)
    progress = min(1., max(0., (elapsed - state['departure']) / 4.))
    departing_pos = None
    for i in range(7):
        mocap = model.body(f'market_life_customer_{i}').mocapid[0]
        if i < 3:
            slot = (i - state['rotation']) % 3
            departing = slot == 2 and progress < 1
            x = .1 + (progress * 2.4 if departing else (slot % 2) * .16)
            y = 1.2 + (progress * 1.3 if departing else (slot + 1 - progress) * .68)
            if departing:
                departing_pos = (x, y)
        else:
            x = ((elapsed * (.28 + i * .025) + i * 1.5) % 7) - 3.5
            y = 3.5 + (i % 2) * .5
        data.mocap_pos[mocap] = (x, y, .012 * math.sin(elapsed * 4 + i))
    cash = model.body('market_life_cash_TEST').mocapid[0]
    bag = model.body('market_life_order_bag').mocapid[0]
    data.mocap_pos[cash] = (.34, 1.04 + .07 * (1 + math.sin(elapsed * 1.8)), 1.06)
    data.mocap_pos[bag] = ((departing_pos[0] + .25, departing_pos[1] - .1, .87)
                            if departing_pos else (1.08, 1.2, 1.02))
