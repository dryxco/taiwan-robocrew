import time
from fastapi.testclient import TestClient
from server.app import app


def ack(ws):
    for _ in range(30):
        msg = ws.receive_json()
        if msg['type'] == 'ack':
            return msg
    raise AssertionError('No acknowledgement')


def test_websocket_state_claim_disconnect_and_camera():
    with TestClient(app) as client:
        data = client.get('/api/state').json()
        assert {r['id'] for r in data['robots']} == {'jipai', 'pepper', 'tea'}
        with client.websocket_connect('/ws/operator') as ws:
            ws.send_json(dict(type='claim', robot_id='jipai', seq=1, sent_at=time.time()*1000))
            assert ack(ws)['ok']
            ws.send_json(dict(type='activate', robot_id='jipai', seq=2, sent_at=time.time()*1000))
            assert ack(ws)['ok']
            ws.send_text('{')
            assert ack(ws)['error'] == 'invalid_message'
            assert not client.get('/api/state').json()['robots'][0]['active']
        assert app.state.world.robots['jipai'].lease.owner is None
        deadline = time.time()+10
        response = client.get('/api/robots/jipai/frame')
        while response.status_code == 503 and time.time() < deadline:
            time.sleep(.1)
            response = client.get('/api/robots/jipai/frame')
        assert response.status_code == 200, response.text
        assert response.content[:2] == b'\xff\xd8'
        assert client.get('/api/robots/jipai/frame?view=invalid').status_code == 404
