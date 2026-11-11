import { useEffect, useRef, useState } from 'react';

export interface VLMSuggestion {
  action: 'hold' | 'move' | 'approach' | 'retract' | 'grasp' | 'release' | 'twist' | 'season' | 'pack' | 'serve';
  target: 'food' | 'seasoning' | 'bag' | 'tray' | 'pickup' | 'none';
  arm: 'left' | 'right';
  direction: 'left' | 'right' | 'up' | 'down' | 'forward' | 'back' | 'none';
  confidence: number;
}
export interface VLMIntentResult {
  robot_id: string;
  stage: string;
  suggestion: VLMSuggestion;
  reason: 'accepted' | 'invalid_output' | 'low_confidence';
}
export interface VLMPanelProps {
  getFrame: () => string | null;
  onIntent: (result: VLMIntentResult) => void;
  robotId: string;
  stage: string;
  enabled: boolean;
}
interface ProviderStatus { configured: boolean; provider: string | null; model: string | null }

function validResult(value: VLMIntentResult): boolean {
  const s = value?.suggestion;
  return !!s && ['accepted', 'invalid_output', 'low_confidence'].includes(value.reason)
    && ['hold', 'move', 'approach', 'retract', 'grasp', 'release', 'twist', 'season', 'pack', 'serve'].includes(s.action)
    && ['food', 'seasoning', 'bag', 'tray', 'pickup', 'none'].includes(s.target)
    && ['left', 'right'].includes(s.arm)
    && ['left', 'right', 'up', 'down', 'forward', 'back', 'none'].includes(s.direction)
    && typeof s.confidence === 'number' && Number.isFinite(s.confidence) && s.confidence >= 0 && s.confidence <= 1
    && (s.action === 'hold' || (value.reason === 'accepted' && s.confidence >= .75));
}

/** Suggestions only. Parent must retain lease, stage, freshness and deterministic safety checks. */
export default function VLMPanel({ getFrame, onIntent, robotId, stage, enabled }: VLMPanelProps) {
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [consent, setConsent] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Checking VLM configuration…');
  const [retry, setRetry] = useState(0);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const lastStart = useRef(-Infinity);
  const latest = useRef({ getFrame, onIntent, robotId, stage, enabled, consent });
  latest.current = { getFrame, onIntent, robotId, stage, enabled, consent };

  useEffect(() => {
    const controller = new AbortController();
    setProvider(null);
    void fetch('/api/vlm/status', { signal: controller.signal, cache: 'no-store' })
      .then(async response => { if (!response.ok) throw new Error(); return response.json() as Promise<ProviderStatus>; })
      .then(value => { if (!controller.signal.aborted) { setProvider(value); setMessage(value.configured ? 'Ready for explicit frame-sharing consent.' : 'VLM is not configured on the server.'); } })
      .catch(() => { if (!controller.signal.aborted) setMessage('VLM status unavailable. Retry configuration check.'); });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    generation.current += 1;
    request.current?.abort(); request.current = null; setBusy(false);
    setContinuous(false);
    if (!enabled) setConsent(false);
    return () => { generation.current += 1; request.current?.abort(); request.current = null; };
  }, [robotId, stage, enabled, consent]);

  async function infer() {
    const context = latest.current;
    if (!context.enabled || !context.consent || !provider?.configured || document.hidden
      || request.current || performance.now() - lastStart.current < 1000) return;
    const frame = context.getFrame();
    if (!frame) { setMessage('No camera frame available. Enable the existing camera first.'); return; }
    const controller = new AbortController();
    const epoch = generation.current;
    request.current = controller;
    lastStart.current = performance.now();
    setBusy(true); setMessage('Interpreting intent…');
    const timeout = setTimeout(() => controller.abort(), 16000);
    const stillCurrent = () => epoch === generation.current && latest.current.enabled && latest.current.consent
      && context.robotId === latest.current.robotId && context.stage === latest.current.stage;
    try {
      const response = await fetch('/api/vlm/intent', {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frames: [frame], robot_id: context.robotId, stage: context.stage, consent: true }),
      });
      if (!response.ok) {
        const errors: Record<number, string> = { 403: 'Frame-sharing consent required.', 413: 'Camera frame is too large.',
          422: 'Camera frame or context is invalid.', 429: 'VLM busy; wait before retrying.', 502: 'VLM provider unavailable.',
          503: 'VLM is not configured.', 504: 'VLM provider timed out.' };
        throw new Error(errors[response.status] || 'VLM request failed.');
      }
      const result = await response.json() as VLMIntentResult;
      if (!stillCurrent() || controller.signal.aborted) return;
      if (!validResult(result) || result.robot_id !== context.robotId || result.stage !== context.stage) throw new Error('Invalid VLM suggestion; ignored.');
      setMessage(`${result.suggestion.action} · ${Math.round(result.suggestion.confidence * 100)}% confidence · ${result.reason.replaceAll('_', ' ')}`);
      latest.current.onIntent(result);
    } catch (error) {
      if (stillCurrent()) { setContinuous(false); setMessage(controller.signal.aborted ? 'Inference cancelled or timed out.' : error instanceof Error ? error.message : 'VLM unavailable.'); }
    } finally {
      clearTimeout(timeout);
      if (request.current === controller) { request.current = null; setBusy(false); }
    }
  }
  const inferRef = useRef(infer);
  inferRef.current = infer;
  useEffect(() => {
    if (!continuous || !enabled || !consent || !provider?.configured) return;
    const timer = setInterval(() => { void inferRef.current(); }, 1000);
    return () => clearInterval(timer);
  }, [continuous, enabled, consent, provider]);

  return <section aria-label="VLM semantic intent" style={{ padding: 14, border: '1px solid #344252', borderRadius: 12, color: '#dce7ed' }}>
    <strong>Semantic intent · VLM</strong>
    <p style={{ fontSize: 12 }}>{provider?.configured ? `${provider.provider} · ${provider.model}` : 'VLM offline / unconfigured'}</p>
    <label style={{ display: 'block', fontSize: 12 }}><input type="checkbox" checked={consent} disabled={!enabled || !provider?.configured}
      onChange={event => setConsent(event.target.checked)} /> I consent to sending sampled camera images to the configured VLM provider, which may be external. Provider processing and charges may apply.</label>
    <p style={{ fontSize: 11 }}>Frames are not saved by this app. Provider retention policies apply. Suggestions pass through robot safety controls.</p>
    <button type="button" disabled={!enabled || !consent || !provider?.configured || busy} onClick={() => { void infer(); }}>{busy ? 'Interpreting…' : 'Infer intent once'}</button>{' '}
    <button type="button" onClick={() => setRetry(value => value + 1)}>Check configuration</button>
    <label style={{ display: 'block', marginTop: 10, fontSize: 12 }}><input type="checkbox" checked={continuous}
      disabled={!enabled || !consent || !provider?.configured} onChange={event => setContinuous(event.target.checked)} /> Sample continuously (at most once per second)</label>
    <p role="status" style={{ fontSize: 12 }}>{message}</p>
  </section>;
}
