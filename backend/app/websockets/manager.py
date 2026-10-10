import asyncio
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps delivery_id -> set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, delivery_id: str):
        await websocket.accept()
        if delivery_id not in self.active_connections:
            self.active_connections[delivery_id] = set()
        self.active_connections[delivery_id].add(websocket)

    def disconnect(self, websocket: WebSocket, delivery_id: str):
        if delivery_id in self.active_connections:
            if websocket in self.active_connections[delivery_id]:
                self.active_connections[delivery_id].remove(websocket)
            if not self.active_connections[delivery_id]:
                del self.active_connections[delivery_id]

    async def broadcast(self, delivery_id: str, message: dict):
        if delivery_id in self.active_connections:
            connections = list(self.active_connections[delivery_id])
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send message to client on delivery {delivery_id}: {e}")
                    self.disconnect(connection, delivery_id)

manager = ConnectionManager()
