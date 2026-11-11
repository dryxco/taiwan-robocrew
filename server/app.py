"""Run: python -m uvicorn server.app:app --host 127.0.0.1 --port 8000"""
import asyncio
from contextlib import asynccontextmanager
import json
import re

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from server.simulation import World


@asynccontextmanager
async def lifespan(app):
    app.state.world = World()
    app.state.connections = set()
    app.state.world.start()
    yield
    app.state.world.close()


app = FastAPI(title='Night Shift simulation', lifespan=lifespan)


@app.get('/api/state')
def state():
    return app.state.world.state()


@app.get('/api/robots/{robot_id}/frame')
def frame(robot_id: str, view: str = 'first_person'):
    world = app.state.world
    robot = world.robots.get(robot_id)
    if not robot or view not in ('first_person', 'top', 'wrist'):
        raise HTTPException(404, 'Unknown robot or camera')
    with robot.frame_lock:
        content = robot.frames.get(view)
        if content is None:
            raise HTTPException(503, robot.renderer_error or 'Camera warming up')
        return Response(content, media_type='image/jpeg', headers={'Cache-Control': 'no-store', 'X-Frame-Timestamp': str(robot.frame_timestamps[view])})


@app.websocket('/ws/{worker_id}')
async def websocket(ws: WebSocket, worker_id: str):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', worker_id):
        await ws.close(code=1008, reason='Invalid worker ID')
        return
    if worker_id in app.state.connections:
        await ws.close(code=1008, reason='Worker already connected')
        return
    app.state.connections.add(worker_id)
    await ws.accept()
    world = app.state.world
    send_lock = asyncio.Lock()

    async def send(payload):
        async with send_lock:
            await ws.send_json(payload)

    async def broadcast():
        while True:
            await send({'type': 'state', 'state': await asyncio.to_thread(world.state)})
            await asyncio.sleep(.1)

    task = asyncio.create_task(broadcast())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                cmd = json.loads(raw)
                if not isinstance(cmd, dict) or len(raw) > 4096:
                    raise ValueError('Invalid command')
                error = await asyncio.to_thread(world.command, worker_id, cmd)
                await send({'type': 'ack', 'seq': cmd.get('seq'), 'ok': error is None, 'error': error})
            except (ValueError, TypeError):
                await asyncio.to_thread(world.disconnect, worker_id, release=False, reason='invalid_message')
                await send({'type': 'ack', 'ok': False, 'error': 'invalid_message'})
    except WebSocketDisconnect:
        pass
    finally:
        await asyncio.to_thread(world.disconnect, worker_id)
        app.state.connections.discard(worker_id)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
