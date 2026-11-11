# Night Shift — a Taiwanese night-market shift from home

Product and system master · v0.5 · 2026-11-11

This is the single design master. The original proposal was a design, not an implementation claim. Current implementation boundaries are recorded below.

## Story and product

At 10 p.m., a home operator accepts a short request from a Taipei chicken stall. The operator sees through a robot camera, helps pick, season, package, and serve a chicken cutlet, then moves to a pepper-bun stall. The platform allocates work between people and autonomous robots; one operator manually controls only one robot at a time. Separate operators can control different robots simultaneously.

The intended future service connects physical stores. This prototype uses MuJoCo and test credits only.

## Three stalls

- Chicken: pick a finished cutlet, season per order, put it in a fixed bag fixture, and deliver to pickup. Rigid food and color/state changes replace frying, powder physics, and paper deformation.
- Pepper buns: attach rigid dough to an oven target, wait for a simulated baking interval, retrieve, and deliver. Attachment constraints and a timer do not reproduce dough adhesion or heat transfer.
- Bubble tea: place a sealed rigid cup upright in a tray. No fluid simulation.

All three stalls are implemented as simplified task sequences. Completion of all three should not come at the expense of usable chicken teleoperation.

## Views and interface

The primary work view is a fixed robot-height first-person camera. Operator, wrist, and overhead views supplement it. A fullscreen button enlarges the main view without deleting the supporting views. The webcam remains a small local preview. Work areas should be legible, with the same market scene naturally visible around them. Matching target colors clarify depth and occlusion; simulator ground-truth overlays must not be represented as camera perception.

A store switch shows the new workspace and task before activation, discards previous hand input, and releases the previous lease. Sound effects are staged demo effects.

## Hand control and safety intent

Browser webcam → landmarks → intent → lease and safety checks → controller. Raw webcam video is not stored by default. Hand tracking runs locally; optional external VLM sampling requires explicit consent.

The requested spatial convention treats the webcam as the customer: horizontal correspondence is reversed, a growing palm moves the robot forward toward the customer, and image height controls vertical movement. Depth is a relative monocular cue, not accurate measured 3D position or force. Smoothing, hysteresis, speed and workspace limits are required. Hand loss, disconnection, or stale video stops manual motion while retaining held objects.

Shared autonomy supplies bounded task segments. VLM output may suggest semantic intent; it does not decide safety, ownership, or joint commands. Hardware safety requires separate validation.

## System

React/TypeScript consoles connect over WebSocket to FastAPI, which owns independent MuJoCo workstations through robot controllers. Physics and rendering are separated. The server tracks workers, requests, exclusive leases, task stages, validation, events, and test-credit records. Commands have sequence numbers and timestamps. One robot has one owner; one operator manually owns one robot. Held or disconnected robots require explicit activation before control resumes.

The design handoff is AUTO → SAFE_HOLD → REMOTE → VERIFYING → AUTO. Future qualification and matching logic must be validated with operators; availability in this prototype is not a production qualification system.

## Current demonstration

The recording is **two minutes**, superseding the original 90-second proposal. See DEMO.md for the shot list.

The current recording mode uses explicit scripted actions. The operator performs hand movements for the camera, but those movements do not drive scripted mode. Start scripted demo resets the current simulated order and advances the task through checked states. Connection/video freshness checks remain. The screen identifies scripted operation.

Official G1 body visuals are used, with a chef hat and procedural market. Grasping is a simplified weld. The stock fixed hand mesh does not provide articulated finger contact, and grasp appearance remains incomplete. Live two-hand teleoperation has not been validated as a reliable full user workflow. Automated three-stall completion/repeat tests and a no-webcam browser chicken run have passed; these are distinct from webcam validation. RoboCasa was investigated, not integrated.

## Business hypothesis and boundaries

Potential customers are robot-service providers and multi-site food-service operators. Validate intervention time, concurrent requests, support cost, and willingness to pay. A future reward policy may combine time and verified work without encouraging unsafe speed competition.

Real payments, worker qualifications, labor rules, liability, customer privacy, physical robots, and general-purpose model training are outside this demo. The initial proposal referenced YC’s physical-world operating-systems RFS and hackathon rules; those external eligibility requirements are not reverified here.

## Revision history

v0.1 system integration → v0.2 prize-rescue removed → v0.3 ring-toss removed and pepper buns proposed → v0.4 chicken-shift story, webcam interaction, and robot/auxiliary views unified → v0.5 English master, all three simplified stalls, G1 visuals, and explicit two-minute scripted demonstration boundaries.
