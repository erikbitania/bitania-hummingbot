import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from hummingbot.connector.exchange.bitania import bitania_constants as CONSTANTS
from hummingbot.connector.exchange.bitania.bitania_api_order_book_data_source import (
    BitaniaAPIOrderBookDataSource,
)
from hummingbot.connector.exchange.bitania.bitania_order_book import BitaniaOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class BitaniaOrderBookTests(IsolatedAsyncioTestCase):
    def test_snapshot_message_converts_levels(self):
        msg = BitaniaOrderBook.snapshot_message_from_exchange(
            {
                "bids": [{"price": 100.0, "amount": 1.5, "total": 150.0}],
                "asks": [{"price": 101.0, "amount": 2.0, "total": 202.0}],
            },
            timestamp=1700000000.0,
            metadata={"trading_pair": "BTC-USDT", "update_id": 1700000000000},
        )
        self.assertEqual(OrderBookMessageType.SNAPSHOT, msg.type)
        self.assertEqual("BTC-USDT", msg.content["trading_pair"])
        self.assertEqual([[100.0, 1.5]], msg.content["bids"])
        self.assertEqual([[101.0, 2.0]], msg.content["asks"])
        self.assertEqual(1700000000000, msg.content["update_id"])

    def test_trade_message_buy(self):
        msg = BitaniaOrderBook.trade_message_from_exchange(
            {"id": "t1", "price": 100.0, "amount": 1.0, "side": "buy", "ts": 1700000000000},
            metadata={"trading_pair": "BTC-USDT"},
        )
        self.assertEqual(OrderBookMessageType.TRADE, msg.type)
        self.assertEqual("t1", msg.content["trade_id"])
        # buy taker -> TradeType.BUY value
        self.assertEqual(float(1), msg.content["trade_type"])


class BitaniaAPIOrderBookDataSourceTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.trading_pair = "BTC-USDT"
        self.connector = MagicMock()
        self.connector.exchange_symbol_associated_to_pair = AsyncMock(return_value="BTC/USDT")
        self.connector.trading_pair_associated_to_exchange_symbol = AsyncMock(return_value="BTC-USDT")
        self.api_factory = MagicMock()
        self.data_source = BitaniaAPIOrderBookDataSource(
            trading_pairs=[self.trading_pair],
            connector=self.connector,
            api_factory=self.api_factory,
            domain=CONSTANTS.DEFAULT_DOMAIN,
        )

    def test_channel_originating_message_routes_orderbook(self):
        channel = self.data_source._channel_originating_message({"channel": "orderbook", "pair": "BTC/USDT"})
        self.assertEqual(CONSTANTS.DIFF_EVENT_TYPE, channel)

    def test_channel_originating_message_routes_trades(self):
        channel = self.data_source._channel_originating_message({"channel": "trades", "pair": "BTC/USDT"})
        self.assertEqual(CONSTANTS.TRADE_EVENT_TYPE, channel)

    def test_channel_originating_message_ignores_control(self):
        channel = self.data_source._channel_originating_message({"op": "pong"})
        self.assertEqual("", channel)

    async def test_parse_order_book_snapshot_message(self):
        queue = asyncio.Queue()
        raw = {
            "channel": "orderbook",
            "pair": "BTC/USDT",
            "data": {
                "bids": [{"price": 100.0, "amount": 1.0, "total": 100.0}],
                "asks": [{"price": 101.0, "amount": 1.0, "total": 101.0}],
            },
            "ts": 1700000000000,
        }
        await self.data_source._parse_order_book_snapshot_message(raw, queue)
        msg = queue.get_nowait()
        self.assertEqual(OrderBookMessageType.SNAPSHOT, msg.type)
        self.assertEqual("BTC-USDT", msg.content["trading_pair"])
        self.assertEqual(1700000000000, msg.content["update_id"])

    async def test_parse_trade_message(self):
        queue = asyncio.Queue()
        raw = {
            "channel": "trades",
            "pair": "BTC/USDT",
            "data": {"id": "t1", "price": 100.0, "amount": 1.0, "side": "sell", "time": "2023-11-14T22:13:20Z"},
        }
        await self.data_source._parse_trade_message(raw, queue)
        msg = queue.get_nowait()
        self.assertEqual(OrderBookMessageType.TRADE, msg.type)
        self.assertEqual("t1", msg.content["trade_id"])


if __name__ == "__main__":
    asyncio.get_event_loop()
