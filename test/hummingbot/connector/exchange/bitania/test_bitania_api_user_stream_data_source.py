import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from hummingbot.connector.exchange.bitania import bitania_constants as CONSTANTS
from hummingbot.connector.exchange.bitania.bitania_api_user_stream_data_source import (
    BitaniaAPIUserStreamDataSource,
)
from hummingbot.connector.exchange.bitania.bitania_auth import BitaniaAuth


class BitaniaAPIUserStreamDataSourceTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.auth = BitaniaAuth(api_key="key", secret_key="secret")
        self.connector = MagicMock()
        self.api_factory = MagicMock()
        self.data_source = BitaniaAPIUserStreamDataSource(
            auth=self.auth,
            trading_pairs=["BTC-USDT"],
            connector=self.connector,
            api_factory=self.api_factory,
            domain=CONSTANTS.DEFAULT_DOMAIN,
        )

    async def test_connect_authenticates_and_subscribes(self):
        ws = AsyncMock()
        # First receive() returns a successful auth ack.
        ws.receive.return_value = MagicMock(data={"op": "auth", "status": "ok"})
        self.api_factory.get_ws_assistant = AsyncMock(return_value=ws)

        result = await self.data_source._connected_websocket_assistant()
        self.assertIs(ws, result)
        # The first frame sent must be the auth payload.
        first_sent = ws.send.call_args_list[0].args[0]
        self.assertEqual("auth", first_sent.payload["op"])
        self.assertEqual("key", first_sent.payload["apiKey"])

    async def test_connect_raises_on_failed_auth(self):
        ws = AsyncMock()
        ws.receive.return_value = MagicMock(data={"op": "auth", "status": "error"})
        self.api_factory.get_ws_assistant = AsyncMock(return_value=ws)
        with self.assertRaises(IOError):
            await self.data_source._connected_websocket_assistant()

    async def test_subscribe_channels_sends_user_subscribe(self):
        ws = AsyncMock()
        await self.data_source._subscribe_channels(ws)
        sent = ws.send.call_args_list[0].args[0]
        self.assertEqual("subscribe", sent.payload["op"])
        self.assertEqual("user", sent.payload["channel"])

    async def test_process_event_message_forwards_user_event(self):
        queue = asyncio.Queue()
        event = {"channel": "user", "type": "fill", "data": {"orderId": "1"}}
        await self.data_source._process_event_message(event, queue)
        self.assertEqual(event, queue.get_nowait())

    async def test_process_event_message_drops_control_frames(self):
        queue = asyncio.Queue()
        await self.data_source._process_event_message({"op": "pong"}, queue)
        self.assertTrue(queue.empty())


if __name__ == "__main__":
    asyncio.get_event_loop()
