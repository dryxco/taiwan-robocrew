# Night Shift backend

Local FastAPI/WebSocket prototype with three independent real MuJoCo model/data worlds: `jipai`, `pepper`, and `tea`. Python 3.9+ works; tested on macOS arm64 with Python 3.9 and MuJoCo 3.3.7. No cloud services or API keys.

```sh
python3 -m venv server/.venv
server/.venv/bin/python -m pip install --upgrade pip
server/.venv/bin/pip install --only-binary=mujoco -r requirements.txt
server/.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
# From another shell:
server/.venv/bin/python -m pytest server/tests -q
```

Run one Uvicorn process: worlds, leases and test ledger are in memory. Restart resets everything. Bind to localhost; this P0 has no identity authentication and worker IDs are client-chosen. Do not expose as a production service. The frontend should proxy `/api` and `/ws` to port 8000.

## API

- `GET /api/state`: `{robots, orders, ledger, server_time, simulation, simulation_error, test_mode}`.
- `WS /ws/{worker_id}`: alphanumeric/underscore/hyphen ID, 1–64 characters. One live socket per worker ID. Sends `{type:"state", state:...}` at 10 Hz and `{type:"ack",seq,ok,error}` for commands. State messages can arrive before acknowledgement.
- `GET /api/robots/{robot_id}/frame?view=first_person|top|wrist`: 480×320 JPEG, refreshed about 4 Hz, `Cache-Control: no-store`. Returns 503 during startup or with an explicit renderer error; unknown robot/view returns 404.

All commands require `type`, `robot_id`, increasing integer `seq` scoped to worker ID, and `sent_at` in Unix milliseconds (`Date.now()`). Keep sequence increasing across reconnects within the same server process. Messages older than 1000 ms or more than 250 ms in the future are rejected and hold the worker's robot.

```json
{"type":"claim","robot_id":"jipai","seq":1,"sent_at":1794398400000}
{"type":"activate","robot_id":"jipai","seq":2,"sent_at":1794398400001}
{"type":"control","robot_id":"jipai","seq":3,"sent_at":1794398400002,"x":0,"y":0,"pinch":true,"shake":false,"action":"pick"}
```

Use a current timestamp, not the sample timestamp. Commands: `claim`, `activate`, `control`, `hold`, `release`. Claiming a different available robot releases and holds the previous one. Claiming an occupied robot fails without changing the previous lease. Claim never activates: explicit `activate` is mandatory. `control` requires an active owned lease. `x/y` are normalized horizontal velocity inputs in [-1,1]. A `pinch` requests the current non-season stage; `shake` requests seasoning. Alternatively send `action` equal to the current `stage` once. Continue sending fresh control messages (e.g. every 100 ms with zero x/y) during autonomy. Input silence over 750 ms cancels autonomy, holds the gripper at its current pose and requires reactivation. Disconnect holds and releases immediately. Rejected malformed messages also hold. Physics/gravity and already-attached oven cooking continue while held.

Robot state includes `id,name,status,owner,active,stage,action,hold_reason,position,food_position,grasped,seasoned,bagged,delivered,cooked,cook_time,attached,trayed,simulation_time,camera_error,cameras`. Status is `available`, `held` or `active`; cameras maps view names to image URLs. Order fields are `id,robot_id,item,status,stage,test_credit`. Ledger entries contain `id,order_id,robot_id,amount,currency,verified`; currency is always `TEST` and each order can credit once.

Errors include `invalid_sequence`, `stale_input`, `unknown_robot`, `robot_busy`, `lease_required`, `activation_required`, `wrong_stage`, `invalid_control`, `unknown_command`, `invalid_message`, `simulation_unavailable`. The UI should show `hold_reason` and require explicit activation to resume.

## Physical task models and boundaries

- Chicken: `pick → season → bag → deliver → complete`. Grasp requires physical proximity; a MuJoCo weld models the grip. Lift height verifies pickup, positioning over the spice station plus a one-second shake verifies seasoning, and a stable rigid food body within the fixed bag verifies bagging. Delivery moves the serving to a pickup zone and verifies settled location.
- Pepper bun: `pick → attach → cook → retrieve → deliver → complete`. A second weld attaches the rigid bun to the front wall of a cylindrical oven. Three simulated seconds of actual attachment at the oven pose verifies cooking. Retrieve disengages the oven weld, grips/lifts, then delivery verifies a stable serving at pickup.
- Tea: `pick → tray → deliver → complete`. The cup and lid are one rigid compound body. Tray placement verifies settled position and upright orientation; delivery rechecks these conditions.

These are simplified Cartesian mocap grippers, not articulated hardware arms. No deformable bag, liquids, pouring, real heat/food chemistry, or real money is simulated. The bag remains fixed; chicken delivery transfers the rigid serving from the bag fixture to pickup. One order per stall per process; no reset endpoint. The server never accepts a client completion/reward event. Credits come only from verified simulation state and are idempotent per order.

A dedicated thread owns simulation stepping and OpenGL rendering. All nine camera views were tested successfully on this machine, including rendering from the FastAPI worker thread. If another machine cannot create an OpenGL context, state continues and reports the exact rendering exception. `server/assets/market_backdrop.xml`, if present, is merged as a `worldbody` fragment (or a `<mujoco><worldbody>…` asset) when models load. Restart to load newly integrated assets.

Tests cover lease exclusivity, explicit activation after switching, sequence/age rejection, timeout/disconnect hold, invalid control, physical completion of all three workflows, idempotent credits, WebSocket acknowledgement/error behavior, and HTTP JPEG rendering.
