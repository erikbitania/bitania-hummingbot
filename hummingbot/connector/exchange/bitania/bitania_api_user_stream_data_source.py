import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.bitania import (
    bitania_constants as CONSTANTS,
    bitania_web_utils as web_utils,
)
from hummingbot.connector.exchange.bitania.bitania_auth import BitaniaAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest, WSResponse
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.bitania.bitania_exchange import BitaniaExchange


class BitaniaAPIUserStreamDataSource(UserStreamTrackerDataSource):
    """
    Bitania user-stream.

    There is NO listen-key REST call and NO listen-key keep-alive (unlike
    Binance). Instead, after the websocket connects we:
      1. send {"op":"auth","apiKey":"...","apiSecret":"..."}
      2. await {"op":"auth","status":"ok"}
      3. send {"op":"subscribe","channel":"user"}

    The only user events are fills:
      {"channel":"user","type":"fill","data":{"fillId","orderId","pair","side",
       "price","amount","quoteAmount","time"}}
    """

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: BitaniaAuth,
                 trading_pairs: List[str],
                 connector: 'BitaniaExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._auth: BitaniaAuth = auth
        self._domain = domain
        self._api_factory = api_factory
        self._connector = connector

    async def _get_ws_assistant(self) -> WSAssistant:
        return await self._api_factory.get_ws_assistant()

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._get_ws_assistant()
        await ws.connect(ws_url=web_utils.wss_url(self._domain),
                         ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)

        # Step 1: send the auth frame.
        auth_request = WSJSONRequest(payload=self._auth.ws_auth_payload())
        await ws.send(auth_request)

        # Step 2: await {"op":"auth","status":"ok"}.
        response: WSResponse = await ws.receive()
        data = response.data
        if not isinstance(data, dict) or data.get("op") != CONSTANTS.WS_OP_AUTH or data.get("status") != "ok":
            raise IOError(f"Bitania websocket authentication failed (response: {data})")

        self.logger().info("Authenticated Bitania user data stream websocket.")
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Step 3: subscribe to the private "user" channel. Must run only after a
        successful auth handshake.
        """
        try:
            subscribe_request = WSJSONRequest(payload={
                "op": CONSTANTS.WS_OP_SUBSCRIBE,
                "channel": CONSTANTS.WS_CHANNEL_USER,
            })
            await websocket_assistant.send(subscribe_request)
            self.logger().info("Subscribed to Bitania private user channel.")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error subscribing to the user data stream.")
            raise

    async def _process_event_message(self, event_message: Dict[str, Any], queue: asyncio.Queue):
        if not isinstance(event_message, dict) or len(event_message) == 0:
            return
        # Drop control frames (pong, auth ack, subscribe ack) — they carry an
        # "op" but no "channel".
        if event_message.get("op") in (CONSTANTS.WS_OP_PONG, CONSTANTS.WS_OP_AUTH, CONSTANTS.WS_OP_SUBSCRIBE):
            return
        # Forward only user-channel events to the connector's listener.
        if event_message.get("channel") == CONSTANTS.WS_CHANNEL_USER:
            queue.put_nowait(event_message)

    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        websocket_assistant and await websocket_assistant.disconnect()
