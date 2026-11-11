# Entrance illustration source

Final asset: `public/assets/entrance-chef.png` (1254 × 1254 RGBA PNG).
Open `preview.html` locally to preview the unchanged asset on dark, cream, and
checkerboard backgrounds. No frontend integration is included in this change.

The G1 identity reference, `g1-chef-reference.png`, is an actual MuJoCo render
of the committed official Unitree mesh from `server/assets/g1/g1.xml` and its STL
files. Their attribution and BSD license remain in `server/assets/g1/`.
The white chef hat matches the geometry in `server/humanoid.py`.

Reproduce the reference from the repository root with a Python environment
containing the project's requirements:

```sh
python scripts/render_entrance_reference.py
```

The final composition was created with the built-in imagegen editor, using the
rendered reference, then a second edge-cleanup edit. Image generation is not
deterministic; the script reproduces the official reference, not the final art.
The customer and raised V-sign hands are illustrative edits, not a claim that
the simulator or the physical robot supports this gesture.

## Initial editing prompt

Use case: compositing / identity-preserve / background-extraction. Edit the supplied actual official Unitree G1 robot render into a polished entrance hero cutout for the Night Shift Taiwan night-market game. Keep the exact recognizable G1 identity from the reference: narrow dark recessed face and black neck, white/silver tapered chest with existing UNITREE wordmark, round shoulder joints, exposed mechanical waist and round black hip joints, long silver articulated legs, small black feet, and white chef hat. Do not turn it into a generic cartoon robot, give it eyes, or replace its mechanical body. Repose one arm so its robot hand makes an unmistakable two-finger V/peace sign beside its head. Beside the robot add one cute young adult Taiwanese night-market customer, in tasteful charming high-quality 3D animated-film style: short dark bob hair, warm smile, casual teal shirt, light shorts and sneakers, a small crossbody bag. Customer also makes a clear V/peace sign with one hand, other hand holds a bubble tea. They lean companionably toward one another, looking toward the viewer, like a cheerful souvenir photo. Customer is slightly shorter than the robot including its chef hat. Full bodies fully visible with a small clear margin, close compact balanced two-person composition, premium soft studio illumination and warm friendly mood. Preserve robot proportions and mesh silhouette faithfully, with smooth detailed material rendering. Actual transparent PNG alpha background, fully isolated subjects, no black background, no white background, no checkerboard drawn into image, no surrounding scene, no floor, no ground shadow outside the subjects, no border, no text except the existing robot chest wordmark. Output approximately square, suitable as a website foreground cutout.

## Cleanup prompt

Precise cutout cleanup of this exact image. Keep the robot and woman, poses, clothing, faces, materials, branding, body shapes and composition unchanged. Fix ONLY the transparent background edges: remove ALL white fuzzy speckles, colored red/yellow fringe, detached pixels and white halo surrounding the chef hat, robot limbs, between the robot legs, and around the customer. Clean smooth antialiased silhouette with natural hair edge suitable for placing on a dark navy webpage. Ensure all areas outside the two subjects and all negative-space holes between limbs are actual alpha=0 transparency, with no baked black/white/checkerboard background. Add approximately 6% transparent breathing room around the full subjects on all sides, particularly above the chef hat and below shoes so no subject or edge touches canvas. Keep both full bodies and both V/peace poses. No shadow or ground. Output a clean production transparent PNG cutout.
