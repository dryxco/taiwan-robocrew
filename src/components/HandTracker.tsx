import { useEffect, useRef, useState } from 'react';
import type { HandLandmarker } from '@mediapipe/tasks-vision';
import { HandIntentProcessor, type HandIntent, type HandPoint } from '../lib/handIntent';

export type { HandIntent } from '../lib/handIntent';
export interface HandTrackerProps { enabled: boolean; onIntent: (intent: HandIntent) => void }

// Keep this version identical to the package dependency. These are asset downloads only;
// camera frames are processed locally and are never uploaded, recorded, or persisted.
const WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm';
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';
const EDGES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];

function cameraError(error: unknown, phase: string): string {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'Camera access was blocked. Allow camera access in your browser site settings, then retry. Embedded pages also need camera permission from their host.';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return 'No camera was found. Connect a webcam, then retry.';
  if (name === 'NotReadableError' || name === 'TrackStartError') return 'The camera is busy or unavailable. Close other camera apps, check OS camera permission, then retry.';
  if (name === 'OverconstrainedError') return 'This camera cannot use the requested settings. Try a different camera, then retry.';
  if (phase === 'model') return 'The hand model could not load. Check your connection and allow cdn.jsdelivr.net and storage.googleapis.com, then retry.';
  return 'Camera tracking stopped. Check camera permissions and try a current Chrome, Edge, Firefox, or Safari browser, then retry.';
}

function draw(canvas: HTMLCanvasElement, points: readonly HandPoint[] | undefined) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!points) return;
  const x = (p: HandPoint) => (1 - p.x) * canvas.width;
  const y = (p: HandPoint) => p.y * canvas.height;
  ctx.strokeStyle = '#bfff71';
  ctx.lineWidth = 2;
  for (const [a, b] of EDGES) {
    ctx.beginPath(); ctx.moveTo(x(points[a]), y(points[a])); ctx.lineTo(x(points[b]), y(points[b])); ctx.stroke();
  }
  for (const point of points) {
    ctx.beginPath(); ctx.arc(x(point), y(point), 3, 0, Math.PI * 2); ctx.fillStyle = '#e9ffd3'; ctx.fill();
  }
}

/** enabled must only be set after explicit user camera opt-in. HTTPS or localhost is required. */
export default function HandTracker({ enabled, onIntent }: HandTrackerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const callbackRef = useRef(onIntent);
  const [retry, setRetry] = useState(0);
  const [status, setStatus] = useState('Camera off');
  const [error, setError] = useState('');
  const [confidence, setConfidence] = useState(0);
  const [tracked, setTracked] = useState(false);
  useEffect(() => { callbackRef.current = onIntent; }, [onIntent]);

  useEffect(() => {
    const processor = new HandIntentProcessor();
    const video = videoRef.current;
    const canvas = canvasRef.current;
    let disposed = false;
    let failed = false;
    let stream: MediaStream | undefined;
    let detector: HandLandmarker | undefined;
    let frame = 0;
    let watchdog: ReturnType<typeof setInterval> | undefined;
    let phase = 'camera';
    let lastVideoTime = -1;
    let lastInference = -Infinity;
    let lastUi = -Infinity;
    let wasTracked = false;
    const emit = (intent: HandIntent) => {
      callbackRef.current(intent);
      const now = performance.now();
      if (intent.tracked !== wasTracked || now - lastUi > 120 || !intent.tracked) {
        setTracked(intent.tracked); setConfidence(intent.confidence);
        wasTracked = intent.tracked; lastUi = now;
      }
    };
    const clearHand = () => { emit(processor.lost()); if (canvas) draw(canvas, undefined); };
    const stop = () => {
      cancelAnimationFrame(frame);
      if (watchdog) clearInterval(watchdog);
      stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
      if (video) video.srcObject = null;
      detector?.close(); detector = undefined;
    };
    const fail = (message: string) => {
      if (disposed || failed) return;
      failed = true; stop(); clearHand(); setError(message); setStatus('Camera unavailable');
    };
    clearHand(); setError('');
    if (!enabled) { setStatus('Camera off'); return () => { disposed = true; stop(); }; }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('Camera access requires HTTPS or localhost and a browser with webcam support. Open this app at a secure address.');
      setStatus('Camera unavailable');
      return () => { disposed = true; stop(); };
    }
    const onVisibility = () => { if (document.hidden) clearHand(); };
    document.addEventListener('visibilitychange', onVisibility);
    const tick = () => {
      if (disposed || failed || !video || !canvas || !detector) return;
      const now = performance.now();
      if (!document.hidden && video.readyState >= 2 && video.currentTime !== lastVideoTime && now - lastInference >= 40) {
        lastVideoTime = video.currentTime; lastInference = now;
        try {
          const result = detector.detectForVideo(video, now);
          if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
            canvas.width = video.videoWidth; canvas.height = video.videoHeight;
          }
          const points = result.landmarks[0];
          const intent = points ? processor.update(points, result.handedness[0]?.[0]?.score ?? 0, now, video.videoWidth / video.videoHeight) : processor.lost();
          // Inference itself is synchronous; discard excessively old results too.
          if (performance.now() - now > 250) { clearHand(); }
          else { draw(canvas, intent.tracked ? points : undefined); emit(intent); }
        } catch (reason) { fail(cameraError(reason, 'tracking')); return; }
      }
      frame = requestAnimationFrame(tick);
    };
    void (async () => {
      try {
        setStatus('Waiting for camera permission…');
        const acquired = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } } });
        if (disposed || failed) { acquired.getTracks().forEach(track => track.stop()); return; }
        stream = acquired;
        for (const track of acquired.getVideoTracks()) track.onended = () => fail('Camera access ended. Reconnect your camera or restore browser permission, then retry.');
        if (!video) throw new Error('Video element unavailable');
        video.srcObject = acquired;
        await video.play();
        if (disposed || failed) return;
        phase = 'model'; setStatus('Loading hand model…');
        const { FilesetResolver, HandLandmarker: Landmarker } = await import('@mediapipe/tasks-vision');
        if (disposed || failed) return;
        const files = await FilesetResolver.forVisionTasks(WASM_URL);
        if (disposed || failed) return;
        const created = await Landmarker.createFromOptions(files, {
          baseOptions: { modelAssetPath: MODEL_URL, delegate: 'CPU' },
          runningMode: 'VIDEO', numHands: 1,
          minHandDetectionConfidence: 0.6, minHandPresenceConfidence: 0.6, minTrackingConfidence: 0.6,
        });
        if (disposed || failed) { created.close(); return; }
        detector = created; setStatus('Show one hand to the camera');
        watchdog = setInterval(() => {
          const stale = processor.stale(performance.now());
          if (stale) { emit(stale); if (canvas) draw(canvas, undefined); }
        }, 100);
        tick();
      } catch (reason) { fail(cameraError(reason, phase)); }
    })();
    return () => {
      disposed = true;
      document.removeEventListener('visibilitychange', onVisibility);
      stop();
      callbackRef.current(processor.lost());
      if (canvas) draw(canvas, undefined);
    };
  }, [enabled, retry]);

  return (
    <section aria-label="Hand tracking camera" style={{ color: '#dce7ed', fontFamily: 'inherit', width: '100%' }}>
      <div style={{ position: 'relative', aspectRatio: '4 / 3', overflow: 'hidden', borderRadius: 14, background: '#0a1118', border: '1px solid #28313b' }}>
        <video ref={videoRef} muted playsInline autoPlay aria-label="Mirrored local webcam preview" style={{ width: '100%', height: '100%', objectFit: 'fill', transform: 'scaleX(-1)', display: enabled ? 'block' : 'none' }} />
        <canvas ref={canvasRef} aria-hidden="true" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
        {!tracked && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', padding: 24, textAlign: 'center', background: enabled ? 'rgba(5,10,16,.28)' : 'transparent' }}><span>{status}</span></div>}
        <span title="MediaPipe handedness classification confidence, not gesture accuracy" style={{ position: 'absolute', bottom: 10, left: 12, padding: '5px 8px', borderRadius: 6, background: '#0a1118cc', fontSize: 11, letterSpacing: '.04em' }}>{tracked ? `HAND DETECTED · ${Math.round(confidence * 100)}% CONFIDENCE` : 'NO HAND SIGNAL'}</span>
      </div>
      <p role="status" style={{ fontSize: 12, margin: '8px 0', color: '#a0adb9' }}>{error || (tracked ? 'Move to steer · pinch thumb + index · shake side to side' : status)}</p>
      {error && enabled && <button type="button" onClick={() => setRetry(value => value + 1)} style={{ border: '1px solid #617544', borderRadius: 8, background: '#1b291a', color: '#d9f7b8', padding: '8px 12px', cursor: 'pointer' }}>Retry camera</button>}
      <p style={{ fontSize: 11, color: '#82909d', margin: '6px 0 0' }}>Camera stays on this device. No video is saved or uploaded.</p>
    </section>
  );
}
