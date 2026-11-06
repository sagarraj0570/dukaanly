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

    def get_total_connections(self) -> int:
        """Return the total number of connected WebSockets across all deliveries."""
        return sum(len(conns) for conns in self.active_connections.values())

    def get_active_delivery_ids(self) -> list[str]:
        """Return list of delivery IDs that currently have active connections."""
        return list(self.active_connections.keys())

    async def close_all(self, code: int = 1001, reason: str = "Server shutting down") -> int:
        """
        Gracefully close all active WebSockets across all deliveries during shutdown.
        Uses WebSocket close code 1001 (Going Away).
        """
        closed_count = 0
        all_deliveries = list(self.active_connections.keys())
        for d_id in all_deliveries:
            conns = list(self.active_connections.get(d_id, set()))
            for ws in conns:
                try:
                    await ws.close(code=code, reason=reason)
                    closed_count += 1
                except Exception as err:
                    logger.debug("Error closing websocket during shutdown: %s", err)
            if d_id in self.active_connections:
                del self.active_connections[d_id]
        logger.info("Gracefully closed %d active WebSockets during shutdown", closed_count)
        return closed_count

manager = ConnectionManager()
