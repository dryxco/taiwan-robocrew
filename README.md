# Taiwan RoboCrew

A Taiwanese night-market robot-work demo: chicken cutlets, pepper buns, and bubble tea. React and Three.js render a shared market; FastAPI and MuJoCo run independent simulated G1 workstations.

## Run locally

Use Node.js 22 and Python 3.9 or newer.

```sh
npm ci
python3 -m venv server/.venv
server/.venv/bin/pip install -r requirements.txt
server/.venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
npm run dev -- --host 0.0.0.0
```

For optional webcam tracking, first run `python3 scripts/download_hand_model.py` to download the upstream MediaPipe model. The scripted demo does not need it.

Open `http://localhost:5173`. Other devices on the same network can use the host's LAN address on port 5173. Webcam access on other devices requires HTTPS; localhost is allowed by browsers. This prototype has no production identity/authentication layer; use a trusted demo network.

## Scripted demonstration

Open a stall and press **Start scripted demo**. This resets that simulated order and runs its steps automatically. Webcam images can be displayed for performance; hand tracking is **not required** for the scripted routine. Keep the scripted-demo label visible. **Stop scripted demo** holds motion. Connection and video freshness checks remain active.

See [the two-minute recording script](docs/DEMO.md) for English narration and Korean stage directions.

## What is implemented

- Three independent MuJoCo workstations and official G1 visual assets.
- First-person, operator, wrist, and overhead views of the shared market.
- Exclusive robot control leases, explicit activation, stale-input holds, verified completion, and idempotent test credits.
- Scripted task routines; browser hand tracking and an experimental two-hand mapping path.
- Optional external VLM connection; see [VLM configuration](docs/vlm.md). No API key is needed for the scripted demo.

## Limits

This is a simulation prototype, not a deployed robot service. Grasping uses simplified weld constraints; the fixed G1 hand mesh does not reproduce articulated finger contact. Hand-control reliability and grasp visuals still need work. Baking is timed state, bags are rigid fixtures, and there are no fluids, cash payments, real robot safety claims, or general-purpose model training. The environment is procedural; RoboCasa assets were investigated but are not included.

## Validation

```sh
npm run build
node --experimental-strip-types --test tests/handIntent.test.mjs tests/handAssignment.test.mjs tests/teleopMapping.test.mjs
server/.venv/bin/python -m pytest tests/test_runtime.py -q -k 'verified_orders or rehearsal'
```

Three-stall completion/repeat tests and a no-webcam browser chicken-order run passed during development. These are not validation of live user webcam control. The full runtime suite also has known renderer-test failures; do not treat the focused command above as a clean full-suite claim.

## Assets and design

[Asset provenance](docs/assets.md), [G1 notices](server/assets/g1/LICENSE), [design master](docs/NIGHT_SHIFT.md). The entrance scene is rendered from the simulation robot and procedural customer using `scripts/render_entrance_scene.py`; an older unused generated entrance image remains in the project history.
