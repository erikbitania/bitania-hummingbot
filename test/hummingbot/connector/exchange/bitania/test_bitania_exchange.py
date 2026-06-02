import asyncio
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from hummingbot.connector.exchange.bitania import bitania_constants as CONSTANTS
from hummingbot.connector.exchange.bitania.bitania_exchange import BitaniaExchange
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import OrderState


def _build_exchange() -> BitaniaExchange:
    client_config_map = MagicMock()
    with patch.object(BitaniaExchange, "_create_web_assistants_factory", return_value=MagicMock()):
        exchange = BitaniaExchange(
            client_config_map=client_config_map,
            bitania_api_key="key",
            bitania_api_secret="secret",
            trading_pairs=["BTC-USDT"],
            trading_required=False,
        )
    return exchange


class BitaniaExchangeTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.exchange = _build_exchange()

    def test_name(self):
        self.assertEqual("bitania", self.exchange.name)

    def test_supported_order_types(self):
        types = self.exchange.supported_order_types()
        self.assertIn(OrderType.LIMIT, types)
        self.assertIn(OrderType.LIMIT_MAKER, types)
        self.assertIn(OrderType.MARKET, types)

    def test_order_type_mapping(self):
        self.assertEqual(CONSTANTS.TYPE_MARKET, BitaniaExchange.bitania_order_type(OrderType.MARKET))
        self.assertEqual(CONSTANTS.TYPE_LIMIT, BitaniaExchange.bitania_order_type(OrderType.LIMIT))
        self.assertEqual(CONSTANTS.TYPE_LIMIT, BitaniaExchange.bitania_order_type(OrderType.LIMIT_MAKER))

    def test_order_state_mapping(self):
        self.assertEqual(OrderState.OPEN, CONSTANTS.ORDER_STATE["open"])
        self.assertEqual(OrderState.PARTIALLY_FILLED, CONSTANTS.ORDER_STATE["partially_filled"])
        self.assertEqual(OrderState.FILLED, CONSTANTS.ORDER_STATE["filled"])
        self.assertEqual(OrderState.CANCELED, CONSTANTS.ORDER_STATE["cancelled"])

    def test_initialize_trading_pair_symbols(self):
        exchange_info = {
            "pairs": [
                {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT"},
                {"symbol": "LTC/USDT", "base": "LTC", "quote": "USDT"},
            ]
        }
        self.exchange._initialize_trading_pair_symbols_from_exchange_info(exchange_info)
        symbol_map = self.exchange._trading_pair_symbol_map
        self.assertEqual("BTC-USDT", symbol_map["BTC/USDT"])
        self.assertEqual("LTC-USDT", symbol_map["LTC/USDT"])

    async def test_format_trading_rules(self):
        self.exchange.trading_pair_associated_to_exchange_symbol = AsyncMock(return_value="BTC-USDT")
        exchange_info = {
            "pairs": [{
                "symbol": "BTC/USDT",
                "base": "BTC",
                "quote": "USDT",
                "priceIncrement": 0.01,
                "amountIncrement": 0.000001,
                "minAmount": 0.0001,
                "minNotional": 5.0,
            }]
        }
        rules = await self.exchange._format_trading_rules(exchange_info)
        self.assertEqual(1, len(rules))
        rule = rules[0]
        self.assertEqual("BTC-USDT", rule.trading_pair)
        self.assertEqual(Decimal("0.01"), rule.min_price_increment)
        self.assertEqual(Decimal("0.000001"), rule.min_base_amount_increment)
        self.assertEqual(Decimal("0.0001"), rule.min_order_size)
        self.assertEqual(Decimal("5.0"), rule.min_notional_size)

    async def test_place_order_limit_maker_sets_post_only(self):
        self.exchange.exchange_symbol_associated_to_pair = AsyncMock(return_value="BTC/USDT")
        captured = {}

        async def fake_post(path_url, data=None, is_auth_required=False, limit_id=None):
            captured.update(data)
            return {"order": {"id": "exch-1", "createdOn": "2023-11-14T22:13:20Z"}}

        self.exchange._api_post = fake_post
        o_id, ts = await self.exchange._place_order(
            order_id="HBOT-1",
            trading_pair="BTC-USDT",
            amount=Decimal("1"),
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT_MAKER,
            price=Decimal("100"),
        )
        self.assertEqual("exch-1", o_id)
        self.assertEqual(CONSTANTS.TIME_IN_FORCE_POST_ONLY, captured["timeInForce"])
        self.assertEqual("buy", captured["side"])
        self.assertEqual("BTC/USDT", captured["pair"])
        self.assertEqual("HBOT-1", captured["clientOrderId"])

    async def test_place_cancel_returns_true_on_cancelled(self):
        async def fake_post(path_url, is_auth_required=False, limit_id=None):
            return {"order": {"id": "exch-1", "status": "cancelled"}}

        self.exchange._api_post = fake_post
        tracked = MagicMock()
        tracked.trading_pair = "BTC-USDT"
        result = await self.exchange._place_cancel("HBOT-1", tracked)
        self.assertTrue(result)

    async def test_update_balances(self):
        async def fake_get(path_url, is_auth_required=False):
            return {"balances": [
                {"asset": "bitcoin", "ticker": "BTC", "total": 2.0, "available": 1.5, "locked": 0.5, "usdValue": 0},
            ]}

        self.exchange._api_get = fake_get
        await self.exchange._update_balances()
        self.assertEqual(Decimal("1.5"), self.exchange.available_balances["BTC"])
        self.assertEqual(Decimal("2.0"), self.exchange.get_balance("BTC"))

    async def test_request_order_status(self):
        self.exchange.exchange_symbol_associated_to_pair = AsyncMock(return_value="BTC/USDT")

        async def fake_get(path_url, is_auth_required=False, limit_id=None):
            return {"order": {
                "id": "exch-1",
                "status": "filled",
                "createdOn": "2023-11-14T22:13:20Z",
                "updatedOn": "2023-11-14T22:14:20Z",
            }}

        self.exchange._api_get = fake_get
        tracked = MagicMock()
        tracked.client_order_id = "HBOT-1"
        tracked.trading_pair = "BTC-USDT"
        update = await self.exchange._request_order_status(tracked)
        self.assertEqual(OrderState.FILLED, update.new_state)
        self.assertEqual("exch-1", update.exchange_order_id)

    async def test_all_trade_updates_for_order_is_empty(self):
        tracked = MagicMock()
        updates = await self.exchange._all_trade_updates_for_order(tracked)
        self.assertEqual([], updates)


if __name__ == "__main__":
    asyncio.get_event_loop()
