# DUAL YAM simulation backend

This is a MuJoCo embodiment of two official I2RT YAM v1 six-axis arms, using unscaled meshes, link transforms, masses, inertias, joint limits and 10 N·m joint force limits. Both arms accept independent target positions and optional orientations. The left arm carries food through a weld on its physical TCP; absent an explicit right-arm target, the right arm moves a simulated seasoning shaker. This is not real-robot validation, collision-safe motion planning, or a hardware driver.

## Source and assets

- Official repository: https://github.com/i2rt-robotics/i2rt
- Pinned revision: `c8c29ce470410135ba71029f28cdcbac1c787f14`
- Model: `i2rt/robot_models/arm/yam/v1/yam.xml`
- Exactly the six referenced STL meshes are vendored with the unmodified model, root MIT license, and `SOURCE.json` in `server/assets/yam/`.
- `preview-first-person.png` and `preview-operator.png` are actual MuJoCo renders of the augmented task scene after 200 physics steps; they are not AI illustrations. The procedural palms, sliding jaws, shaker and mounts are local prototype geometry, not official gripper CAD. Two additional bounded slide joints per hand actuate the jaw geometry.

## Runtime integration

```python
from server.dual_yam import augment_scene, DualYamController

# Apply task-specific XML modifications (including oven weld) BEFORE augmentation.
model = mujoco.MjModel.from_xml_string(augment_scene(xml))
data = mujoco.MjData(model)
controller = DualYamController(model, data)

# Existing mocap gripper is a hidden command target, never the physical gripper.
controller.step(data.mocap_pos[gripper_id], stage, dt, bool(data.eq_active[0]), twist=0.0)
mujoco.mj_step(model, data)
state = controller.snapshot()
```

`augment_scene(xml: str) -> str` appends the robot chains after the existing food body, preserving food freejoint qpos 0 and velocity 0. Official body, joint and mesh names are prefixed `left_` and `right_`. Existing equality order is preserved: `grasp` stays index 0 and an existing oven weld stays index 1. An additional `right_grasp` weld is appended after existing equalities (resolve it by name). The grasp's `body1` is changed to `left_tcp`, with its existing `0 0 -.07` tool-to-food offset retained. The wrist camera moves to that physical TCP. The `first_person` camera is the employee viewpoint behind the counter looking down at the work table. The `operator` camera is a customer-side observer view of both arms; `wrist` and `top` remain available.

`DualYamController(model, data)` initializes only robot joint positions and controls. Do this once when creating/resetting a scene, never as a substitute for moving the arm during a task. `reset(target_position=None)` is also an initialization operation: it writes only the robot joints, not food state.

`step(target_position, stage, dt, grasped=False, *, twist=0.0, right_target_position=None, left_orientation=None, right_orientation=None) -> dict` computes DLS IK in scratch data, then writes servo controls. It does **not** call `mj_step`, write live qpos/qvel, change food pose, activate/deactivate welds, or move the command mocap. `grasped` is retained for integration compatibility; the caller owns the weld. Twist is a bounded semantic joint-6 command in radians, clamped to ±0.6, not a direct human-landmark mapping. An explicit `right_target_position` controls the right arm independently and overrides guided assistance. Without orientation arguments, the vertical tool axis is constrained while yaw is otherwise free. Optional `left_orientation` / `right_orientation` values are finite, nonzero wxyz quaternions, normalized before full-pose IK. Joint limits still restrict which poses are feasible; an infeasible position or orientation leaves that arm’s servo goal unchanged. Full orientation overrides the left twist convenience command.

Calling `step(None, 'hold', dt, grasped)` or `step(target, 'hold', dt, grasped)` freezes actuator commands and retains the live weld. Existing physical motion can settle under the servos; hold does not forcibly zero physical velocity. `hold()` alone latches the flag, but subsequent ordinary `step` calls resume: the runtime must continue sending the hold stage while its lease is inactive. Do not activate/deactivate the food weld simply because control is held or resumed.

`set_grasp(side, closed) -> bool` directly controls either hand (`side` is `left` or `right`). Closing moves that hand’s physical finger slides; it attaches food only when the achieved tool-to-food grasp point is within 35 mm and no other food weld is active. Opening releases only that hand. It returns whether that hand currently holds food and never moves food qpos. An explicit handover is left open followed by right close when both achieved TCPs are at the grasp pose; it never silently steals a grasp. Existing guided code may still change equality activation itself: the controller synchronizes finger closure on attach/release transitions. Finger commands slew at 0.15 m/s, use 2 N force limits and 0–45 mm travel.

Use `snapshot()` **after physics** for current achieved state:

- `tcp`: achieved left TCP xyz, in meters.
- `target`: requested left TCP xyz.
- `ik_error`: Euclidean achieved position error, in meters.
- `reachable`: left scratch IK residual is under 15 mm position and 0.12 rad orientation; it is not a collision or trajectory certificate.
- `valid`: all live qpos values finite and achieved TCP within 35 mm of target.
- `held`, `active_arm`, `embodiment`.
- `arms.left` and `arms.right`: six `joint_positions`, six `joint_velocities`, achieved `tcp`, achieved `ik_error`, scratch `solver_error` and `orientation_error`, `gripper_closed`, actual `grasped`, per-arm `reachable`, and `rejection_reason` (`unreachable_pose` or null).

Arrival and grasp tests must use the achieved TCP, not the command mocap. For instance compare `food` with `np.asarray(state['tcp']) - [0, 0, .07]` before enabling the grasp. Keep the food upright check based on its actual rotation. Stop or reject an unreachable user command rather than treating the rectangular joystick bounds as a reachability guarantee. A scratch failure is observable through per-arm `reachable` and `rejection_reason`; the controller holds the last accepted servo command for only that arm. It never chases a changing partial solution to an unreachable target.

## Reach, control and limitations

The main base is at `(0, 0.24, 1.04)` meters and the assisting base at `(0.30, 0.34, 1.18)`, on explicitly rendered raised mounts. No robot model scale was changed. The runtime must apply the agreed **0.55 planar task scale** to all task positions, planar food/fixture dimensions, target coordinates, workspace and planar completion thresholds. Heights stay unchanged. `augment_scene` does not perform this task-layout scaling: supply already-scaled scene XML and actual world-coordinate targets. The initial left target is `(-.231, -.0825, 1.08)`; guided right target is `(0, .132, 1.25)`. Both bases are behind the compact task fixtures from the customer viewpoint. The unscaled arm cannot cover every corner of the old x `[-.65,.65]`, y `[-.48,.48]`, z `[.75,1.12]` command box. Numerical tests instead verify the actual default source, lift, seasoning, bag, delivery, oven and retrieval poses. Joint command slew is limited to 1.5 rad/s, with each update capped to 50 ms of slew. Physical joint velocity is available in telemetry; this command limit is not a certified hard physical velocity stop.

The implementation adds position servos (kp 250, kv 22), damping 2, armature 0.03, implicit-fast integration and simulated gravity compensation. All twelve arm joints remain dynamic and force-limited; IK never teleports them during stepping. The source model has no actuator block, so these are simulator tuning choices, not official controller settings.

The following approximation boundaries are intentional and must remain visible in product claims:

- Robot mesh, procedural jaw and mount contacts are excluded. Food/counter/tray/bag contacts remain physical. This prototype cannot detect arm-fixture or arm-arm collision and is not collision-safe.
- The gripper is a simplified palm with physically actuated finger slides and an explicit grasp weld, not a contact-driven friction grasp mechanism. Food follows the actual actuated chain through the constraint; finger friction/grasp-force validation is not performed.
- Gravity compensation is simulated per-link; this is not validation of motor thermal, payload, current or hardware safety limits.
- Both arms support independent control; the right shaker is the default guided assisting role; explicit proximity-gated food handover is supported, but there is no deformable bag or seasoning-particle simulation.

## Verification

Run with the parent environment:

```sh
/Users/airdry/orca/projects/NightShift/server/.venv/bin/python -m pytest server/tests/test_dual_yam.py -q
```

The tests cover original scene index preservation, official limits and meshes, live actuator-only motion, reachable default task waypoints, actual food constraint carrying and hold behavior, explicit unreachable/invalid states, independent right-arm motion, bounded twist, optional orientation, rejection without command jitter, and direct grasp/release/handover without food teleportation. In MuJoCo 3.3.7, all nine tests pass; unloaded default endpoint tracking is below 12 mm, with measured representative errors under 12 mm in the compact layout. These are simulated tests only. The runtime worker must also run full task workflows after adding the integration hooks.
