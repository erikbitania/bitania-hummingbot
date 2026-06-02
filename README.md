# Bitania Hummingbot Connector (spot)

A community **spot** connector that lets you run [Hummingbot](https://hummingbot.org)
strategies against the **Bitania** exchange (`bitania.com`). It is a drop-in
connector built on Hummingbot's `ExchangePyBase`, structured exactly like the
in-tree connectors so it can be copied straight into a Hummingbot source
checkout.

> **For market makers:** point your favorite Hummingbot strategy (pure market
> making, cross-exchange MM, Avellaneda, V2 controllers, etc.) at Bitania's order
> book. The connector supports `LIMIT`, `LIMIT_MAKER` (post-only), and `MARKET`
> orders, real-time order-book + trade streams over WebSocket, and fill-driven
> position tracking.

---

## Quick Start (≈10 minutes)

This gets you from zero to a running market-making bot on the **XMR-USDT** pair.

> 🧪 **Test risk-free FIRST.** Before you trade real funds, run the strategy in
> Hummingbot's built-in **`paper_trade`** mode (simulated balances, live prices,
> no real orders). It's the single best way to sanity-check your config and
> spreads with zero risk. See step 6 — do that before step 5.

### 1. Get a Hummingbot source install

Install Hummingbot from source (the connector is a pure-Python drop-in, so a
source checkout is all you need):

```bash
git clone https://github.com/hummingbot/hummingbot.git
cd hummingbot
./install                 # creates the `hummingbot` conda env
conda activate hummingbot
```

Full official guide: <https://hummingbot.org/installation/source/>.

### 2. Copy the Bitania connector into your Hummingbot tree

Clone this repo, then copy the connector package into the exact in-tree path
Hummingbot auto-discovers:

```bash
git clone https://github.com/erikbitania/bitania-hummingbot.git

# copy the connector package into your Hummingbot checkout
cp -r bitania-hummingbot/hummingbot/connector/exchange/bitania \
      hummingbot/hummingbot/connector/exchange/bitania

# (optional) copy the test suite too
cp -r bitania-hummingbot/test/hummingbot/connector/exchange/bitania \
      hummingbot/test/hummingbot/connector/exchange/bitania
```

The destination path is exactly
`hummingbot/hummingbot/connector/exchange/bitania` (the `hummingbot/` repo root,
then the in-tree `hummingbot/connector/exchange/` package dir, then `bitania`).
Hummingbot auto-discovers any connector package under
`hummingbot/connector/exchange/`, so `bitania` shows up in `connect` with no
further registration.

### 3. Compile + launch Hummingbot

```bash
cd hummingbot
conda activate hummingbot
./compile      # builds Hummingbot's Cython parts (the Bitania connector itself is pure Python)
./start        # launches the Hummingbot client
```

### 4. Create a Bitania API key (with trade permission)

1. Log in at **<https://exchange.bitania.com>**.
2. Go to **Account → API Keys** and **Create API key**.
3. Grant it **Trade** permission (placing/cancelling orders) plus balance read.
   Save the **key** and **secret** — the secret is shown only once.

> 💰 **Lower your fees:** Bitania's standard maker fee is **0.15%**, but the
> **MM Program** can rebate the maker fee down to **0%** for qualifying market
> makers. Apply via the MM Program page in the exchange and use `LIMIT_MAKER`
> (post-only) orders to stay on the maker side. (Hummingbot can't model a tier
> rebate statically, so its PnL estimate uses the standard 0.15% maker rate —
> your effective fees are equal or better once enrolled.)

### 5. Connect your keys in Hummingbot

In the Hummingbot client prompt:

```
>>> connect bitania
Enter your Bitania API key      >>> <paste key>
Enter your Bitania API secret   >>> <paste secret>
```

Keys are stored encrypted by Hummingbot's standard secrets handling. The
connector sends them only as `X-API-Key` / `X-API-Secret` headers over HTTPS
(no HMAC signing). Verify with `balance` and `status`.

### 6. (Do this first!) Test risk-free with paper trading

Flip Hummingbot into simulated-trading mode so no real orders are sent:

```
>>> config paper_trade_enabled True
```

Then import the bundled sample config (next step) and `start`. You'll see
simulated fills against live Bitania prices — perfect for validating spreads,
order size, and refresh timing. When you're happy:

```
>>> config paper_trade_enabled False
```

…and restart to trade for real.

### 7. Run pure market making on XMR-USDT

A ready-to-use **conservative** config ships in this repo at
[`examples/conf_pmm_bitania_XMR_USDT.yml`](examples/conf_pmm_bitania_XMR_USDT.yml)
(small order size, ~0.5% spreads, 45s refresh). Copy it into Hummingbot's
strategy-config directory, then start it:

```bash
cp bitania-hummingbot/examples/conf_pmm_bitania_XMR_USDT.yml \
   hummingbot/conf/strategies/conf_pmm_bitania_XMR_USDT.yml
```

In the Hummingbot client:

```
>>> import conf_pmm_bitania_XMR_USDT.yml
>>> start
```

Use `status` to watch active orders and inventory, and `history` to review
fills. Tune `bid_spread` / `ask_spread` / `order_amount` / `order_refresh_time`
to taste — but always re-test changes in `paper_trade` mode first.

---

## What this is

- **Exchange:** Bitania spot (`https://api.bitania.com/v1/exchange`)
- **Connector name (for `connect`):** `bitania`
- **Base class:** `ExchangePyBase` (pure Python — no Cython compile step needed)
- **Order types:** `LIMIT`, `LIMIT_MAKER` (maps to Bitania `timeInForce=post_only`), `MARKET`
- **Auth:** two plaintext headers over TLS — `X-API-Key` / `X-API-Secret`. No HMAC
  request signing, no nonce/timestamp, no listen key.
- **Symbols:** Bitania uses `BASE/QUOTE` (e.g. `BTC/USDT`); Hummingbot uses
  `BASE-QUOTE` (`BTC-USDT`). The connector converts both ways automatically.
- **Fees:** maker **0.15%**, taker **0.25%** (standard tier). The MM Program can
  rebate the maker fee to **0%** — see the Quick Start fee note.

---

## Supported pairs

The market list and per-pair trading rules come live from `GET /pairs`, so any
spot pair Bitania lists (e.g. `BTC-USDT`, `LTC-USDT`, `XMR-USDT`, `ETH-USDT`,
`TRX-USDT`) is tradeable as soon as it appears there. Price/amount increments,
minimum order size, and minimum notional are all enforced from that endpoint.

---

## How it works (architecture)

| File | Role |
|---|---|
| `bitania_constants.py` | URLs, paths, order/state maps, rate limits |
| `bitania_auth.py` | Header-only REST auth + WS auth-frame payload |
| `bitania_web_utils.py` | URL builders + `WebAssistantsFactory` (no time sync) |
| `bitania_utils.py` | `DEFAULT_FEES`, `KEYS` config map, pair filter |
| `bitania_order_book.py` | Converts Bitania book/trade shapes to HB messages |
| `bitania_api_order_book_data_source.py` | REST snapshot + WS orderbook/trades |
| `bitania_api_user_stream_data_source.py` | WS auth handshake + private fills |
| `bitania_exchange.py` | The `ExchangePyBase` connector (orders, balances, status) |

**Data flow:**
- Order book: `GET /orderbook` for the initial snapshot, then the WS `orderbook`
  channel pushes **full snapshots** (Bitania has no diff channel) which replace
  the book each tick.
- Fills: the WS `user` channel pushes `fill` events that carry the exchange
  `orderId`; these drive trade/fill updates.
- Order status (OPEN → CANCELED, etc.): REST `GET /orders/{id}` polling, where
  `{id}` is the Hummingbot client order id (Bitania accepts it directly).

---

## Status / caveats

- **Targets Hummingbot `master`.** The connector is modeled on the current
  in-tree Binance spot connector. Methods that are sensitive to a specific
  Hummingbot release are flagged with `# NOTE:` comments (e.g. the
  `ExchangePyBase.__init__` signature, the order-book snapshot parse hook name,
  the pydantic-v2 `KEYS` config map). If `connect`/construction fails on your
  version, search the connector for `NOTE` and reconcile against your installed
  Hummingbot.
- **User stream is fill-driven; REST status polling is the backup.** Bitania's
  private WS channel only emits `fill` events (no separate order-status events),
  so the connector relies on REST `_request_order_status` polling for
  OPEN/CANCELED transitions and on WS fills for fill/quantity updates.
- **`/my-trades` has no `orderId`.** The REST trade history endpoint does not tie
  trades to orders, so `_all_trade_updates_for_order` intentionally returns
  nothing and the authoritative fill source is the WS user stream (those fills
  **do** carry `orderId`). If Bitania adds `orderId` to `/my-trades`, populate
  that method.
- **No time synchronizer.** Bitania auth needs no timestamp, so the connector
  deliberately omits the `TimeSynchronizer` pre-processor entirely.
- **Fees / fills fee token.** `DEFAULT_FEES` are the standard non-program rates
  (maker 0.15% / taker 0.25%), and WS fills do not carry a per-fill fee token —
  fees are attributed as the estimated percentage in the quote asset. If you're
  in the MM Program your real maker fee may be lower (down to 0%).
- **Rate limits** in `bitania_constants.py` track the standard API-key tier
  (market-data 300/min, order placement 60/min, general 120/min). Higher tiers
  exist server-side but aren't auto-granted.
- **Single domain.** No testnet yet; `DEFAULT_DOMAIN` exists so a future
  staging/testnet host is a one-line change. Use Hummingbot's `paper_trade` mode
  to test risk-free against live prices.

---

## Running the tests

From inside your Hummingbot source tree (after copying the test folder):

```bash
conda activate hummingbot
python -m pytest test/hummingbot/connector/exchange/bitania -q
```

The provided tests mock the network layer and validate auth headers, symbol
conversion, trading-rule parsing, order placement params (incl. post-only),
balance parsing, order-status mapping, and the WS auth handshake.

---

## License

Provided as-is for the Bitania market-making community. Align with the
Apache-2.0 license of upstream Hummingbot when redistributing.
