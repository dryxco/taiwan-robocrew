# Living market scenery

`buildMarketEnvironment(scene)` retains the existing stall IDs (`jipai`,
`pepper-bun`, `bubble-tea`), approach/counter positions, `update(seconds)` and
idempotent `dispose()`. The street now has 20 looping pedestrians, three queued
customers per stall, four seated diners and three working vendors. Clothing,
skin, hair and takeaway bags use instance colors. The entire 36-person crowd
uses eight instanced meshes, two shared geometries and one cached material;
static counter clutter continues through the existing geometry batching.

Call the optional `setOrders` before the next `update` to synchronize queues:

```ts
market.setOrders?.(state.orders.map(order => ({
  robot_id: order.robot_id,
  stage: order.stage,
  delivered: order.status === 'completed',
  order_id: order.id,
})));
```

Both server IDs (`pepper`, `tea`) and scene IDs are accepted. A newly delivered
order advances its queue once and gives the departing customer a paper bag.
Repeated snapshots of that order do not restart the departure. Customers at the
back recycle after four seconds to sustain the crowd. Stall approach centerlines
remain clear; pedestrians cross farther down the alley. Vendors gesture while
waiting and use larger packing/handoff motions during `bag`/`deliver` stages.
Queue length and TEST cash are illustrative, not inventory or payment state.

## MuJoCo integration

`server/market_life.py` is isolated from `simulation.py`. The coordinator should
call `decorate_market_life(xml)` **after** robot-specific XML substitutions and
before `MjModel.from_xml_string`. It appends seven mocap humans, two mocap props
and static receipt clutter. No joints, equalities, cameras or existing fixtures
are changed; original food qpos addresses and equality indices are preserved.
Decoration is idempotent. All new geoms have zero contact masks and zero mass.
Customers/props remain beyond y=1, facing the first-person camera across the
counter; four background pedestrians cross behind the three-person queue.

Call `update_market_life(model, data, elapsed, delivered, order_number)` under
the physics lock before `mj_forward` or `mj_step`, including while the operator
is held, if customers should keep moving during a hold. `elapsed` is absolute
seconds: `data.time` is supported, including resets when a new order begins.
The helper changes only its own mocap positions and stores small per-data state
in a weak map. Camera copies inherit the updated positions normally. It safely
returns when given an undecorated model. A delivered edge advances the queue
once per order; the bag follows that customer for four seconds. The floating
cash prop depicts **TEST simulation only** and never authorizes payments,
creates ledger entries or changes delivery verification.

## Validation performed

- Strict TypeScript check passed with the parent checkout's existing dependencies.
- Node scene smoke verified all original stall IDs, 36 instances in eight draws,
  moving queue members, repeated-delivery idempotence, finite matrices, and
  idempotent disposal including instance buffers.
- For all three compiled robot variants, decorated models retained nq/nv/neq,
  joint names/qpos addresses, equality body indices, and original fixture
  positions, sizes and collision masks. Updates left qpos/equality state intact.
- MuJoCo first-person images rendered successfully for chicken, pepper bun and
  tea; the chicken image was visually inspected with customers visible behind
  the counter. Temporary images are `/tmp/market-life-{jipai,pepper,tea}.png`.
- Existing `server/tests/test_simulation.py`: 6 passed.

The complete integrated browser view still needs coordinator validation after
wiring scene telemetry and the simulation helper. No new dependencies are used.
