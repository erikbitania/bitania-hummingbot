from typing import Dict, List, Optional

from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


def _levels_to_pairs(levels: List[Dict]) -> List[List[float]]:
    """
    Bitania order-book levels look like {"price": .., "amount": .., "total": ..}.
    Hummingbot's OrderBookMessage expects [price, amount] pairs. Convert here.
    """
    pairs = []
    for level in levels or []:
        pairs.append([float(level["price"]), float(level["amount"])])
    return pairs


class BitaniaOrderBook(OrderBook):

    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: Dict[str, any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        Creates a SNAPSHOT order-book message.

        Bitania exposes only full snapshots (REST GET /orderbook and the WS
        "orderbook" channel both return the whole book), so there is no diff
        path. ``msg`` must contain "trading_pair", "update_id", and the raw
        "bids"/"asks" level lists.
        """
        if metadata:
            msg.update(metadata)
        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": msg["trading_pair"],
            "update_id": msg["update_id"],
            "bids": _levels_to_pairs(msg.get("bids", [])),
            "asks": _levels_to_pairs(msg.get("asks", [])),
        }, timestamp=timestamp)

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: Dict[str, any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        Bitania has NO diff channel. We never call this in practice; WS
        order-book frames are full snapshots and are routed through
        ``snapshot_message_from_exchange`` instead. Kept for interface parity.
        """
        if metadata:
            msg.update(metadata)
        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": msg["trading_pair"],
            "update_id": msg["update_id"],
            "bids": _levels_to_pairs(msg.get("bids", [])),
            "asks": _levels_to_pairs(msg.get("asks", [])),
        }, timestamp=timestamp)

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, any], metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        Creates a TRADE message from a Bitania trade event.

        ``msg`` is the trade object: {"id", "price", "amount", "quoteAmount",
        "side": "buy"|"sell", "time"|"ts"}. ``time`` is ISO-8601 from REST; the
        WS path passes a numeric "ts" (ms) in metadata for the update id.
        """
        if metadata:
            msg.update(metadata)
        ts = msg["ts"]  # epoch ms; injected by the data source
        # Bitania reports trade side from the taker's perspective.
        trade_type = float(TradeType.SELL.value) if msg["side"] == "sell" else float(TradeType.BUY.value)
        return OrderBookMessage(OrderBookMessageType.TRADE, {
            "trading_pair": msg["trading_pair"],
            "trade_type": trade_type,
            "trade_id": msg["id"],
            "update_id": ts,
            "price": msg["price"],
            "amount": msg["amount"],
        }, timestamp=ts * 1e-3)
