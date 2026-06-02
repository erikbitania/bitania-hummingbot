import asyncio
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.bitania import (
    bitania_constants as CONSTANTS,
    bitania_web_utils as web_utils,
)
from hummingbot.connector.exchange.bitania.bitania_order_book import BitaniaOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.bitania.bitania_exchange import BitaniaExchange


def _iso_to_ms(value: Any) -> int:
    """Best-effort convert an ISO-8601 string (or numeric ms) to epoch ms."""
    if value is None:
        return int(time.time() * 1e3)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        # Handle trailing "Z".
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1e3)
    except ValueError:
        return int(time.time() * 1e3)


class BitaniaAPIOrderBookDataSource(OrderBookTrackerDataSource):
    HEARTBEAT_TIME_INTERVAL = 30.0

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 trading_pairs: List[str],
                 connector: 'BitaniaExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__(trading_pairs)
        self._connector = connector
        self._trade_messages_queue_key = CONSTANTS.TRADE_EVENT_TYPE
        # Bitania has no diff channel; WS order-book frames are full snapshots,
        # which we route through the *snapshot* queue key so the tracker
        # replaces (not merges) the book each time.
        self._snapshot_messages_queue_key = CONSTANTS.DIFF_EVENT_TYPE
        self._domain = domain
        self._api_factory = api_factory

    async def get_last_traded_prices(self,
                                     trading_pairs: List[str],
                                     domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Fetches a full order-book snapshot from GET /orderbook?pair=BASE/QUOTE.
        Returns {"asks": [...], "bids": [...]}.
        """
        symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        params = {"pair": symbol}
        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.ORDERBOOK_PATH_URL, domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDERBOOK_PATH_URL,
        )
        return data

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        # REST snapshot has no sequence id; use the fetch timestamp (ms).
        update_id = int(snapshot_timestamp * 1e3)
        snapshot_msg: OrderBookMessage = BitaniaOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair, "update_id": update_id},
        )
        return snapshot_msg

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=web_utils.wss_url(self._domain),
                         ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the public orderbook + trades channels for every tracked
        pair. Bitania expects one subscribe frame per channel per pair:
            {"op":"subscribe","channel":"orderbook","pair":"BTC/USDT"}
        """
        try:
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                ob_request = WSJSONRequest(payload={
                    "op": CONSTANTS.WS_OP_SUBSCRIBE,
                    "channel": CONSTANTS.WS_CHANNEL_ORDERBOOK,
                    "pair": symbol,
                })
                trades_request = WSJSONRequest(payload={
                    "op": CONSTANTS.WS_OP_SUBSCRIBE,
                    "channel": CONSTANTS.WS_CHANNEL_TRADES,
                    "pair": symbol,
                })
                await ws.send(ob_request)
                await ws.send(trades_request)
            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...",
                exc_info=True,
            )
            raise

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        """
        Routes an inbound WS frame to the right local queue. Bitania tags each
        data frame with a top-level "channel". Control frames (pong, auth, sub
        acks) have no "channel" / no "data" and are ignored (return "").
        """
        channel = event_message.get("channel")
        if channel == CONSTANTS.WS_CHANNEL_ORDERBOOK:
            return self._snapshot_messages_queue_key
        elif channel == CONSTANTS.WS_CHANNEL_TRADES:
            return self._trade_messages_queue_key
        return ""

    async def _parse_order_book_snapshot_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        Parses a WS orderbook frame (full snapshot):
        {"channel":"orderbook","pair":"BTC/USDT","data":{"asks":[...],"bids":[...]},"ts":<ms>}
        """
        symbol = raw_message["pair"]
        trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=symbol)
        ts = int(raw_message.get("ts") or time.time() * 1e3)
        data = raw_message.get("data", {})
        snapshot_msg: OrderBookMessage = BitaniaOrderBook.snapshot_message_from_exchange(
            {"bids": data.get("bids", []), "asks": data.get("asks", [])},
            ts * 1e-3,
            metadata={"trading_pair": trading_pair, "update_id": ts},
        )
        message_queue.put_nowait(snapshot_msg)

    # NOTE: version-sensitive. On Hummingbot master the snapshot queue is drained
    # via `_parse_order_book_snapshot_message`. Some older releases only wired a
    # `_parse_order_book_diff_message`. If your build never replaces the book
    # from WS frames, alias the diff parser to the snapshot one below.
    _parse_order_book_diff_message = _parse_order_book_snapshot_message

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        Parses a WS trades frame:
        {"channel":"trades","pair":"BTC/USDT","data":{"id","price","amount","quoteAmount","side","time"}}
        """
        symbol = raw_message["pair"]
        trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=symbol)
        data = dict(raw_message.get("data", {}))
        # Prefer a frame-level ts; else derive ms from the trade's ISO time.
        ts = raw_message.get("ts")
        if ts is None:
            ts = _iso_to_ms(data.get("time"))
        data["ts"] = int(ts)
        trade_message = BitaniaOrderBook.trade_message_from_exchange(
            data, {"trading_pair": trading_pair})
        message_queue.put_nowait(trade_message)
