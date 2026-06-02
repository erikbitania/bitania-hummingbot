from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

# Bitania uses a single domain (no testnet yet). DEFAULT_DOMAIN is the key used
# to select the host pair below; "com" -> api.bitania.com.
DEFAULT_DOMAIN = "com"

HBOT_ORDER_ID_PREFIX = "HBOT-"
# Bitania accepts our client order id verbatim as `clientOrderId`. Keep it well
# under any sane server-side column limit.
MAX_ORDER_ID_LEN = 40

# Base URLs. The "{}" is filled with the domain key (see DEFAULT_DOMAIN). Today
# only "com" is wired up, but keeping the format string makes adding a future
# testnet/staging domain a one-line change.
REST_URL = "https://api.bitania.{}/v1/exchange"
WSS_URL = "wss://api.bitania.{}/v1/ws"

# Public REST endpoints
PAIRS_PATH_URL = "/pairs"
TICKER_PATH_URL = "/ticker"
ORDERBOOK_PATH_URL = "/orderbook"
TRADES_PATH_URL = "/trades"
SERVER_TIME_PATH_URL = "/time"

# Private REST endpoints
ORDERS_PATH_URL = "/orders"
ORDER_PATH_URL = "/orders/{}"          # GET single order by exchange id OR clientOrderId
ORDER_CANCEL_PATH_URL = "/orders/{}/cancel"
MY_TRADES_PATH_URL = "/my-trades"
BALANCES_PATH_URL = "/balances"

WS_HEARTBEAT_TIME_INTERVAL = 30

# Bitania order params
SIDE_BUY = "buy"
SIDE_SELL = "sell"

TYPE_LIMIT = "limit"
TYPE_MARKET = "market"

# timeInForce values. post_only is how Bitania expresses a maker-only order,
# which maps to Hummingbot's OrderType.LIMIT_MAKER.
TIME_IN_FORCE_GTC = "gtc"
TIME_IN_FORCE_IOC = "ioc"
TIME_IN_FORCE_FOK = "fok"
TIME_IN_FORCE_POST_ONLY = "post_only"

# WS op / channel names
WS_OP_AUTH = "auth"
WS_OP_SUBSCRIBE = "subscribe"
WS_OP_PING = "ping"
WS_OP_PONG = "pong"
WS_CHANNEL_ORDERBOOK = "orderbook"
WS_CHANNEL_TRADES = "trades"
WS_CHANNEL_USER = "user"

# Local queue keys for the order book data source (these are internal labels,
# not Bitania wire values).
TRADE_EVENT_TYPE = "trades"
# Bitania only publishes full snapshots; we route them through the "diff" path
# as full snapshots.
DIFF_EVENT_TYPE = "orderbook"

# Rate Limit pool / time intervals
GLOBAL_RATE_LIMIT_ID = "BitaniaGlobal"
MARKET_DATA_LIMIT_ID = "BitaniaMarketData"
ORDERS_LIMIT_ID = "BitaniaOrders"
GENERAL_LIMIT_ID = "BitaniaGeneral"

ONE_MINUTE = 60
ONE_SECOND = 1
ONE_DAY = 86400

MAX_REQUEST = 5000

# Real server-side limits for the default authenticated ("standard") API-key
# tier on Bitania — see gbit/util/rate_limits.py RATE_LIMIT_TIERS["standard"].
# The connector throttles to these so a fresh key won't be 429'd. Higher tiers
# (professional/enterprise) exist server-side but are not yet auto-granted, so
# standard is the safe default. Limits are per minute.
MARKET_DATA_PER_MIN = 300      # pairs / ticker / orderbook / trades / time
ORDER_PLACEMENT_PER_MIN = 60   # POST /orders  (the binding limit on the orders bucket)
GENERAL_PER_MIN = 120          # balances / my-trades / single-order status
GLOBAL_PER_MIN = 600           # cross-category umbrella (per-category pools bind first)

# Order status -> Hummingbot OrderState mapping.
# Bitania statuses: open | partially_filled | filled | cancelled
ORDER_STATE = {
    "open": OrderState.OPEN,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "filled": OrderState.FILLED,
    "cancelled": OrderState.CANCELED,
    # Defensive aliases in case the API ever emits these variants.
    "canceled": OrderState.CANCELED,
    "rejected": OrderState.FAILED,
    "expired": OrderState.FAILED,
    "pending": OrderState.PENDING_CREATE,
}

# Pools mirror Bitania's per-category server limits (standard tier). Per-endpoint
# limits are MAX_REQUEST (effectively unbounded) and bind through the linked
# pools, so the throttle a key actually sees is the category pool below.
RATE_LIMITS = [
    # Pools (per minute, matching gbit RATE_LIMIT_TIERS["standard"])
    RateLimit(limit_id=GLOBAL_RATE_LIMIT_ID, limit=GLOBAL_PER_MIN, time_interval=ONE_MINUTE),
    RateLimit(limit_id=MARKET_DATA_LIMIT_ID, limit=MARKET_DATA_PER_MIN, time_interval=ONE_MINUTE),
    RateLimit(limit_id=ORDERS_LIMIT_ID, limit=ORDER_PLACEMENT_PER_MIN, time_interval=ONE_MINUTE),
    RateLimit(limit_id=GENERAL_LIMIT_ID, limit=GENERAL_PER_MIN, time_interval=ONE_MINUTE),
    # Public endpoints (counted against the market-data + global pools)
    RateLimit(limit_id=PAIRS_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(MARKET_DATA_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    RateLimit(limit_id=TICKER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(MARKET_DATA_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    RateLimit(limit_id=ORDERBOOK_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(MARKET_DATA_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    RateLimit(limit_id=TRADES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(MARKET_DATA_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(MARKET_DATA_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    # Private "general" endpoints (server category "general" = 120/min)
    RateLimit(limit_id=BALANCES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
    # Order placement / status / cancel share the ORDERS pool via limit_id=
    # ORDERS_PATH_URL. Server-side, placement is the most restrictive (60/min)
    # while status/cancel are looser (general/120, cancel/120); throttling all
    # three at 60/min is intentionally conservative so we never 429.
    RateLimit(limit_id=ORDERS_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(ORDERS_LIMIT_ID, 1),
                             LinkedLimitWeightPair(GLOBAL_RATE_LIMIT_ID, 1)]),
]

# Error-string fragments used to detect "order not found" in an HTTP error body.
# Confirmed against the API: GET/cancel on a missing order returns 404 with body
# {"error": "Order not found"} — the lowercase "not found" fragment matches it.
ORDER_NOT_EXIST_MESSAGE = "not found"
UNKNOWN_ORDER_MESSAGE = "not found"
