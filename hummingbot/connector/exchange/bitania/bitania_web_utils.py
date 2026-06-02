from typing import Optional

import hummingbot.connector.exchange.bitania.bitania_constants as CONSTANTS
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


def public_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Creates a full URL for a public REST endpoint.
    :param path_url: a public REST endpoint (e.g. "/pairs")
    :param domain: the Bitania domain key (default "com" -> api.bitania.com)
    """
    return CONSTANTS.REST_URL.format(domain) + path_url


def private_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Creates a full URL for a private REST endpoint. Bitania uses the same base
    path for public and private endpoints (auth is via headers, not a path),
    so this delegates to public_rest_url.
    """
    return public_rest_url(path_url=path_url, domain=domain)


def wss_url(domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    return CONSTANTS.WSS_URL.format(domain)


def build_api_factory(
        throttler: Optional[AsyncThrottler] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
        auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    """
    Builds the WebAssistantsFactory.

    NOTE: Bitania auth needs NO timestamp/signature, so we deliberately skip the
    TimeSynchronizer and its REST pre-processor entirely (unlike Binance, which
    installs a TimeSynchronizerRESTPreProcessor here). Keep it simple.
    """
    throttler = throttler or create_throttler()
    api_factory = WebAssistantsFactory(
        throttler=throttler,
        auth=auth,
    )
    return api_factory


def build_api_factory_without_time_synchronizer_pre_processor(throttler: AsyncThrottler) -> WebAssistantsFactory:
    """
    Kept for parity with the Binance connector / framework expectations. Bitania
    never installs a time-sync pre-processor, so this is identical to the unauth
    factory.
    """
    return WebAssistantsFactory(throttler=throttler)


def create_throttler() -> AsyncThrottler:
    return AsyncThrottler(CONSTANTS.RATE_LIMITS)


async def get_current_server_time(
        throttler: Optional[AsyncThrottler] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
) -> float:
    """
    Returns the Bitania server time in milliseconds. Not strictly needed (auth
    is timestamp-free) but provided for the framework's get_current_server_time
    hook. Reads {"serverTime": <unix ms>} from GET /time.
    """
    throttler = throttler or create_throttler()
    api_factory = build_api_factory_without_time_synchronizer_pre_processor(throttler=throttler)
    rest_assistant = await api_factory.get_rest_assistant()
    response = await rest_assistant.execute_request(
        url=public_rest_url(path_url=CONSTANTS.SERVER_TIME_PATH_URL, domain=domain),
        method=RESTMethod.GET,
        throttler_limit_id=CONSTANTS.SERVER_TIME_PATH_URL,
    )
    server_time = response["serverTime"]
    return server_time
