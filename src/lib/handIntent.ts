export interface HandIntent {
  x: number;
  y: number;
  pinch: boolean;
  shake: boolean;
  /** Handedness classification confidence; MediaPipe does not expose per-frame detection confidence. */
  confidence: number;
  tracked: boolean;
}

export interface HandPoint { x: number; y: number; z?: number }

export const STALE_HAND_MS = 250;
const clamp = (value: number) => Math.max(0, Math.min(1, value));

/** Stateful, browser-independent gesture processing. Create one instance per camera session. */
export class HandIntentProcessor {
  private value: HandIntent = { x: 0.5, y: 0.5, pinch: false, shake: false, confidence: 0, tracked: false };
  private lastTime = -Infinity;
  private turnX = 0;
  private direction = 0;
  private reversals: number[] = [];
  private lastShake = -Infinity;
  private pendingPinch = false;
  private pinchSince = -Infinity;

  lost(): HandIntent {
    this.value = { ...this.value, pinch: false, shake: false, confidence: 0, tracked: false };
    this.direction = 0;
    this.reversals = [];
    this.lastTime = -Infinity;
    this.pendingPinch = false;
    this.pinchSince = -Infinity;
    return { ...this.value };
  }

  stale(now: number): HandIntent | null {
    return this.value.tracked && now - this.lastTime > STALE_HAND_MS ? this.lost() : null;
  }

  update(points: readonly HandPoint[], confidence: number, now: number, aspect = 4 / 3): HandIntent {
    if (points.length !== 21 || points.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y)) ||
        !Number.isFinite(confidence) || confidence < 0.5 || !Number.isFinite(now) ||
        !Number.isFinite(aspect) || aspect <= 0) return this.lost();
    if (now <= this.lastTime) return { ...this.value, shake: false };
    if (now - this.lastTime > STALE_HAND_MS) this.lost();
    const distance = (a: HandPoint, b: HandPoint) => Math.hypot((a.x - b.x) * aspect, a.y - b.y);
    const size = Math.max(distance(points[0], points[9]), distance(points[5], points[17]));
    if (size < 0.025) return this.lost();
    const ratio = distance(points[4], points[8]) / size;
    // Require a sustained gesture; one noisy frame must never release a held object.
    const candidate = this.value.pinch ? ratio < 0.58 : ratio < 0.34;
    if (candidate !== this.pendingPinch) { this.pendingPinch = candidate; this.pinchSince = now; }
    let pinch = this.value.pinch;
    if (candidate !== pinch && now - this.pinchSince >= 100) pinch = candidate;
    // Palm center stays still when fingers close; fingertip steering caused grasp-time jumps.
    const rawX = clamp(1 - (points[0].x + points[5].x + points[9].x + points[17].x) / 4);
    const rawY = clamp((points[0].y + points[5].y + points[9].y + points[17].y) / 4);
    const wasTracked = this.value.tracked;
    const dt = wasTracked ? Math.min(100, now - this.lastTime) : 40;
    const alpha = 1 - Math.exp(-dt / 130);
    const smooth = (previous: number, raw: number) => {
      if (!wasTracked) return raw;
      const delta = raw - previous;
      if (Math.abs(delta) < .009) return previous;
      return previous + Math.max(-.6 * dt / 1000, Math.min(.6 * dt / 1000, alpha * delta));
    };
    const x = smooth(this.value.x, rawX);
    const y = smooth(this.value.y, rawY);
    // Shake uses palm movement, not fingertip motion during a pinch.
    const palmX = 1 - (points[0].x + points[5].x + points[9].x + points[17].x) / 4;
    if (!wasTracked) this.turnX = palmX;
    const delta = palmX - this.turnX;
    const threshold = Math.max(0.035, size / aspect * 0.5);
    this.reversals = this.reversals.filter(time => now - time < 650);
    if (Math.abs(delta) >= threshold) {
      const nextDirection = Math.sign(delta);
      if (this.direction && nextDirection !== this.direction) this.reversals.push(now);
      this.direction = nextDirection;
      this.turnX = palmX;
    } else if (this.direction && Math.sign(delta) === this.direction) {
      this.turnX = palmX;
    }
    const shake = this.reversals.length >= 2 && now - this.lastShake > 1000;
    if (shake) { this.lastShake = now; this.reversals = []; }
    this.lastTime = now;
    this.value = { x: clamp(x), y: clamp(y), pinch, shake, confidence: clamp(confidence), tracked: true };
    return { ...this.value };
  }
}
