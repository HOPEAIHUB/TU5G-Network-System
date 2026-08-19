"""
Real-time WebSocket Chat routers for TU5G platform.
Manages active socket channels, handles message broadcasts, and archives communication threads.
"""

import json
from datetime import datetime
from typing import Any, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Try to import database configurations and CRUD archiving methods; provide graceful stubs
try:
    from app.database import SessionLocal
except ImportError:
    SessionLocal = None

try:
    from app.crud import message as crud_message
except ImportError:
    class MockMessageCRUD:
        @staticmethod
        def save_message(db_session: Any, sender_id: str, content: str) -> bool:
            # Stub logic representing DB persistence
            return True
    crud_message = MockMessageCRUD()

router = APIRouter(prefix="/chat", tags=["Real-time Chat Engine"])


# ==========================================
# Connection Manager
# ==========================================

class ChatConnectionManager:
    """Manages active WebSocket connections for administrative/user chats."""
    def __init__(self):
        # Maps user_id to their active websocket connection
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Accept connection and register user session."""
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str) -> None:
        """Unregister user session upon socket closure."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_private_message(self, user_id: str, message: str) -> None:
        """Direct message to a single connected peer."""
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_text(message)

    async def broadcast(self, message: str) -> None:
        """Broadcast an event payload to all active chat sessions."""
        for user_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.send_text(message)
            except Exception:
                # Handle orphaned connections during broadcast iteration
                self.disconnect(user_id)


manager = ChatConnectionManager()


# ==========================================
# Endpoints
# ==========================================

@router.websocket("/ws/{user_id}")
async def chat_websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    """
    WebSocket channel for real-time messaging, events, and server broadcasts.
    Establishes connection, maintains message delivery loops, and archives logs.
    """
    await manager.connect(user_id, websocket)
    
    # Broadcast join event to chat room
    join_event = {
        "system": True,
        "sender": "System",
        "message": f"User {user_id} joined the secure channel.",
        "timestamp": datetime.utcnow().isoformat()
    }
    await manager.broadcast(json.dumps(join_event))

    try:
        while True:
            # Wait and receive text from client
            raw_data = await websocket.receive_text()
            
            try:
                # If client sent JSON structure, unpack it, otherwise treat as simple string
                parsed_data = json.loads(raw_data)
                message_text = parsed_data.get("message", raw_data)
            except json.JSONDecodeError:
                message_text = raw_data

            # Archive the message inside DB if DB session exists, otherwise skip gracefully
            if SessionLocal:
                db_session = SessionLocal()
                try:
                    crud_message.save_message(db_session, sender_id=user_id, content=message_text)
                    db_session.commit()
                except Exception:
                    db_session.rollback()
                finally:
                    db_session.close()
            else:
                # Use stub fallback if DB is offline/unavailable
                crud_message.save_message(None, sender_id=user_id, content=message_text)

            # Construct standardized message envelope
            broadcast_payload = {
                "system": False,
                "sender": user_id,
                "message": message_text,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Distribute message to all connected users
            await manager.broadcast(json.dumps(broadcast_payload))

    except WebSocketDisconnect:
        # Gracefully cleanup socket resources
        manager.disconnect(user_id)
        
        # Notify channel of client departure
        leave_event = {
            "system": True,
            "sender": "System",
            "message": f"User {user_id} disconnected.",
            "timestamp": datetime.utcnow().isoformat()
        }
        await manager.broadcast(json.dumps(leave_event))
