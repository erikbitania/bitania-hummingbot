from decimal import Decimal
from typing import Any, Dict

from pydantic import ConfigDict, Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "BTC-USDT"

# Bitania's standard spot fees: maker 0.15%, taker 0.25% (server defaults in
# gbit.services.exchange_admin). The MM Program can rebate the maker fee down to
# 0% (gold tier) — Hummingbot can't model a tier rebate statically, so these are
# the conservative non-program rates; effective PnL improves for program MMs.
DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.0015"),
    taker_percent_fee_decimal=Decimal("0.0025"),
    buy_percent_fee_deducted_from_returns=True,
)


def is_exchange_information_valid(pair_info: Dict[str, Any]) -> bool:
    """
    Returns True if a pair entry from GET /pairs is tradeable. Bitania's /pairs
    response only lists active spot pairs, so by default everything with a
    symbol is valid. We keep a hook here so a future "status"/"tags" filter can
    be added without touching the exchange class.

    NOTE: if Bitania later adds a per-pair status flag or a "disabled" tag,
    filter on it here.
    """
    return bool(pair_info.get("symbol"))


class BitaniaConfigMap(BaseConnectorConfigMap):
    connector: str = "bitania"
    bitania_api_key: SecretStr = Field(
        default=...,
        json_schema_extra={
            "prompt": lambda cm: "Enter your Bitania API key",
            "is_secure": True,
            "is_connect_key": True,
            "prompt_on_new": True,
        }
    )
    bitania_api_secret: SecretStr = Field(
        default=...,
        json_schema_extra={
            "prompt": lambda cm: "Enter your Bitania API secret",
            "is_secure": True,
            "is_connect_key": True,
            "prompt_on_new": True,
        }
    )
    model_config = ConfigDict(title="bitania")


# NOTE: version-sensitive. Recent Hummingbot uses pydantic v2 + model_construct()
# and BaseConnectorConfigMap. Older releases used pydantic v1 ConfigVar/
# BaseConnectorConfigMap with a different Field schema. Reconcile with your
# installed hummingbot.client.config.config_data_types if connect fails.
KEYS = BitaniaConfigMap.model_construct()
