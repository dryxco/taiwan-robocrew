# Browser hand tracking

`HandTracker` is the default export from `src/components/HandTracker.tsx`.

```tsx
<HandTracker enabled={cameraOptIn} onIntent={handleIntent} />
```

Only set `enabled` after the user explicitly chooses to enable the camera. The parent controls this boolean and should forward intents only while its interaction is active. Turning it off releases every media track; unmount, startup failure, and camera disconnect also release resources. Late permission responses after teardown have their tracks stopped immediately.

The callback receives `{ x, y, pinch, shake, confidence, tracked }`. Coordinates are normalized to `[0, 1]`, follow the mirrored index fingertip, and use temporal smoothing. Pinch uses thumb/index distance divided by palm size with separate press/release thresholds. Shake requires two substantial horizontal palm reversals within 650 ms; `shake: true` is a one-frame pulse with a one-second cooldown. Loss of a hand clears gestures immediately. A camera frame stale for more than 250 ms clears tracking through a 100 ms watchdog; hidden tabs clear tracking as soon as visibility changes. Parent consumers should always require `tracked` before acting on a gesture.

The displayed confidence is the SDK's handedness classification score. It is **not** gesture confidence or an exposed detection score. MediaPipe detection, presence, and tracking thresholds are configured separately at 0.6. One hand is supported; keep only the controlling hand in view.

## Runtime requirements

- Pin `@mediapipe/tasks-vision` to `0.10.32`; the WASM URL in the component must match that dependency.
- Use HTTPS or localhost and grant browser/OS camera permission. Embedded hosts must allow camera access through their Permissions Policy and iframe permissions.
- On activation, the browser downloads WASM assets from `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm` and the official model from `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`. Network access to both origins is required unless assets are already browser-cached. Restricted CSP deployments must allow these resource loads and WebAssembly execution.
- SDK inference runs locally with the CPU delegate, capped at 25 frames per second. It is synchronous on the UI thread; device performance varies, and results taking longer than 250 ms are discarded. No webcam frame is uploaded, recorded, or persisted by this component.
- [Official MediaPipe web guide](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/web_js).

## Validation

Run `node --experimental-strip-types --test tests/handIntent.test.mjs` with Node 22.23+ to check mirroring, hand-scale normalization, pinch hysteresis, stale release, invalid input rejection, smoothing, and shake pulse/cooldown behavior. Strict TypeScript checking passed against the parent React 19 / TypeScript installation. Real camera permission flows, hardware performance, and browser rendering still require a manual integrated smoke test.
