"""
Telemetry Service Module.
Handles MQTT telemetry subscriber/ingestion, in-memory telemetry buffer tracking,
and real-time WebRTC/telemetry WebSocket broadcasts.
"""

import os
import time
import json
import logging
import asyncio
from collections import deque
from typing import List, Dict, Any, Set, Optional
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class TelemetryBuffer:
    """
    In-memory telemetry buffer utilizing a thread-safe double-ended queue.
    Automatically trims old readings once max length is reached.
    """

    def __init__(self, maxlen: int = 1000):
        self._buffer: deque = deque(maxlen=maxlen)

    def append(self, data: Dict[str, Any]) -> None:
        """
        Stores a telemetry payload tagged with a local arrival timestamp.
        """
        self._buffer.append({
            "timestamp": time.time(),
            "data": data
        })

    def get_latest(self) -> Dict[str, Any]:
        """
        Returns the most recently received telemetry reading.
        """
        if not self._buffer:
            return {}
        return self._buffer[-1]["data"]

    def get_history(self, seconds: int = 60) -> List[Dict[str, Any]]:
        """
        Returns a list of telemetry payloads received within the last N seconds.
        """
        cutoff = time.time() - seconds
        return [record["data"] for record in self._buffer if record["timestamp"] >= cutoff]


class TelemetryBroadcastManager:
    """
    WebSocket and WebRTC signaling broadcast manager.
    Maintains active connections and broadcasts telemetry messages concurrently.
    """

    def __init__(self):
        self.active_connections: Set[Any] = set()

    def register(self, websocket: Any) -> None:
        """
        Registers an active WebSocket client connection.
        """
        self.active_connections.add(websocket)
        logger.debug(f"Registered WebSocket client. Total connections: {len(self.active_connections)}")

    def unregister(self, websocket: Any) -> None:
        """
        Unregisters/discards a WebSocket connection.
        """
        self.active_connections.discard(websocket)
        logger.debug(f"Unregistered WebSocket client. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        Asynchronously broadcasts a payload to all connected clients.
        Sends are grouped concurrently so slow or hung clients do not block the thread.
        """
        if not self.active_connections:
            return

        payload = json.dumps(message)
        tasks = []
        clients = list(self.active_connections)

        for client in clients:
            try:
                # Expects a standard FastAPI WebSocket instance with send_text
                tasks.append(client.send_text(payload))
            except Exception as e:
                logger.error(f"Failed to prepare telemetry broadcast to client: {e}")
                self.active_connections.discard(client)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for client, result in zip(clients, results):
                if isinstance(result, Exception):
                    logger.warning(f"Removing failing WebSocket connection during broadcast: {result}")
                    self.active_connections.discard(client)


# Alias ConnectionManager to TelemetryBroadcastManager for package backwards compatibility
ConnectionManager = TelemetryBroadcastManager

# Global instances for memory buffer and WebSocket manager
TELEMETRY_BUFFER = TelemetryBuffer(maxlen=1000)
BROADCAST_MANAGER = TelemetryBroadcastManager()

# Event loop pointer to safely route background MQTT thread signals to the main async thread
main_loop: Optional[asyncio.AbstractEventLoop] = None
mqtt_client: Optional[mqtt.Client] = None


async def ingest_telemetry(data: Dict[str, Any]) -> None:
    """
    Main telemetry ingestion gateway.
    Stores the data in-memory and broadcasts it to active WebSocket clients.
    """
    # 1. Ingest in memory buffer
    TELEMETRY_BUFFER.append(data)

    # 2. Forward to active WebSocket/WebRTC subscribers
    await BROADCAST_MANAGER.broadcast(data)


def get_latest_telemetry() -> Dict[str, Any]:
    """
    Retrieves the most recent telemetry reading from the buffer.
    """
    return TELEMETRY_BUFFER.get_latest()


def get_telemetry_history(seconds: int = 60) -> List[Dict[str, Any]]:
    """
    Retrieves historical telemetry readings received within the specified number of seconds.
    """
    return TELEMETRY_BUFFER.get_history(seconds)


def init_mqtt_client(loop: Optional[asyncio.AbstractEventLoop] = None) -> Optional[mqtt.Client]:
    """
    Initializes and starts the MQTT telemetry client subscriber in a background thread.
    
    Loads configuration from environment variables:
    - MQTT_BROKER_HOST (e.g. 'localhost' or 'broker.hivemq.com')
    - MQTT_BROKER_PORT (default 1883)
    - MQTT_TOPIC (default 'tu5g/telemetry/#')
    - MQTT_CLIENT_ID (default 'tu5g_backend_subscriber')
    - MQTT_USER (optional)
    - MQTT_PASSWORD (optional)
    """
    global mqtt_client, main_loop

    # Store a reference to the main thread's event loop
    if loop:
        main_loop = loop
    else:
        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    broker_host = os.getenv("MQTT_BROKER_HOST")
    if not broker_host:
        logger.warning("MQTT_BROKER_HOST environment variable is not defined. MQTT Subscriber skipped.")
        return None

    broker_port_str = os.getenv("MQTT_BROKER_PORT", "1883")
    topic = os.getenv("MQTT_TOPIC", "tu5g/telemetry/#")
    client_id = os.getenv("MQTT_CLIENT_ID", "tu5g_backend_subscriber")
    username = os.getenv("MQTT_USER")
    password = os.getenv("MQTT_PASSWORD")

    try:
        broker_port = int(broker_port_str)
    except ValueError:
        logger.error(f"Invalid MQTT_BROKER_PORT: {broker_port_str}. Falling back to 1883.")
        broker_port = 1883

    try:
        # Compatibility handling for Paho MQTT 2.x callback API versioning
        try:
            mqtt_client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id=client_id
            )
        except AttributeError:
            # Fallback to Paho MQTT 1.x
            mqtt_client = mqtt.Client(client_id=client_id)

        if username and password:
            mqtt_client.username_pw_set(username, password)

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info(f"Successfully connected to MQTT broker at {broker_host}:{broker_port}")
                client.subscribe(topic)
                logger.info(f"Subscribed to telemetry topic: {topic}")
            else:
                logger.error(f"Failed to connect to MQTT broker, status code: {rc}")

        def on_message(client, userdata, msg):
            try:
                payload = msg.payload.decode("utf-8")
                data = json.loads(payload)
                
                # Deque operations are naturally thread-safe in Python
                TELEMETRY_BUFFER.append(data)

                # Thread-safe dispatch of the broadcast task back to the main event loop
                if main_loop and main_loop.is_running():
                    main_loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(BROADCAST_MANAGER.broadcast(data))
                    )
                else:
                    logger.warning("Main event loop is not running. Broadcast skipped.")
            except json.JSONDecodeError:
                logger.error(f"Received malformed non-JSON MQTT payload: {msg.payload}")
            except Exception as e:
                logger.error(f"Error processing MQTT message: {e}")

        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message

        # Start standard background worker thread for MQTT loop
        mqtt_client.connect_async(broker_host, broker_port, keepalive=60)
        mqtt_client.loop_start()
        logger.info("MQTT Client background worker thread started.")
        return mqtt_client

    except Exception as e:
        logger.error(f"Failed to initialize MQTT telemetry client: {e}")
        return None
