"""
OBS WebSocket client using the standard websockets library.

Implements the OBS WebSocket protocol v5 for controlling OBS Studio.
Documentation: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class OBSWebSocketError(Exception):
    """Raised when OBS WebSocket operations fail."""

    pass


class OBSWebSocketClient:
    """
    OBS WebSocket client implementing protocol v5.

    Handles authentication, request/response, and provides high-level
    methods for controlling OBS scenes and sources.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """
        Initialize OBS WebSocket client.

        Args:
            url: WebSocket URL (e.g., "ws://localhost:4444")
            password: WebSocket password for authentication
            timeout: Request timeout in seconds
        """
        self.url = url or os.getenv("OBS_WEBSOCKET_URL", "ws://localhost:4444")
        self.password = password or os.getenv("OBS_WEBSOCKET_PASSWORD", "")
        self.timeout = timeout
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.rpc_version = 1
        self._response_futures: Dict[str, asyncio.Future] = {}

        # Events for handshake coordination
        self._hello_received: asyncio.Event = asyncio.Event()
        self._identified_received: asyncio.Event = asyncio.Event()
        self._hello_data: Optional[Dict] = None
        self._receive_task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        """Connect to OBS WebSocket on context entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Disconnect from OBS WebSocket on context exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """
        Connect to OBS WebSocket and complete authentication handshake.

        Raises:
            OBSWebSocketError: If connection or authentication fails
        """
        try:
            logger.debug(f"Connecting to OBS WebSocket at {self.url}")

            # Clear events from any previous connection
            self._hello_received.clear()
            self._identified_received.clear()
            self._hello_data = None

            # Connect to WebSocket
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.url), timeout=self.timeout
            )

            # Start background task to receive ALL messages (only one receiver)
            self._receive_task = asyncio.create_task(self._receive_messages())

            # Wait for Hello message (received by background task)
            await asyncio.wait_for(
                self._hello_received.wait(), timeout=self.timeout
            )

            if not self._hello_data:
                raise OBSWebSocketError("Hello message was not received properly")

            logger.debug(
                f"Connected to OBS WebSocket v{self._hello_data['d'].get('obsWebSocketVersion')}"
            )

            # Send Identify message (OpCode 1) with authentication
            auth_string = None
            if "authentication" in self._hello_data["d"]:
                auth_string = self._generate_auth_string(
                    self._hello_data["d"]["authentication"]
                )

            identify_msg = {
                "op": 1,
                "d": {
                    "rpcVersion": self.rpc_version,
                    "eventSubscriptions": 0,  # We don't need events
                },
            }

            if auth_string:
                identify_msg["d"]["authentication"] = auth_string

            await self.websocket.send(json.dumps(identify_msg))

            # Wait for Identified message (received by background task)
            await asyncio.wait_for(
                self._identified_received.wait(), timeout=self.timeout
            )

            logger.debug("Successfully authenticated with OBS WebSocket")

        except asyncio.TimeoutError:
            raise OBSWebSocketError(f"Connection timeout to {self.url}")
        except websockets.exceptions.WebSocketException as e:
            raise OBSWebSocketError(f"WebSocket connection failed: {e}")
        except Exception as e:
            raise OBSWebSocketError(f"Failed to connect to OBS: {e}")

    async def disconnect(self) -> None:
        """Disconnect from OBS WebSocket."""
        # Cancel background task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket connection
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.debug("Disconnected from OBS WebSocket")

    def _generate_auth_string(self, auth_data: Dict[str, str]) -> str:
        """
        Generate authentication string using OBS WebSocket protocol.

        Authentication flow:
        1. secret = base64(SHA256(password + salt))
        2. auth = base64(SHA256(secret + challenge))

        Args:
            auth_data: Dict containing 'challenge' and 'salt' from Hello message

        Returns:
            Base64-encoded authentication string
        """
        challenge = auth_data["challenge"]
        salt = auth_data["salt"]

        # Step 1: hash password with salt
        secret_hash = hashlib.sha256((self.password + salt).encode("utf-8")).digest()
        secret = base64.b64encode(secret_hash).decode("utf-8")

        # Step 2: hash secret with challenge
        auth_hash = hashlib.sha256((secret + challenge).encode("utf-8")).digest()
        auth_string = base64.b64encode(auth_hash).decode("utf-8")

        return auth_string

    async def _receive_messages(self) -> None:
        """
        Background task to receive and route ALL messages.

        This is the ONLY coroutine that calls websocket.recv() to avoid
        the "cannot call recv while another coroutine is already running recv" error.
        """
        if not self.websocket:
            return

        try:
            async for message in self.websocket:
                data = json.loads(message)
                op = data.get("op")

                # OpCode 0 = Hello (handshake)
                if op == 0:
                    self._hello_data = data
                    self._hello_received.set()
                    logger.debug("Received Hello message")

                # OpCode 2 = Identified (handshake confirmation)
                elif op == 2:
                    self._identified_received.set()
                    logger.debug("Received Identified message")

                # OpCode 7 = RequestResponse
                elif op == 7:
                    request_id = data["d"].get("requestId")
                    if request_id in self._response_futures:
                        future = self._response_futures.pop(request_id)
                        if not future.done():
                            future.set_result(data)

                # OpCode 5 = Event (we ignore these for now)
                elif op == 5:
                    pass

                else:
                    logger.debug(f"Received unhandled message: {data}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning("OBS WebSocket connection closed")
        except asyncio.CancelledError:
            logger.debug("Message receiving task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")

    async def send_request(
        self, request_type: str, request_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a request to OBS WebSocket and wait for response.

        Args:
            request_type: OBS request type (e.g., "SetCurrentProgramScene")
            request_data: Optional request parameters

        Returns:
            Response data dict

        Raises:
            OBSWebSocketError: If request fails or times out
        """
        if not self.websocket:
            raise OBSWebSocketError("Not connected to OBS WebSocket")

        request_id = str(uuid.uuid4())
        request_msg = {
            "op": 6,  # OpCode 6 = Request
            "d": {
                "requestType": request_type,
                "requestId": request_id,
            },
        }

        if request_data:
            request_msg["d"]["requestData"] = request_data

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._response_futures[request_id] = future

        # Send request
        await self.websocket.send(json.dumps(request_msg))
        logger.debug(f"Sent request: {request_type} (id={request_id})")

        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=self.timeout)
            status = response["d"]["requestStatus"]

            if not status.get("result"):
                error_code = status.get("code", "unknown")
                error_comment = status.get("comment", "No error message")
                raise OBSWebSocketError(
                    f"Request {request_type} failed: {error_comment} (code={error_code})"
                )

            return response["d"].get("responseData", {})

        except asyncio.TimeoutError:
            self._response_futures.pop(request_id, None)
            raise OBSWebSocketError(f"Request {request_type} timed out")

    async def switch_scene(self, scene_name: str) -> None:
        """
        Switch to the specified scene.

        Args:
            scene_name: Name of the scene to switch to

        Raises:
            OBSWebSocketError: If scene switch fails
        """
        logger.info(f"Switching OBS scene to: {scene_name}")
        await self.send_request(
            "SetCurrentProgramScene", {"sceneName": scene_name}
        )
        logger.info(f"Successfully switched to scene: {scene_name}")

    async def update_text_source(self, input_name: str, text: str) -> None:
        """
        Update the text content of a text source.

        Args:
            input_name: Name of the text input/source
            text: New text content

        Raises:
            OBSWebSocketError: If text update fails
        """
        logger.debug(f"Updating text source '{input_name}' to: {text}")
        await self.send_request(
            "SetInputSettings",
            {
                "inputName": input_name,
                "inputSettings": {"text": text},
            },
        )

    async def get_stream_status(self) -> bool:
        """
        Get the current streaming status.

        Returns:
            True if OBS is currently streaming, False otherwise

        Raises:
            OBSWebSocketError: If status check fails
        """
        logger.debug("Checking OBS stream status")
        response = await self.send_request("GetStreamStatus")
        is_streaming = response.get("outputActive", False)
        logger.debug(f"Stream status: {'active' if is_streaming else 'inactive'}")
        return is_streaming

    async def start_stream(self) -> None:
        """
        Start streaming in OBS.

        Raises:
            OBSWebSocketError: If stream start fails
        """
        logger.info("Starting OBS stream")
        await self.send_request("StartStream")
        logger.info("Successfully started OBS stream")

    async def stop_stream(self) -> None:
        """
        Stop streaming in OBS.

        Raises:
            OBSWebSocketError: If stream stop fails
        """
        logger.info("Stopping OBS stream")
        await self.send_request("StopStream")
        logger.info("Successfully stopped OBS stream")
