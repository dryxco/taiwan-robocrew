# Robot camera market background

`server.camera_market.decorate_camera_market(xml, robot_id)` appends visual-only
Taipei shophouses, striped neighboring stalls, warm windows, AC units, balconies,
roof tanks, lantern strings and pavement. The palette follows
`src/scene/marketEnvironment.ts`: chicken red, pepper amber, tea teal and cream
awnings. This is procedural matching architecture, not a pixel-identical copy of
the browser scene; it does not add crowds or Chinese sign textures.

Composition order:

```python
xml = augment_scene(robot_specific_xml)
xml = decorate_scene(xml, robot_id)
xml = decorate_camera_market(xml, robot_id)
model = mujoco.MjModel.from_xml_string(xml)
```

Use robot IDs `jipai`, `pepper`, `tea`. No `simulation.py` integration is included
in this module change. Callers can omit the old `market_backdrop.xml` include for
new compositions: the module tolerates and preserves `market_decor_root` but its
distant stalls duplicate parts of this background. Existing workstation dressing
is retained. Repeated calls are idempotent.

World axes are MuJoCo Z-up: the G1 stands at Y=+0.25 facing -Y. Rear building
fronts start at Y=1.7; opposite fronts are at -4.8, with shops at -4; neighboring
stalls sit at X=+/-2. The active central stall has only elevated awning/sign and
outer posts, not another counter. Lowest street lantern tassels are above 2.8m.
All appended geometry uses `camera_market_` names, zero mass, and zero contact
masks. Task elements, equality IDs, actuators, cameras, lighting and physics are
preserved. A teal gradient sky is added only if none exists, and one ambient fill
light supplements the task lights.

Validation used the parent Python environment and actual `Robot` source XML,
including robot-specific food, oven, weld and old backdrop; then humanoid and
workstation composition. Four tests verify all three scenes compile, original XML
survives unchanged, collision masks are zero, and 20 physics steps match the
undecorated composition to 1e-12. Standalone rendering produced 960x640 first-person,
operator and overview PNGs for all three robots in `/tmp/nightshift-camera-market`.
These local artifacts are outside Git.

Existing camera framing is intentionally preserved: the downward first-person
camera sees pavement and opposite shop counters, but crops upper windows and
lanterns; the narrow operator view also crops upper architecture. Camera owners
can widen/raise framing to show that architecture while keeping task visibility.

The pepper operator render confirms the existing oven decoration surrounds the
G1 torso. Source coordinates place the oven at `(0, .27, .87)` and its mouth at
`(0, .27, 1.041)`, beside the employee at Y=.25. This module does not move owned
workstation or physical task elements. Suggested owner change: translate oven
physics, decorative bricks/rim/mouth, oven anchor and interaction targets together
toward negative Y (counter front), then check working reach and collisions. Moving
only the decorative mesh would leave physical contact and task targets mismatched.
