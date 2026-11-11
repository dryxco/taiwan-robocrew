// Run: node --experimental-strip-types --test tests/handIntent.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { HandIntentProcessor } from '../src/lib/handIntent.ts';

function hand({ scale = 1, gap = 0.1, shift = 0 } = {}) {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5 }));
  points[0] = { x: 0.5, y: 0.8 };
  points[9] = { x: 0.5, y: 0.5 };
  points[5] = { x: 0.4, y: 0.5 };
  points[17] = { x: 0.6, y: 0.5 };
  points[8] = { x: 0.4, y: 0.2 };
  points[4] = { x: 0.4 + gap * 0.3, y: 0.2 };
  return points.map(p => ({ x: 0.5 + (p.x - 0.5) * scale + shift, y: 0.5 + (p.y - 0.5) * scale }));
}

test('mirrors the palm and clamps screen coordinates', () => {
  const processor = new HandIntentProcessor();
  const intent = processor.update(hand(), 0.93, 0, 1);
  assert.equal(intent.x, 0.5); assert.equal(intent.y, 0.575);
  assert.equal(intent.tracked, true); assert.equal(intent.confidence, 0.93);
  assert.equal(new HandIntentProcessor().update(hand({ shift: 2 }), 1, 0).x, 0);
});

test('pinch is scale-independent and has different close/open thresholds', () => {
  for (const scale of [0.4, 1, 1.5]) {
    const processor = new HandIntentProcessor();
    assert.equal(processor.update(hand({ scale, gap: 0.2 }), 1, 0, 1).pinch, false);
    assert.equal(processor.update(hand({ scale, gap: 0.2 }), 1, 100, 1).pinch, true);
    assert.equal(processor.update(hand({ scale, gap: 0.4 }), 1, 140, 1).pinch, true);
    assert.equal(processor.update(hand({ scale, gap: 0.7 }), 1, 180, 1).pinch, true);
    assert.equal(processor.update(hand({ scale, gap: 0.7 }), 1, 280, 1).pinch, false);
    assert.equal(processor.update(hand({ scale, gap: 0.4 }), 1, 320, 1).pinch, false);
  }
});

test('tracking loss and stale frames release pinch and reset smoothing', () => {
  const processor = new HandIntentProcessor();
  processor.update(hand(), 1, 0);
  assert.equal(processor.stale(250), null);
  assert.deepEqual(processor.stale(251), { x: 0.5, y: 0.575, pinch: false, shake: false, confidence: 0, tracked: false });
  assert.ok(Math.abs(processor.update(hand({ shift: 0.3 }), 1, 300).x - 0.2) < 1e-12);
  assert.equal(processor.update([], 1, 340).tracked, false);
});

test('low confidence, malformed and degenerate hands cannot activate gestures', () => {
  const processor = new HandIntentProcessor();
  assert.equal(processor.update(hand(), 0.3, 0).tracked, false);
  assert.equal(processor.update(hand(), NaN, 1).tracked, false);
  const bad = hand(); bad[0].x = NaN;
  assert.equal(processor.update(bad, 1, 2).tracked, false);
  assert.equal(processor.update(Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5 })), 1, 3).tracked, false);
});

test('smoothing reduces jitter and old timestamps cannot move the cursor', () => {
  const processor = new HandIntentProcessor();
  processor.update(hand(), 1, 100);
  const next = processor.update(hand({ shift: 0.2 }), 1, 140);
  assert.ok(next.x > 0.47 && next.x < 0.5);
  assert.equal(processor.update(hand({ shift: -0.2 }), 1, 120).x, next.x);
});

test('shake requires direction reversals, emits a pulse, and respects cooldown', () => {
  const processor = new HandIntentProcessor();
  const shifts = [0, 0.22, -0.22, 0.22];
  const samples = shifts.map((shift, i) => processor.update(hand({ shift }), 1, i * 100, 1));
  assert.deepEqual(samples.map(s => s.shake), [false, false, false, true]);
  assert.equal(processor.update(hand({ shift: -0.22 }), 1, 400, 1).shake, false);
  assert.equal(processor.update(hand({ shift: 0.22 }), 1, 500, 1).shake, false);
  processor.lost();
  assert.equal(processor.update(hand(), 1, 600, 1).shake, false);
});


test('finger closing cannot steer the palm and small jitter is ignored', () => {
  const p = new HandIntentProcessor();
  const initial = p.update(hand({ gap: 0.8 }), 1, 0);
  for (let t = 40; t <= 200; t += 40) {
    const sample = p.update(hand({ gap: 0.1, shift: .003 }), 1, t);
    assert.equal(sample.x, initial.x);
    assert.equal(sample.y, initial.y);
  }
  assert.equal(p.update(hand(), 1, 240).pinch, true);
});
