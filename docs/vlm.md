# Optional semantic VLM intent

The VLM interprets deliberate operator intent from sampled camera images; it does not
copy human joints, own leases, or execute robot commands. `server.vlm.router` exposes
`GET /api/vlm/status` and `POST /api/vlm/intent`. The application must include this router.
`VLMPanel` uses the existing camera through `getFrame`; it never opens another camera.

## Configuration

The default is disabled. For Anthropic, set these server-side environment variables:

```sh
export VLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY='your-api-key'
export VLM_MODEL=claude-haiku-5-5
```

Use a securely supplied API key; do not put it in frontend environment variables, Git,
logs, or browser storage. No CLI login/OAuth credential is read. The native adapter
posts base64 image blocks to `https://api.anthropic.com/v1/messages`, with the
`x-api-key` and `anthropic-version: 2023-06-01` headers. `VLM_MODEL` defaults to
`claude-haiku-5-5` only for Anthropic. Verified against the official
[vision guide](https://platform.claude.com/docs/en/build-with-claude/vision) and
[model IDs](https://platform.claude.com/docs/en/models/overview) on 2026-11-11.

For an OpenAI-compatible vision provider (including a locally configured Ollama or
vLLM server), use:

```sh
export VLM_PROVIDER=openai-compatible
export VLM_BASE_URL=http://localhost:11434/v1
export VLM_MODEL='your-installed-vision-model'
# VLM_API_KEY is optional for a local provider; set it when your provider requires it.
```

The adapter appends `/chat/completions` to the base URL. The server operator controls
that URL; request bodies cannot change it. Use HTTPS for external providers. Status
returns only `configured`, provider type, and model, never credentials or the base URL.
Configured means environment settings are present, not that inference has succeeded.
**Live provider inference is unverified**: automated tests mock both provider APIs.
No synthetic VLM output is substituted for an unavailable provider.

## Consent and privacy

No inference upload occurs by default. Enable the existing camera, explicitly consent
to sharing sampled images in the VLM panel, then infer once or opt into continuous
sampling. External processing may incur charges and is subject to provider retention
policies. This app does not log request bodies or persist camera frames. Keep reverse
proxy/APM body capture disabled for these endpoints too. Revoking consent aborts the
browser request and prevents further uploads; it cannot recall a frame already sent.
Disabling the panel clears consent. Switching robot or stage stops continuous mode
and ignores late responses. Background tabs do not initiate inference.

## Contract and limits

POST JSON fields: `frames` (1–3 JPEG data URLs, each decoded image at most 256 KiB),
`robot_id`, `stage` (each 1–64 alphanumeric/underscore/hyphen characters), and literal
boolean `consent: true`. JPEG verification and a 4096×4096 pixel-count ceiling apply.
The total request body is bounded before parsing. Error responses never echo images.

The result is `{robot_id, stage, suggestion, reason}`. The suggestion fields are:

| Field | Values |
| --- | --- |
| action | hold, move, approach, retract, grasp, release, twist, season, pack, serve |
| target | food, seasoning, bag, tray, pickup, none |
| arm | left, right |
| direction | left, right, up, down, forward, back, none |
| confidence | finite number from 0 to 1 |

Extra keys, malformed JSON, invalid enums, nonfinite confidence, and confidence below
0.75 produce a conservative `hold`, with `reason` `invalid_output` or `low_confidence`.
Accepted output has reason `accepted`. Prompts treat frames as untrusted data, never
instructions. Model confidence is self-reported, not a calibrated safety guarantee.

The provider has a 15-second overall deadline and HTTP timeout. Requests are limited
to one in flight and one start per second per server process, with no waiting queue.
Use one API process or a shared ingress rate limiter when deploying multiple workers.
Provider responses are capped at 64 KiB. Errors are actionable codes: 403 consent,
413 body limit, 422 invalid input, 429 busy/rate cap, 503 unconfigured, 504 timeout,
502 provider failure. Errors stop panel continuous mode and do not fabricate intent.

## Parent integration and validation

Import the default `VLMPanel` and exported `VLMIntentResult` type. Supply props
`{getFrame, onIntent, robotId, stage, enabled}`. `getFrame` should return a small JPEG
data URL from the existing camera (or null). The panel sends one frame per request;
the API also permits up to three chronological frames for other clients.

`onIntent` is a suggestion callback only. Parent controls must enforce robot identity,
stage, lease ownership, freshness, deterministic action/target compatibility, movement
bounds, and independent timeout/hold behavior. Never convert an arbitrary suggestion
into a claim or bypass safety controls. A network timeout produces no callback, so
robot safety must not depend on receiving a successful VLM response. Repeated gestures
must not retrigger irreversible stage actions without parent edge/state checks.

Run `python -m pytest tests/test_vlm.py -q`. Tests cover both wire formats, consent,
frame limits, output validation, configuration, rate/concurrency caps, timeouts,
redacted errors, and absence of world interactions. The panel is TypeScript checked;
live browser camera consent/cancellation and live provider quality still need a
configured environment and manual end-to-end verification.
