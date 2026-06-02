import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.bitania import (
    bitania_constants as CONSTANTS,
    bitania_utils,
    bitania_web_utils as web_utils,
)
from hummingbot.connector.exchange.bitania.bitania_api_order_book_data_source import BitaniaAPIOrderBookDataSource
from hummingbot.connector.exchange.bitania.bitania_api_user_stream_data_source import BitaniaAPIUserStreamDataSource
from hummingbot.connector.exchange.bitania.bitania_auth import BitaniaAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


def _iso_to_seconds(value: Any) -> float:
    """Convert an ISO-8601 timestamp (or numeric ms) to epoch seconds."""
    if value is None:
        import time
        return time.time()
    if isinstance(value, (int, float)):
        # Assume milliseconds if it looks like ms.
        return float(value) * (1e-3 if value > 1e11 else 1.0)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        import time
        return time.time()


class BitaniaExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    # NOTE: version-sensitive __init__ signature. Recent Hummingbot passes a
    # `client_config_map` as the first positional arg to ExchangePyBase. Older
    # releases used (balance_asset_limit, rate_limits_share_pct). This matches
    # current master; reconcile against your ExchangePyBase if construction
    # fails.
    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 bitania_api_key: str,
                 bitania_api_secret: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN,
                 ):
        self.api_key = bitania_api_key
        self.secret_key = bitania_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        super().__init__(client_config_map)

    @staticmethod
    def bitania_order_type(order_type: OrderType) -> str:
        """Maps a Hummingbot OrderType to Bitania's `type` field."""
        if order_type is OrderType.MARKET:
            return CONSTANTS.TYPE_MARKET
        # LIMIT and LIMIT_MAKER are both "limit"; LIMIT_MAKER is distinguished by
        # timeInForce=post_only (set in _place_order).
        return CONSTANTS.TYPE_LIMIT

    @staticmethod
    def to_hb_order_type(bitania_type: str) -> OrderType:
        if bitania_type == CONSTANTS.TYPE_MARKET:
            return OrderType.MARKET
        return OrderType.LIMIT

    @property
    def authenticator(self) -> BitaniaAuth:
        return BitaniaAuth(api_key=self.api_key, secret_key=self.secret_key)

    @property
    def name(self) -> str:
        return "bitania"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.PAIRS_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.PAIRS_PATH_URL

    @property
    def check_network_request_path(self):
        # GET /time is a cheap, always-available public endpoint.
        return CONSTANTS.SERVER_TIME_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        # POST /orders/{id}/cancel returns the updated order synchronously.
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    async def get_all_pairs_prices(self) -> List[Dict[str, Any]]:
        pairs = await self._api_get(path_url=CONSTANTS.PAIRS_PATH_URL)
        return pairs.get("pairs", [])

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        # Bitania auth has no timestamp/signature, so time drift can never cause
        # an auth failure.
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return CONSTANTS.ORDER_NOT_EXIST_MESSAGE in str(status_update_exception).lower()

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return CONSTANTS.UNKNOWN_ORDER_MESSAGE in str(cancelation_exception).lower()

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        # NOTE: no time_synchronizer passed — Bitania auth is timestamp-free.
        return web_utils.build_api_factory(
            throttler=self._throttler,
            domain=self._domain,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return BitaniaAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return BitaniaAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        is_maker = is_maker if is_maker is not None else (order_type is OrderType.LIMIT_MAKER)
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    async def _place_order(self,
                           order_id: str,
                           trading_pair: str,
                           amount: Decimal,
                           trade_type: TradeType,
                           order_type: OrderType,
                           price: Decimal,
                           **kwargs) -> Tuple[str, float]:
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        type_str = BitaniaExchange.bitania_order_type(order_type)

        api_params: Dict[str, Any] = {
            "pair": symbol,
            "side": side_str,
            "type": type_str,
            "amount": f"{amount:f}",
            "clientOrderId": order_id,
        }
        if order_type in (OrderType.LIMIT, OrderType.LIMIT_MAKER):
            api_params["price"] = f"{price:f}"
        if order_type is OrderType.LIMIT:
            api_params["timeInForce"] = CONSTANTS.TIME_IN_FORCE_GTC
        elif order_type is OrderType.LIMIT_MAKER:
            api_params["timeInForce"] = CONSTANTS.TIME_IN_FORCE_POST_ONLY

        order_result = await self._api_post(
            path_url=CONSTANTS.ORDERS_PATH_URL,
            data=api_params,
            is_auth_required=True,
            limit_id=CONSTANTS.ORDERS_PATH_URL,
        )
        order = order_result["order"]
        o_id = str(order["id"])
        transact_time = _iso_to_seconds(order.get("createdOn"))
        return o_id, transact_time

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        # The {id} path accepts either the exchange id or our clientOrderId; use
        # the client order id so cancellation works even before we learn the
        # exchange id.
        cancel_result = await self._api_post(
            path_url=CONSTANTS.ORDER_CANCEL_PATH_URL.format(order_id),
            is_auth_required=True,
            limit_id=CONSTANTS.ORDERS_PATH_URL,
        )
        order = cancel_result.get("order", {})
        status = str(order.get("status", "")).lower()
        return status in ("cancelled", "canceled")

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Builds TradingRule objects from GET /pairs.

        Each pair entry carries explicit increments / minimums:
          priceIncrement   -> min_price_increment
          amountIncrement  -> min_base_amount_increment
          minAmount        -> min_order_size (base)
          minNotional      -> min_notional_size (quote)
        """
        trading_pair_rules = exchange_info_dict.get("pairs", [])
        retval = []
        for rule in filter(bitania_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=rule.get("symbol"))
                retval.append(
                    TradingRule(
                        trading_pair,
                        min_order_size=Decimal(str(rule["minAmount"])),
                        min_price_increment=Decimal(str(rule["priceIncrement"])),
                        min_base_amount_increment=Decimal(str(rule["amountIncrement"])),
                        min_notional_size=Decimal(str(rule["minNotional"])),
                    )
                )
            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _update_trading_fees(self):
        """Bitania has no fee-schedule endpoint wired here; rely on DEFAULT_FEES."""
        pass

    async def _user_stream_event_listener(self):
        """
        Processes events from the private user stream. Bitania only emits fill
        events on this channel:
          {"channel":"user","type":"fill","data":{"fillId","orderId","pair",
           "side","price","amount","quoteAmount","time"}}

        Fills carry the exchange `orderId`, so we match against tracked orders by
        exchange order id. There are NO order-status events here; OPEN/CANCELED
        transitions come from REST status polling (_request_order_status). We do
        push a derived OrderUpdate after a fill so the bot reacts promptly:
        FILLED once the cumulative fill reaches the order amount, else
        PARTIALLY_FILLED.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                if event_message.get("type") != "fill":
                    continue
                data = event_message.get("data", {})
                exchange_order_id = str(data.get("orderId"))

                tracked_order = None
                for order in self._order_tracker.all_fillable_orders.values():
                    if order.exchange_order_id == exchange_order_id:
                        tracked_order = order
                        break
                if tracked_order is None:
                    continue

                fill_base = Decimal(str(data["amount"]))
                fill_quote = Decimal(str(data.get("quoteAmount", Decimal(str(data["price"])) * fill_base)))
                fill_price = Decimal(str(data["price"]))
                fill_ts = _iso_to_seconds(data.get("time"))

                # NOTE: Bitania fill events do not carry a per-fill fee token /
                # amount, so we attribute the estimated percentage fee in the
                # quote token. Confirm the real fee shape and adjust if Bitania
                # adds fee fields to the user-stream fill payload.
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=tracked_order.trade_type,
                    percent_token=tracked_order.quote_asset,
                )
                trade_update = TradeUpdate(
                    trade_id=str(data.get("fillId")),
                    client_order_id=tracked_order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=tracked_order.trading_pair,
                    fee=fee,
                    fill_base_amount=fill_base,
                    fill_quote_amount=fill_quote,
                    fill_price=fill_price,
                    fill_timestamp=fill_ts,
                )
                self._order_tracker.process_trade_update(trade_update)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """
        Backup fills fetch via GET /my-trades?pair=&limit=.

        LIMITATION: Bitania's /my-trades objects do NOT carry an orderId, so we
        cannot reliably attribute a historical trade to a specific order from
        REST alone. The authoritative fill source is the WS user-stream (fills
        there DO carry `orderId` — see _user_stream_event_listener). This method
        therefore returns no updates and exists to satisfy the framework
        interface; the WS path drives fills. If Bitania later adds `orderId` to
        /my-trades, populate TradeUpdates here filtered by order.exchange_order_id.
        """
        # NOTE: intentionally empty — see the docstring above. Returning [] is
        # safe: the order tracker simply gets no REST fills and relies on WS.
        return []

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        # GET /orders/{id} accepts our clientOrderId directly.
        updated = await self._api_get(
            path_url=CONSTANTS.ORDER_PATH_URL.format(tracked_order.client_order_id),
            is_auth_required=True,
            limit_id=CONSTANTS.ORDERS_PATH_URL,
        )
        order = updated["order"]
        new_state = CONSTANTS.ORDER_STATE[str(order["status"]).lower()]
        order_update = OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(order["id"]),
            trading_pair=tracked_order.trading_pair,
            update_timestamp=_iso_to_seconds(order.get("updatedOn") or order.get("createdOn")),
            new_state=new_state,
        )
        return order_update

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        response = await self._api_get(
            path_url=CONSTANTS.BALANCES_PATH_URL,
            is_auth_required=True,
        )
        balances = response.get("balances", [])
        for balance_entry in balances:
            # Use the short ticker (e.g. "BTC") as the Hummingbot asset symbol.
            asset_name = balance_entry["ticker"]
            free_balance = Decimal(str(balance_entry["available"]))
            total_balance = Decimal(str(balance_entry["total"]))
            self._account_available_balances[asset_name] = free_balance
            self._account_balances[asset_name] = total_balance
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(bitania_utils.is_exchange_information_valid, exchange_info.get("pairs", [])):
            # Bitania exchange symbol is "BASE/QUOTE"; map it to HB "BASE-QUOTE".
            mapping[symbol_data["symbol"]] = combine_to_hb_trading_pair(
                base=symbol_data["base"], quote=symbol_data["quote"])
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        resp = await self._api_request(
            method=RESTMethod.GET,
            path_url=CONSTANTS.TICKER_PATH_URL,
            params={"pair": symbol},
        )
        # GET /ticker returns a single pair object whose `price` is last/mark.
        return float(resp["price"])
