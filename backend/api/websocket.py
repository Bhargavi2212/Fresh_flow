"""WebSocket endpoint for real-time dashboard updates."""
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from backend.services.websocket_manager import get_ws_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept WebSocket connections; register with manager and keep connection open."""
    manager = get_ws_manager()
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(websocket)
