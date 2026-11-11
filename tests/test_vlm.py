"""Provider-mocked tests: never require a key, webcam, renderer, or robot world."""
import asyncio
import base64
import io
import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from server import vlm


@pytest.fixture
def setup(monkeypatch):
    for name in ('VLM_BASE_URL', 'VLM_MODEL', 'VLM_API_KEY', 'VLM_PROVIDER', 'ANTHROPIC_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('VLM_BASE_URL', 'http://localhost:11434/v1')
    monkeypatch.setenv('VLM_MODEL', 'test-vision')
    monkeypatch.setattr(vlm, 'admission', vlm.Admission())
    app = FastAPI()
    app.include_router(vlm.router)
    app.state.world = Mock()
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, format='JPEG')
    payload = {'frames': ['data:image/jpeg;base64,' + base64.b64encode(image.getvalue()).decode()],
               'robot_id': 'tea', 'stage': 'pick', 'consent': True}
    with TestClient(app) as client:
        yield client, payload, app.state.world
    assert not app.state.world.mock_calls  # suggestions can never command or claim a robot


def mock_provider(monkeypatch, callback):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(callback)
    monkeypatch.setattr(vlm.httpx, 'AsyncClient', lambda **kw: original(transport=transport, **kw))


def suggestion(**changes):
    return dict(action='grasp', target='food', arm='left', direction='none', confidence=.9, **changes)


def test_unconfigured_and_status_do_not_leak_key(setup, monkeypatch):
    client, payload, _ = setup
    monkeypatch.setenv('VLM_API_KEY', 'secret-not-for-clients')
    assert 'secret' not in client.get('/api/vlm/status').text
    monkeypatch.delenv('VLM_BASE_URL')
    assert client.get('/api/vlm/status').json()['configured'] is False
    assert client.post('/api/vlm/intent', json=payload).status_code == 503


@pytest.mark.parametrize('consent', [False, None, 'true', 1])
def test_consent_required_before_any_provider_request(setup, monkeypatch, consent):
    client, payload, _ = setup
    mock_provider(monkeypatch, lambda _: pytest.fail('must not send frames'))
    payload['consent'] = consent
    response = client.post('/api/vlm/intent', json=payload)
    assert response.status_code in (403, 422)
    assert payload['frames'][0] not in response.text


@pytest.mark.parametrize('frames', [[], ['data:image/png;base64,aA=='], ['data:image/jpeg;base64,aA=='],
                                   ['data:image/jpeg;base64,###'], ['x'] * 4,
                                   ['data:image/jpeg;base64,' + 'a' * 350000]])
def test_invalid_frames_never_reach_provider(setup, monkeypatch, frames):
    client, payload, _ = setup
    mock_provider(monkeypatch, lambda _: pytest.fail('must not send frames'))
    payload['frames'] = frames
    response = client.post('/api/vlm/intent', json=payload)
    assert response.status_code == 422
    assert 'base64' not in response.text


def test_oversized_body(setup):
    client, _, _ = setup
    assert client.post('/api/vlm/intent', content=b'x' * (vlm.MAX_BODY_BYTES + 1)).status_code == 413


def test_openai_compatible_image_contract_and_rate_cap(setup, monkeypatch):
    client, payload, _ = setup
    def provider(request):
        body = json.loads(request.content)
        assert str(request.url) == 'http://localhost:11434/v1/chat/completions'
        assert 'authorization' not in request.headers
        assert body['messages'][1]['content'][1]['image_url']['url'] == payload['frames'][0]
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(suggestion())}}]})
    mock_provider(monkeypatch, provider)
    response = client.post('/api/vlm/intent', json=payload)
    assert response.status_code == 200
    assert response.json()['suggestion']['action'] == 'grasp'
    assert response.json()['robot_id'] == 'tea'
    assert client.post('/api/vlm/intent', json=payload).status_code == 429


def test_anthropic_native_contract(setup, monkeypatch):
    client, payload, _ = setup
    monkeypatch.setenv('VLM_PROVIDER', 'anthropic')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.delenv('VLM_MODEL')
    assert client.get('/api/vlm/status').json() == {'configured': True, 'provider': 'anthropic', 'model': 'claude-haiku-5-5'}
    def provider(request):
        body = json.loads(request.content)
        assert str(request.url) == 'https://api.anthropic.com/v1/messages'
        assert request.headers['x-api-key'] == 'test-key'
        assert request.headers['anthropic-version'] == '2023-06-01'
        assert body['system'] == vlm.PROMPT
        assert body['messages'][0]['content'][0]['source']['data'] == payload['frames'][0].split(',')[1]
        return httpx.Response(200, json={'content': [{'type': 'text', 'text': json.dumps(suggestion())}]})
    mock_provider(monkeypatch, provider)
    assert client.post('/api/vlm/intent', json=payload).json()['reason'] == 'accepted'


def test_anthropic_requires_api_key(setup, monkeypatch):
    client, payload, _ = setup
    monkeypatch.setenv('VLM_PROVIDER', 'anthropic')
    assert client.post('/api/vlm/intent', json=payload).status_code == 503


@pytest.mark.parametrize('content,reason', [
    ('not json', 'invalid_output'), ('[]', 'invalid_output'),
    (json.dumps({**suggestion(), 'action': 'execute_shell'}), 'invalid_output'),
    (json.dumps({**suggestion(), 'confidence': float('nan')}), 'invalid_output'),
    (json.dumps({**suggestion(), 'confidence': float('inf')}), 'invalid_output'),
    (json.dumps({**suggestion(), 'confidence': True}), 'invalid_output'),
    (json.dumps({**suggestion(), 'confidence': 1.1}), 'invalid_output'),
    (json.dumps({**suggestion(), 'confidence': .74}), 'low_confidence'),
    (json.dumps({**suggestion(), 'target': 'person'}), 'invalid_output'),
    (json.dumps({**suggestion(), 'arm': 'both'}), 'invalid_output'),
    (json.dumps({**suggestion(), 'direction': 'diagonal'}), 'invalid_output'),
    (json.dumps({**suggestion(), 'lease': 'claim'}), 'invalid_output'),
])
def test_untrusted_output_becomes_hold(setup, monkeypatch, content, reason):
    client, payload, _ = setup
    mock_provider(monkeypatch, lambda _: httpx.Response(200, json={'choices': [{'message': {'content': content}}]}))
    result = client.post('/api/vlm/intent', json=payload).json()
    assert result['reason'] == reason
    assert result['suggestion'] == {'action': 'hold', 'target': 'none', 'arm': 'right', 'direction': 'none', 'confidence': 0}


@pytest.mark.parametrize('failure,status', [('timeout', 504), ('http', 502), ('malformed', 502)])
def test_provider_failures_are_redacted_and_release_slot(setup, monkeypatch, failure, status):
    client, payload, _ = setup
    def provider(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('private provider data', request=request)
        return httpx.Response(500 if failure == 'http' else 200, text='private provider data')
    mock_provider(monkeypatch, provider)
    response = client.post('/api/vlm/intent', json=payload)
    assert response.status_code == status
    assert 'private' not in response.text and 'base64' not in response.text
    assert not vlm.admission.busy


def test_busy_admission_has_no_queue(setup, monkeypatch):
    client, payload, _ = setup
    vlm.admission.enter()
    monkeypatch.setattr(vlm.time, 'monotonic', lambda: vlm.admission.last + 2)
    mock_provider(monkeypatch, lambda _: pytest.fail('busy request must not reach provider'))
    assert client.post('/api/vlm/intent', json=payload).status_code == 429


def test_overall_timeout(setup, monkeypatch):
    client, payload, _ = setup
    async def slow(*args):
        await asyncio.sleep(1)
    monkeypatch.setattr(vlm, 'query_provider', slow)
    monkeypatch.setattr(vlm, 'PROVIDER_TIMEOUT', .01)
    assert client.post('/api/vlm/intent', json=payload).status_code == 504
    assert not vlm.admission.busy
